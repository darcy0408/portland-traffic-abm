"""Trip-level D1-D3 diversion instrument for the pre-registered Rose Quarter
I-5 SB closure (PREREG_I5_ROSEQUARTER.md, section 2). Pure routing analysis:
no simulation runs, no simulation output is read or written.

The frozen pairing rule, implemented literally: the open-arm spawn population
is drawn ONCE per seed, exactly as generate.run_simulation draws its initial
population (same make_vehicle code path, same dedicated random.Random(seed)
trip stream; the fleet and driver draws live on their own RNG streams by
construction, so omitting them here leaves the trip stream untouched). Each
trip routes at free-flow travel time on the open graph. The SAME OD pairs are
then routed on the closed graph (the frozen 5-edge SB span removed). ODs with
no closed-graph path are dropped and counted; the prereg expects that count
to be 0.

An AFFECTED trip is one whose open-arm planned route includes at least one
edge of the frozen span. Unaffected trips contribute zero to every paired
difference by construction: removing edges cannot improve any path that
avoided them, so a route that missed the span stays optimal and unchanged.
The metrics therefore only need the affected trips re-routed.

  D1  share of affected trips whose planned route includes any mainline edge
      of a named detour freeway (I 405; separately I 205), open vs closed.
  D2  share of affected trips that INCREASE their mainline distance on that
      detour freeway under the closure.
  D3  added mainline vehicle-km per seed on each detour freeway.

Identity guards, all hard failures because a silent mismatch would break the
"same population as the campaign" claim: the frozen-span check (imported from
the campaign script), the metro-size graph guard, the config stack the
campaign ran under, and the demand-context counts from the campaign's own
SLURM log (job 126285: 215,655 placeable OD pairs, 531,245 commuters, 20,857
boundary nodes).

    python src/rosequarter_d123.py --check                # guards only
    python src/rosequarter_d123.py --run                  # all 8 seeds
    python src/rosequarter_d123.py --readout              # aggregate D1-D3

--nonwork runs the same metrics for the fwrqn demand arm (prereg Appendix G,
registered before this mode existed). The realism arm did NOT need this:
routing is once-at-spawn at free-flow, so a dynamics-only variant inherits the
base arm's population and routes (Appendix B.1). fwrqn changes DEMAND, so the
drawn population genuinely differs and the metrics must be recomputed. The mode
turns the B3 flag on for this process only, guards the fwrqn campaign's own
non-work fingerprint on top of the LODES one, and writes under an rqd123n_
prefix so the base arm's outputs can never be overwritten.

Data paths default to the repo's config but are overridable, because the
campaign's bit-verified metro graph and raw demand files live outside this
working copy:

    --graph PATH    the campaign graph.graphml (md5 recorded in every output)
    --raw-dir PATH  cenpop2020_bg_or.txt + or_wac_2021.csv.gz + or_od_main_2021.csv.gz
    --out-dir PATH  where rqd123_* outputs land

Outputs per seed: rqd123_open_s{seed}.json (open-pass intermediate, lets a
restart skip the expensive draw), rqd123_s{seed}.json (final summary), and
rqd123_affected_s{seed}.parquet (per-affected-trip audit rows).
"""
import argparse
import hashlib
import json
import os
import random
import sys
import time

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import generate        # noqa: E402
import landuse_data    # noqa: E402  (non-work attraction table, --nonwork guard)
from freeway_rosequarter import (SEEDS, EXPECTED_SB,      # noqa: E402
                                 EXPECTED_REMOVED_N, _verify_span)
from freeway_runs import SCENARIOS  # noqa: E402  (the verified closure specs)

# The two pre-registered detour freeways. I 5 is carried alongside as context
# (how much of the closed route stays on I-5 elsewhere), not as a D-metric.
DETOURS = ("I 405", "I 205")
TRACK = DETOURS + ("I 5",)

# Campaign-environment fingerprints from the original run's log
# (~/pta-freeway/logs/fwrq_126285_7.out, job 126285, Aug 13 2026). If this
# machine builds a different demand context, the drawn population is NOT the
# campaign's population and the run must stop.
EXPECTED_OD_PAIRS = 215_655
EXPECTED_COMMUTERS = 531_245
EXPECTED_BOUNDARY_NODES = 20_857

