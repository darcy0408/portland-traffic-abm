"""Paired multi-seed I-205 closure campaign: license the far-field claims.

The single-seed campaign (src/freeway_runs.py) showed the near-field
redistribution clearly but could NOT support any far-field statement, because
a microscopic model jitters ~50% of all segments at every distance when
perturbed. Freeway-to-freeway diversion is exactly a far-field claim: a trip
pushed off I-205 rejoins I-5 kilometers away, well inside the chaos floor.

The fix is pairing plus replication. For each seed s, run the same demand open
and closed, and difference them: D(s) = closed(s) - open(s). Chaos still
contaminates each individual D(s), but it is unbiased noise, so averaging over
independent seeds shrinks it while a real diversion effect persists. The claim
is then a statement about the DISTRIBUTION of D across seeds (does it exclude
zero), not about one run's difference.

Arms: open, abernethy (the ODOT precedent stretch), powell (the well-supported
stretch). Seeds: the project's pinned 8-seed set. 24 tasks total.

One task per SLURM array index, each writing its own uniquely named files, so
the one-simulation-at-a-time rule holds per process and nothing shares an
output path. Finished tasks skip on their summary, so resubmitting after a
partial failure is safe.

    python src/freeway_multiseed.py --list         # show the task table
    python src/freeway_multiseed.py --task 7       # run one task
    python src/freeway_multiseed.py --readout      # analyze saved summaries

F6 (--realism): the original campaign ran the BASE model with the whole
realism stack off, while the ablation shows lane-changing is what reaches real
Powell volume -- so its absolute grams are understated (ledger flag F6; the
paired DIRECTION is unaffected). --realism reruns the same 24 tasks with the
Jul 29 realism stack on, under the prefix fwmsr so the base campaign's files
can never be overwritten. Modeling note: Webster's seeded warmup times the
signals to the flows of the graph each run actually serves, so in the closed
arms the signals are timed to the CLOSED network -- the result models the
adapted state, not day one of a surprise closure.

    python src/freeway_multiseed.py --realism --task 7
    python src/freeway_multiseed.py --realism --readout
"""
import argparse
import json
import os
import sys

import numpy as np
import osmnx as ox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import generate        # noqa: E402
from freeway_runs import SCENARIOS  # noqa: E402  (the verified closure specs)
import metro_calibrated_experiment as mce  # noqa: E402  (the realism stack)

# the project's pinned seed set, reused so this campaign is comparable with the
# lane and ablation experiments rather than introducing a new set
SEEDS = (42, 7, 13, 99, 314, 777, 2024, 8)
ARMS = ("open", "abernethy", "powell")
PREFIX = "fwms"          # base campaign; --realism switches this to "fwmsr"

# The realism-stack flags, referenced from metro_calibrated_experiment rather
# than retyped so this campaign and the metrocal/ablation experiments can never
# drift apart (the same rule metro_b13_experiment follows). All-True dict:
# MOBIL, driver heterogeneity, Webster, green-wave.
REALISM_FLAGS = dict(mce.ARMS["realism"])
STACK_REALISM = False    # set by --realism in main(), before any dispatch

# routes whose mainline totals are tracked per run. I-5 is the diversion
# hypothesis; I-205 is the closed route itself (the sanity check that it drops);
# the others are the surface alternates that should absorb the local share.
TRACK_ROUTES = ("I 5", "I 205", "OR 213", "OR 99E", "US 26")


def tasks():
    return [(arm, seed) for arm in ARMS for seed in SEEDS]


def run_name(arm, seed):
    return f"{PREFIX}_{arm}_s{seed}"


def summary_path(arm, seed):
    return os.path.join(config.PROCESSED_DIR, f"{run_name(arm, seed)}_summary.json")


def run_task(idx):
    arm, seed = tasks()[idx]
    out = summary_path(arm, seed)
    if os.path.exists(out):
        print(f"task {idx} ({arm}, seed {seed}) already done -> {out}")
        return

    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        raise SystemExit(f"no cached graph at {graph_file}; refusing to "
                         f"download mid-experiment")
    G = ox.load_graphml(graph_file)

    # the seed is what this experiment varies, so set it before anything draws
    config.RANDOM_SEED = seed
    config.RUN_NAME = run_name(arm, seed)

    # F6: set every stack flag EXPLICITLY, True or False, following run_one's
    # precedent in metro_calibrated_experiment -- a task must never inherit
    # these from a config default or a reused interpreter.
    for k in REALISM_FLAGS:
        setattr(config, k, STACK_REALISM)

    removed = []
    if arm != "open":
        removed = generate.apply_freeway_closure(G, SCENARIOS[arm])
        print(f"[{config.RUN_NAME}] removed {len(removed)} freeway edges")

    generate.set_seeds(seed)
    totals, nox, thru = generate.run_simulation(G, use_checkpoint=False)
    generate.save_results(totals, nox, thru)

    # Compact summary so the readout needs only these files, not the parquets.
    # Per-edge values for the tracked mainlines (a few hundred numbers) let the
    # readout do a paired per-segment test, not just a route total.
    routes = {}
    for ref in TRACK_ROUTES:
        keys = generate.freeway_mainline_edges(G, ref)
        if not keys:
            continue
        routes[ref] = {f"{u}_{v}_{k}": [float(nox.get((u, v, k), 0.0)),
                                        float(thru.get((u, v, k), 0.0))]
                       for u, v, k in keys}
    rec = {
        "arm": arm, "seed": seed,
        "stack": "realism" if STACK_REALISM else "base",
        "n_vehicles": config.N_VEHICLES, "n_steps": config.N_STEPS,
        "removed": [[u, v, k] for u, v, k in removed],
        "network_nox_g": float(sum(nox.values())),
        "network_throughput": float(sum(thru.values())),
        "routes": routes,
    }
    with open(out, "w") as f:
        json.dump(rec, f)
    print(f"[{config.RUN_NAME}] summary -> {out}")


