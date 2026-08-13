"""Paired multi-seed Rose Quarter I-5 SB closure campaign (pre-registered).

Models the real ODOT closure (project 19071): I-5 SOUTHBOUND shuts completely
for up to 5 weeks starting Sept 11 2026, between the I-405 and I-84
interchanges, signed detour I-405 SB, regional traffic directed to I-205. The
campaign design, metrics, and verdict rules are frozen in
PREREG_I5_ROSEQUARTER.md BEFORE any task runs; the whole point is a prediction
banked before the real closure produces data, so nothing here is tuned after
results are seen.

Same instrument as the fwms campaign (src/freeway_multiseed.py): for each seed
run the same demand open and closed, difference per seed, and make claims only
about the distribution of paired differences across seeds. 2 arms x 8 block-1
seeds = 16 tasks, one per SLURM array index, each writing its own files;
finished tasks skip on their summary, so resubmission is safe.

    python src/freeway_rosequarter.py --check        # verify the frozen span
    python src/freeway_rosequarter.py --list         # show the task table
    python src/freeway_rosequarter.py --task 7       # run one task
    python src/freeway_rosequarter.py --readout      # analyze saved summaries

The open arm is recomputed under this campaign's prefix rather than reusing
the fwms open summaries, because this campaign tracks I-405 (the signed
detour) and the fwms summaries never recorded it.
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

# the project's pinned block-1 seed set (same as every freeway campaign)
SEEDS = (42, 7, 13, 99, 314, 777, 2024, 8)
ARMS = ("open", "rosequarter")
PREFIX = "fwrq"          # base campaign; --realism switches this to "fwrqr"

# The frozen closed span, verified edge-for-edge against the Aug 12 metro-graph
# probe and the Aug 13 dry run: 3 SB mainline edges (1,628 m) plus 2 stranded
# SB ramps, northbound untouched. A task refuses to run if the graph it loads
# selects anything else: a silently different span would invalidate the
# pre-registration, so this fails loudly instead.
EXPECTED_SB = {(40382443, 40397036, 0), (40397036, 40413533, 0),
               (40413533, 3427976322, 0)}
EXPECTED_REMOVED_N = 5

REALISM_FLAGS = dict(mce.ARMS["realism"])
STACK_REALISM = False    # set by --realism in main(), before any dispatch

# routes whose per-edge mainline values are stored per run. I 405 is the signed
# detour (the pre-registered "up"); I 205 the regional detour ("up"); I 5 the
# closed route; the rest are the surface alternates, kept identical to fwms so
# the two campaigns' readouts stay comparable.
TRACK_ROUTES = ("I 5", "I 405", "I 205", "OR 213", "OR 99E", "US 26")


def tasks():
    return [(arm, seed) for arm in ARMS for seed in SEEDS]


def run_name(arm, seed):
    return f"{PREFIX}_{arm}_s{seed}"


def summary_path(arm, seed):
    return os.path.join(config.PROCESSED_DIR, f"{run_name(arm, seed)}_summary.json")


def _load_metro_graph():
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        raise SystemExit(f"no cached graph at {graph_file}; refusing to "
                         f"download mid-experiment")
    G = ox.load_graphml(graph_file)
    # metro guard: a corridor-sized cache here would silently run the wrong
    # experiment under the right file names
    if G.number_of_edges() < 100_000:
        raise SystemExit(f"graph has {G.number_of_edges():,} edges; this is a "
                         f"metro campaign and refuses a corridor-sized graph")
    return G


def _verify_span(G):
    """The frozen-span guard: the spec must select exactly the pre-registered
    edges on this graph. Returns the removed list on success."""
    removed = generate.closed_freeway_edges(G, SCENARIOS["rosequarter"])
    got_sb = {e for e in removed if e in EXPECTED_SB}
    if got_sb != EXPECTED_SB or len(removed) != EXPECTED_REMOVED_N:
        raise SystemExit(
            f"frozen-span mismatch: selected {len(removed)} edges "
            f"({sorted(removed)}), pre-registered {EXPECTED_REMOVED_N} with SB "
            f"mainline {sorted(EXPECTED_SB)}. The graph differs from the one "
            f"the span was verified on; do NOT run, re-verify first.")
    return removed


def check():
    G = _load_metro_graph()
    removed = _verify_span(G)
    print(f"graph: {G.number_of_nodes():,} nodes / {G.number_of_edges():,} edges")
    print(f"frozen span OK: {len(removed)} edges "
          f"({len(EXPECTED_SB)} SB mainline + "
          f"{len(removed) - len(EXPECTED_SB)} stranded ramps)")


def run_task(idx):
    arm, seed = tasks()[idx]
    out = summary_path(arm, seed)
    if os.path.exists(out):
        print(f"task {idx} ({arm}, seed {seed}) already done -> {out}")
        return

    G = _load_metro_graph()

    # the seed is what this experiment varies, so set it before anything draws
    config.RANDOM_SEED = seed
    config.RUN_NAME = run_name(arm, seed)

    # every stack flag EXPLICITLY True or False (the F6 rule): a task must
    # never inherit these from a config default or a reused interpreter
    for k in REALISM_FLAGS:
        setattr(config, k, STACK_REALISM)
    # absolute grams are cited under the mixed fleet (the live setting, gate
    # G2); explicit for the same reason as the stack flags
    config.FLEET_MIXED = True

    removed = []
    if arm != "open":
        removed = _verify_span(G)
        generate.apply_freeway_closure(G, SCENARIOS[arm])
        print(f"[{config.RUN_NAME}] removed {len(removed)} freeway edges")

    generate.set_seeds(seed)
    totals, nox, thru = generate.run_simulation(G, use_checkpoint=False)
    generate.save_results(totals, nox, thru)

    # Compact summary so the readout needs only these files, not the parquets.
    # Per-edge values for the tracked mainlines let the readout do span-level
    # and paired per-segment tests, not just route totals.
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
        "fleet": "mixed",
        "n_vehicles": config.N_VEHICLES, "n_steps": config.N_STEPS,
        "removed": [[u, v, k] for u, v, k in removed],
        "network_nox_g": float(sum(nox.values())),
        "network_throughput": float(sum(thru.values())),
        "routes": routes,
    }
    with open(out, "w") as f:
        json.dump(rec, f)
    print(f"[{config.RUN_NAME}] summary -> {out}")


def _paired(summaries, ref, field):
    """Per-seed paired difference on route `ref`, closed minus open.
    field 0 = NOx grams, 1 = throughput."""
    diffs, rel = [], []
    for seed in SEEDS:
        o = summaries.get(("open", seed))
        c = summaries.get(("rosequarter", seed))
        if not o or not c or ref not in o["routes"] or ref not in c["routes"]:
            continue
        # the closed run is missing the removed edges; treat them as zero so
        # the route total is comparable rather than silently shorter
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
    want = "realism" if STACK_REALISM else "base"
    for (arm, seed), s in summaries.items():
        got = s.get("stack", "base")
        if got != want:
            raise SystemExit(f"{summary_path(arm, seed)} records stack={got} "
                             f"but this readout is for {want}; wrong file")
    have = {a: sum(1 for (arm, _) in summaries if arm == a) for a in ARMS}
    print("stack: " + want)
    print("summaries found: " +
          ", ".join(f"{a} {have[a]}/{len(SEEDS)}" for a in ARMS))
    if min(have.values()) < 2:
        raise SystemExit("need at least 2 paired seeds for a distribution")

    print(f"\n{'=' * 72}\nROSE QUARTER I-5 SB: paired per-seed differences "
          f"(closed - open, same seed)\n{'=' * 72}")
    print(f"{'route':>8s} {'n':>3s} {'mean %':>8s} {'sd %':>7s} "
          f"{'min %':>7s} {'max %':>7s} {'signs':>7s}  verdict")
    for ref in TRACK_ROUTES:
        d, rel = _paired(summaries, ref, 0)
        if len(d) < 2:
            continue
        pos = int((d > 0).sum())
        # the standing campaign bar: unanimous sign AND |t|>3 (with 8 seeds a
        # unanimous sign is p = 2^-8 = 0.004 under a fair-coin null)
        unanimous = pos == len(d) or pos == 0
        t = abs(rel.mean()) / (rel.std(ddof=1) / np.sqrt(len(rel))) \
            if rel.std(ddof=1) > 0 else float("inf")
        verdict = ("SUPPORTED" if unanimous and t > 3
                   else "weak" if unanimous else "NOT SUPPORTED")
        print(f"{ref:>8s} {len(d):3d} {rel.mean():+8.2f} {rel.std(ddof=1):7.2f} "
              f"{rel.min():+7.2f} {rel.max():+7.2f} {pos:3d}/{len(d):<3d} "
              f" {verdict} (t={t:.1f})")


def main():
    global STACK_REALISM, PREFIX
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--list", action="store_true")
    g.add_argument("--count", action="store_true")
    g.add_argument("--task", type=int)
    g.add_argument("--readout", action="store_true")
    ap.add_argument("--realism", action="store_true",
                    help="run/readout the realism-stack secondary arm (fwrqr)")
    args = ap.parse_args()

    if args.realism:
        STACK_REALISM = True
        PREFIX = "fwrqr"

    if args.check:
        check()
    elif args.list:
        for i, (arm, seed) in enumerate(tasks()):
            print(f"{i:3d}  {arm:>12s}  seed {seed}")
    elif args.count:
        print(len(tasks()))
    elif args.task is not None:
        run_task(args.task)
    else:
        readout()


if __name__ == "__main__":
    main()