# The non-work arm's own fingerprint, from the fwrqn campaign log
# (~/pta-freeway/logs/fwrqn_126805_7.out, job 126805, Aug 14 2026). That log
# also shows the LODES numbers above are UNCHANGED by the layer, which is why
# the commute guard still applies in --nonwork mode: the layer is additive.
EXPECTED_NONWORK_BGS = 1_003
EXPECTED_NONWORK_JOBS = 161_304


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _guard_config(nonwork=False):
    """The campaign stack: refuse to draw under any other config, because every
    flag here changes what the trip RNG stream produces. The non-work flag is
    expected to match the requested MODE, so a config.py edited to True cannot
    silently turn a base-arm run into a non-work one, or the reverse."""
    checks = [
        ("N_VEHICLES", config.N_VEHICLES, 16500),
        ("DEMAND_LODES_OD", config.DEMAND_LODES_OD, True),
        ("THROUGH_TRAFFIC_FRACTION", config.THROUGH_TRAFFIC_FRACTION, 0.15),
        ("DEMAND_NONWORK_ENABLED", config.DEMAND_NONWORK_ENABLED, nonwork),
        ("STUDY_RADIUS_M", config.STUDY_RADIUS_M, 20000),
    ]
    if nonwork:
        # the two a-priori NHTS constants the fwrqn campaign ran under
        checks += [
            ("NONWORK_SHARE", config.NONWORK_SHARE, 0.386),
            ("NONWORK_DECAY_SCALE_M", config.NONWORK_DECAY_SCALE_M, 5900.0),
        ]
    bad = [f"{k} = {got!r} (campaign ran {want!r})"
           for k, got, want in checks if got != want]
    if bad:
        raise SystemExit("config does not match the fwrq campaign stack:\n  "
                         + "\n  ".join(bad))


def _load_graph(path):
    if not os.path.exists(path):
        raise SystemExit(f"no graph at {path}")
    print(f"loading graph {path} ...")
    G = ox.load_graphml(path)
    if G.number_of_edges() < 100_000:
        raise SystemExit(f"graph has {G.number_of_edges():,} edges; the "
                         f"campaign ran on the metro graph, refusing")
    print(f"graph: {G.number_of_nodes():,} nodes / {G.number_of_edges():,} edges")
    return G


def _build_contexts(G, nodes, nonwork=False):
    """Demand + through contexts, then the log-fingerprint guard."""
    demand = generate.build_demand_weights(G, nodes)
    through = generate.build_through_context(G, nodes)
    if demand is None or demand.get("mode") != "od":
        raise SystemExit("demand context is not LODES OD; the campaign's was")
    nw = demand.get("nonwork")
    if nonwork:
        # the layer must be live, and be the one the fwrqn campaign built
        if nw is None:
            raise SystemExit("--nonwork asked for the B3 layer but the demand "
                             "context has none (missing data?); refusing")
        lu = landuse_data.nonwork_table()
        got = (len(lu), int(round(float(lu["nonwork_attr"].sum()))))
        want = (EXPECTED_NONWORK_BGS, EXPECTED_NONWORK_JOBS)
        if got != want:
            raise SystemExit(
                f"non-work context differs from the fwrqn campaign's: got "
                f"{got[0]} block groups / {got[1]:,} retail-service jobs, "
                f"campaign log says {want[0]} / {want[1]:,}")
        print("non-work context matches the fwrqn campaign log fingerprint")
    elif nw is not None:
        raise SystemExit("the B3 non-work layer is live but this is a base-arm "
                         "run; refusing (use --nonwork)")
    n_pairs = len(demand["weights"])
    n_comm = int(round(sum(demand["weights"])))
    n_bound = len(through["nodes"]) if through else 0
    if (n_pairs, n_comm, n_bound) != (EXPECTED_OD_PAIRS, EXPECTED_COMMUTERS,
                                      EXPECTED_BOUNDARY_NODES):
        raise SystemExit(
            f"demand context differs from the campaign's: got {n_pairs} pairs / "
            f"{n_comm} commuters / {n_bound} boundary nodes, campaign log says "
            f"{EXPECTED_OD_PAIRS} / {EXPECTED_COMMUTERS} / {EXPECTED_BOUNDARY_NODES}")
    print("demand context matches the campaign log fingerprint")
    return demand, through