def _paired(summaries, arm, ref, field):
    """Per-seed paired difference on route `ref`, closed arm minus open.
    field 0 = NOx grams, 1 = throughput."""
    diffs, rel = [], []
    for seed in SEEDS:
        o = summaries.get(("open", seed))
        c = summaries.get((arm, seed))
        if not o or not c or ref not in o["routes"] or ref not in c["routes"]:
            continue
        # the closed run is missing the removed edges; treat them as zero so the
        # route total is comparable rather than silently shorter
        ko = o["routes"][ref]
        kc = c["routes"][ref]
        so = sum(v[field] for v in ko.values())
        sc = sum(kc.get(key, [0.0, 0.0])[field] for key in ko)
        diffs.append(sc - so)
        rel.append(100.0 * (sc - so) / so if so else float("nan"))
    return np.array(diffs), np.array(rel)


def readout():
    summaries = {}
    for arm, seed in tasks():
        p = summary_path(arm, seed)
        if os.path.exists(p):
            with open(p) as f:
                summaries[(arm, seed)] = json.load(f)
    # a summary written under the wrong prefix would silently mix campaigns;
    # the stack field (absent = the pre-F6 base campaign) makes that fatal
    want = "realism" if STACK_REALISM else "base"
    for (arm, seed), s in summaries.items():
        got = s.get("stack", "base")
        if got != want:
            raise SystemExit(f"{summary_path(arm, seed)} records stack={got} "
                             f"but this readout is for {want}; wrong file")
    have = {a: sum(1 for (arm, _) in summaries if arm == a) for a in ARMS}
    print(f"stack: {want}")
    print(f"summaries found: " +
          ", ".join(f"{a} {have[a]}/{len(SEEDS)}" for a in ARMS))
    if have["open"] < 2:
        raise SystemExit("need at least 2 paired seeds for a distribution")

    f_no2 = config.F_NO2
    for arm in ("abernethy", "powell"):
        print(f"\n{'=' * 72}\n{arm.upper()}: paired per-seed differences "
              f"(closed - open, same seed)\n{'=' * 72}")
        n_ok = sum(1 for (a, _) in summaries if a == arm)
        if n_ok < 2:
            print("  not enough seeds yet")
            continue
        print(f"{'route':>8s} {'n':>3s} {'mean %':>8s} {'sd %':>7s} "
              f"{'min %':>7s} {'max %':>7s} {'signs':>7s}  verdict")
        for ref in TRACK_ROUTES:
            d, rel = _paired(summaries, arm, ref, 0)
            if len(d) < 2:
                continue
            pos = int((d > 0).sum())
            # A claim survives only if every seed agrees in sign AND the mean is
            # several standard deviations from zero. With 8 seeds a unanimous
            # sign is p = 2^-8 = 0.004 under a fair-coin null, which is the
            # honest non-parametric version of "not chaos".
            unanimous = pos == len(d) or pos == 0
            t = abs(rel.mean()) / (rel.std(ddof=1) / np.sqrt(len(rel))) \
                if rel.std(ddof=1) > 0 else float("inf")
            verdict = ("SUPPORTED" if unanimous and t > 3
                       else "weak" if unanimous else "NOT SUPPORTED")
            print(f"{ref:>8s} {len(d):3d} {rel.mean():+8.2f} {rel.std(ddof=1):7.2f} "
                  f"{rel.min():+7.2f} {rel.max():+7.2f} {pos:3d}/{len(d):<3d} "
                  f" {verdict} (t={t:.1f})")
        d, _ = _paired(summaries, arm, "I 5", 0)
        print(f"\n  I-5 mainline NO2 shift: "
              f"{f_no2 * d.mean():+.1f} g/run (sd {f_no2 * d.std(ddof=1):.1f}, "
              f"n={len(d)} seeds)")