def _meters_on(route, edge_set):
    """Meters a planned route spends on edges in edge_set. Route entries are
    generate._edge_between tuples: (u, v, k, length_m, v0_mps)."""
    return sum(e[3] for e in route if (e[0], e[1], e[2]) in edge_set)


def _fftime_s(route):
    return sum(e[3] / e[4] for e in route)


def _route_edges(G, path):
    """Node path -> the same per-hop edge picks the simulation makes."""
    return [generate._edge_between(G, path[i], path[i + 1])
            for i in range(len(path) - 1)]


def _prefix(args):
    """Separate namespace per arm, so a non-work run can never overwrite the
    base arm's registered outputs (prereg Appendix G)."""
    return "rqd123n" if args.nonwork else "rqd123"


def _open_path(args, seed):
    return os.path.join(args.out_dir, f"{_prefix(args)}_open_s{seed}.json")


def _final_path(args, seed):
    return os.path.join(args.out_dir, f"{_prefix(args)}_s{seed}.json")


def _open_pass(G, nodes, demand, through, mains, span_set, seed):
    """Draw the seed's full initial population and keep the affected trips."""
    config.RANDOM_SEED = seed
    generate.set_seeds(seed)
    rng = random.Random(seed)
    n_spawned, n_failed = 0, 0
    affected = []
    t0 = time.perf_counter()
    for vid in range(config.N_VEHICLES):
        veh = generate.make_vehicle(G, nodes, rng, vid, demand, through,
                                    None, None)
        if veh is None:
            n_failed += 1
            continue
        n_spawned += 1
        route = veh["route"]
        span_m = _meters_on(route, span_set)
        if span_m <= 0:
            continue
        rec = {"o": route[0][0], "d": route[-1][1],
               "open_span_m": span_m, "open_fft_s": _fftime_s(route)}
        for ref in TRACK:
            rec[f"open_{ref.replace(' ', '')}_m"] = _meters_on(route, mains[ref])
        affected.append(rec)
        if (vid + 1) % 2500 == 0:
            el = time.perf_counter() - t0
            print(f"  seed {seed}: {vid + 1}/{config.N_VEHICLES} drawn, "
                  f"{len(affected)} affected, {el:.0f}s", flush=True)
    return {"seed": seed, "n_target": config.N_VEHICLES,
            "n_spawned": n_spawned, "n_route_failures": n_failed,
            "n_affected": len(affected), "affected": affected,
            "draw_seconds": round(time.perf_counter() - t0, 1)}