def near_readout(near_km=2.0):
    """Same unanimity test, applied to the NEAR-FIELD streets.

    The route readout above answers the far-field diversion question from the
    small summaries. This one answers "are the headline street numbers stable
    across seeds", which needs the per-segment parquets (pull them from the
    cluster into data/processed first). Single-seed street percentages like
    "+459% on McLoughlin" are worth nothing until they survive this.
    """
    import pandas as pd

    # Geometry and names as a frame indexed like the results, so the per-seed
    # work below is vectorized. Row-by-row it would be ~2.5M iterrows plus a
    # haversine each, which costs minutes per readout for no reason.
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    recs = []
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        if isinstance(nm, list):
            nm = nm[0] if nm else None
        recs.append((u, v, k,
                     0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"])),
                     0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"])),
                     str(nm) if nm else "(unnamed)"))
    geo = pd.DataFrame(recs, columns=["u", "v", "key", "lat", "lon", "name"]) \
            .set_index(["u", "v", "key"])

    def haversine_np(lat0, lon0, lat, lon):
        """Vectorized great-circle distance in km, same formula as
        generate._haversine_m so the two agree."""
        r = 6_371_000.0
        p1, p2 = np.radians(lat0), np.radians(lat)
        dp, dl = np.radians(lat - lat0), np.radians(lon - lon0)
        a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
        return 2 * r * np.arcsin(np.sqrt(a)) / 1000.0

    def seg(arm, seed):
        p = os.path.join(config.PROCESSED_DIR,
                         f"{run_name(arm, seed)}_segments.parquet")
        if not os.path.exists(p):
            return None
        return pd.read_parquet(p).set_index(["u", "v", "key"])

    for arm in ("abernethy", "powell"):
        per_seed = {}      # street -> list of per-seed percent changes
        used = 0
        for s in SEEDS:
            o, c = seg("open", s), seg(arm, s)
            if o is None or c is None:
                continue
            used += 1
            j = o.join(c, how="left", lsuffix="_o", rsuffix="_c").fillna(0.0)
            j["d"] = j.nox_g_c - j.nox_g_o
            j = j.join(geo, how="inner")
            with open(summary_path(arm, s)) as fh:
                removed = [tuple(e) for e in json.load(fh)["removed"]]
            rem_geo = geo.loc[geo.index.intersection(removed)]
            clat, clon = rem_geo.lat.mean(), rem_geo.lon.mean()

            j["km"] = haversine_np(clat, clon, j.lat.values, j.lon.values)
            near = j[(j.km <= near_km) & (~j.index.isin(set(removed)))]
            g = near.groupby("name").agg(d=("d", "sum"), base=("nox_g_o", "sum"))
            g = g[g.base > 0]
            for nm, row in g.iterrows():
                per_seed.setdefault(nm, []).append((row.d, row.base))

        print(f"\n{'=' * 72}\n{arm.upper()} near field (<={near_km:.0f} km), "
              f"{used} paired seeds\n{'=' * 72}")
        if used < 2:
            print("  need the parquets for at least 2 paired seeds")
            continue
        # Rank by GRAMS moved, not percent. Percent ranking puts tiny streets
        # whose baseline is near zero at the top (a dead-end going from 0.01 g
        # to 0.5 g is +4,900%) and buries the arterials that actually carry the
        # detour. Percent is still shown, because it is what makes the result
        # legible, but it is not what decides importance.
        f = config.F_NO2
        rows = []
        for nm, v in per_seed.items():
            if len(v) != used:
                continue
            dg = np.array([x[0] for x in v]) * f
            base = np.array([x[1] for x in v]) * f
            pct = 100.0 * dg / np.where(base > 0, base, np.nan)
            rows.append((nm, dg.mean(),
                         dg.std(ddof=1) if len(dg) > 1 else 0.0,
                         float(np.nanmean(pct)), int((dg > 0).sum()), len(dg)))
        print(f"{'street':34s} {'mean g':>9s} {'sd g':>8s} {'mean %':>9s} "
              f"{'signs':>6s}  verdict")
        for nm, m, sd, pct, pos, n in sorted(rows, key=lambda r: -abs(r[1]))[:15]:
            unanimous = pos == n or pos == 0
            t = abs(m) / (sd / np.sqrt(n)) if sd > 0 else float("inf")
            verdict = ("SUPPORTED" if unanimous and t > 3
                       else "weak" if unanimous else "NOT SUPPORTED")
            print(f"{nm[:34]:34s} {m:+9.1f} {sd:8.1f} {pct:+8.1f}% "
                  f"{pos:3d}/{n:<2d}  {verdict} (t={t:.1f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", type=int)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--readout", action="store_true")
    ap.add_argument("--near-readout", action="store_true",
                    help="near-field street stability; needs the parquets")
    ap.add_argument("--realism", action="store_true",
                    help="F6: run/read the realism-stack campaign (fwmsr)")
    args = ap.parse_args()

    if args.realism:
        global PREFIX, STACK_REALISM
        PREFIX = "fwmsr"
        STACK_REALISM = True

    if args.count:
        print(len(tasks()))
    elif args.list:
        for i, (arm, seed) in enumerate(tasks()):
            done = "done" if os.path.exists(summary_path(arm, seed)) else ""
            print(f"{i:3d}  {arm:10s} seed {seed:<5d} {done}")
    elif args.near_readout:
        near_readout()
    elif args.readout:
        readout()
    elif args.task is not None:
        run_task(args.task)
    else:
        ap.error("give one of --task/--list/--count/--readout")


if __name__ == "__main__":
    main()