def _closed_pass(G_closed, open_rec, mains, out_dir, graph_md5, args):
    """Route the affected ODs on the closed graph and score D1-D3."""
    seed = open_rec["seed"]
    rows, n_dropped = [], 0
    t0 = time.perf_counter()
    for rec in open_rec["affected"]:
        try:
            path = nx.shortest_path(G_closed, rec["o"], rec["d"],
                                    weight="travel_time_s")
        except nx.NetworkXNoPath:
            n_dropped += 1
            continue
        route = _route_edges(G_closed, path)
        row = dict(rec)
        row["closed_fft_s"] = _fftime_s(route)
        for ref in TRACK:
            row[f"closed_{ref.replace(' ', '')}_m"] = _meters_on(route, mains[ref])
        rows.append(row)

    df = pd.DataFrame(rows)
    d1, d2, d3 = {}, {}, {}
    for ref in DETOURS:
        c = ref.replace(" ", "")
        d1[ref] = {"open_share": float((df[f"open_{c}_m"] > 0).mean()),
                   "closed_share": float((df[f"closed_{c}_m"] > 0).mean())}
        added = df[f"closed_{c}_m"] - df[f"open_{c}_m"]
        d2[ref] = float((added > 0).mean())
        d3[ref] = float(added.sum() / 1000.0)

    summary = {
        "seed": seed,
        "n_target": open_rec["n_target"],
        "n_spawned": open_rec["n_spawned"],
        "n_route_failures": open_rec["n_route_failures"],
        "n_affected": open_rec["n_affected"],
        "n_dropped_closed": n_dropped,
        "D1": d1, "D2": d2, "D3_added_vkm": d3,
        # descriptive context, NOT part of the frozen D-metrics
        "descriptive": {
            "affected_share_of_spawned":
                open_rec["n_affected"] / open_rec["n_spawned"],
            "added_fft_min_mean":
                float((df["closed_fft_s"] - df["open_fft_s"]).mean() / 60.0),
        },
        "provenance": {
            "graph": os.path.abspath(args.graph), "graph_md5": graph_md5,
            "raw_dir": os.path.abspath(args.raw_dir),
            "span_edges": sorted([list(e) for e in
                                  {tuple(e) for e in open_rec["span_edges"]}]),
            "instrument": "src/rosequarter_d123.py",
            "arm": "nonwork" if args.nonwork else "base",
            "nonwork_layer": ({"block_groups": EXPECTED_NONWORK_BGS,
                               "retail_service_jobs": EXPECTED_NONWORK_JOBS,
                               "share": config.NONWORK_SHARE,
                               "decay_m": config.NONWORK_DECAY_SCALE_M}
                              if args.nonwork else None),
            "closed_seconds": round(time.perf_counter() - t0, 1),
        },
    }
    df.to_parquet(os.path.join(out_dir,
                               f"{_prefix(args)}_affected_s{seed}.parquet"),
                  index=False)
    with open(_final_path(args, seed), "w") as f:
        json.dump(summary, f, indent=1)
    print(f"  seed {seed}: {len(df)} affected routed closed "
          f"({n_dropped} dropped), D3 I405 {d3['I 405']:+.0f} vkm, "
          f"I205 {d3['I 205']:+.0f} vkm")
    return summary


def run(args):
    _guard_config(args.nonwork)
    G = _load_graph(args.graph)
    graph_md5 = _md5(args.graph)
    print(f"graph md5 {graph_md5}")
    config.RAW_DIR = args.raw_dir          # demand builders read this at call time
    generate.prepare_network(G)
    removed = _verify_span(G)              # the frozen-span guard, before anything
    span_set = set(removed)
    print(f"frozen span OK: {len(removed)} edges")
    nodes = list(G.nodes)
    demand, through = _build_contexts(G, nodes, args.nonwork)
    mains = {ref: set(generate.freeway_mainline_edges(G, ref)) for ref in TRACK}

    # open passes first for every seed that needs one, on the pristine graph;
    # only then is the graph closed (mutated in place), so the draw stream can
    # never see a modified graph
    open_recs = {}
    for seed in SEEDS:
        if os.path.exists(_final_path(args, seed)):
            print(f"seed {seed}: final summary exists, skipping")
            continue
        op = _open_path(args, seed)
        if os.path.exists(op):
            with open(op) as f:
                open_recs[seed] = json.load(f)
            print(f"seed {seed}: reusing open pass ({open_recs[seed]['n_affected']} affected)")
            continue
        print(f"seed {seed}: open pass (drawing {config.N_VEHICLES} trips)")
        rec = _open_pass(G, nodes, demand, through, mains, span_set, seed)
        rec["span_edges"] = [list(e) for e in removed]
        with open(op, "w") as f:
            json.dump(rec, f)
        open_recs[seed] = rec
        print(f"seed {seed}: {rec['n_affected']} affected of "
              f"{rec['n_spawned']} spawned ({rec['draw_seconds']}s)")

    if not open_recs:
        print("all seeds already final")
        return
    removed_now = generate.apply_freeway_closure(G, SCENARIOS["rosequarter"])
    if set(removed_now) != span_set:
        raise SystemExit("closure removed different edges than the verified "
                         "span; refusing to score")
    for seed in SEEDS:
        if seed in open_recs:
            _closed_pass(G, open_recs[seed], mains, args.out_dir, graph_md5, args)


def readout(args):
    sums = []
    for seed in SEEDS:
        p = _final_path(args, seed)
        if os.path.exists(p):
            with open(p) as f:
                sums.append(json.load(f))
    if not sums:
        raise SystemExit(f"no rqd123 summaries in {args.out_dir}")
    md5s = {s["provenance"]["graph_md5"] for s in sums}
    if len(md5s) > 1:
        raise SystemExit(f"summaries mix graphs: {md5s}")
    print(f"seeds: {len(sums)}/{len(SEEDS)}   graph md5 {md5s.pop()}")
    tot_drop = sum(s["n_dropped_closed"] for s in sums)
    print(f"affected per seed: "
          + ", ".join(str(s['n_affected']) for s in sums)
          + f"   dropped (no closed path): {tot_drop} (prereg expects 0)")

    def stats(vals):
        a = np.array(vals, dtype=float)
        return a.mean(), a.std(ddof=1)

    print(f"\n{'metric':<34s} {'mean':>10s} {'sd':>8s}   per-seed")
    for ref in DETOURS:
        for label, fn in [
                (f"D1 {ref} share open", lambda s: s["D1"][ref]["open_share"]),
                (f"D1 {ref} share closed", lambda s: s["D1"][ref]["closed_share"]),
                (f"D2 {ref} share increased", lambda s: s["D2"][ref]),
                (f"D3 {ref} added veh-km", lambda s: s["D3_added_vkm"][ref])]:
            vals = [fn(s) for s in sums]
            m, sd = stats(vals)
            shown = " ".join(f"{v:.3f}" if abs(v) < 10 else f"{v:.0f}"
                             for v in vals)
            print(f"{label:<34s} {m:>10.3f} {sd:>8.3f}   {shown}")
    # Appendix G citation rule: D3 is a per-seed total over the affected
    # population, so it falls mechanically when that population shrinks. Print
    # the affected share and the per-affected-trip value beside it, always, so
    # a smaller D3 can never be read as weaker diversion.
    m, sd = stats([s["descriptive"]["affected_share_of_spawned"] for s in sums])
    print(f"\n{'affected share of spawned':<34s} {m:>10.4f} {sd:>8.4f}")
    for ref in DETOURS:
        per = [s["D3_added_vkm"][ref] / s["n_affected"] for s in sums]
        m, sd = stats(per)
        print(f"{'D3 ' + ref + ' vkm per affected trip':<34s} {m:>10.3f} {sd:>8.3f}")

    m, sd = stats([s["descriptive"]["added_fft_min_mean"] for s in sums])
    print(f"\ndescriptive (not a frozen metric): affected trips add "
          f"{m:.1f} +/- {sd:.1f} min free-flow travel time")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--run", action="store_true")
    g.add_argument("--readout", action="store_true")
    ap.add_argument("--graph",
                    default=os.path.join(config.NETWORK_DIR, "graph.graphml"))
    ap.add_argument("--raw-dir", default=config.RAW_DIR)
    ap.add_argument("--out-dir", default=config.PROCESSED_DIR)
    ap.add_argument("--nonwork", action="store_true",
                    help="score the fwrqn demand arm (prereg Appendix G)")
    args = ap.parse_args()

    # the arm is chosen HERE and nowhere else: the committed config default
    # stays False, and the guards below assert the flag matches the mode
    config.DEMAND_NONWORK_ENABLED = args.nonwork
    print(f"arm: {'nonwork (fwrqn)' if args.nonwork else 'base (fwrq)'}")

    if args.check:
        _guard_config(args.nonwork)
        G = _load_graph(args.graph)
        generate.prepare_network(G)
        removed = _verify_span(G)
        print(f"graph md5 {_md5(args.graph)}")
        print(f"frozen span OK: {len(removed)} edges "
              f"({len(EXPECTED_SB)} SB mainline + "
              f"{len(removed) - len(EXPECTED_SB)} stranded ramps)")
        config.RAW_DIR = args.raw_dir
        _build_contexts(G, list(G.nodes), args.nonwork)
    elif args.run:
        run(args)
    else:
        readout(args)


if __name__ == "__main__":
    main()
