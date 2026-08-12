"""Paired multi-seed campaigns for the two routing levers (pre-registered Aug 11).

The freeway campaign's I-5 diversion null survived n=16 (ledger section 19), a
realism-stack rerun (F6), and en-route replanning (section 22, fwrr). The
composition diagnostic then showed WHY: seed 42 carries 229 through trips over
the Abernethy span whose full diversion would move ~+20% of I-5's route total,
far above the ~4-5% detection floor -- so the null is a missing corridor-choice
mechanism, not a missing population. Two candidate mechanisms, each behind its
own config flag, are tested here as SEPARATE campaigns so any movement can be
attributed to one lever:

  lever A (config.THROUGH_CORRIDOR_CHOICE): closure-aware corridor choice.
      A through trip samples 5 candidate entry nodes (dedicated RNG stream,
      seed+4) and enters at the one with the cheapest path cost to its exit on
      the actual graph, identically in open and closed arms.
  lever B (config.ROUTE_ITERATED_ASSIGNMENT): congestion-aware initial routing.
      One iterated-assignment pass: pass 1 is today's model and measures
      realized per-edge times (floored at free-flow); pass 2 re-routes the same
      seeded population on them and is the reported run. Each arm runs its own
      pass 1, so a closed arm's weights carry the closed network's congestion.
      Roughly DOUBLES per-task runtime (two full simulations).

Pre-registration, written before any result exists:
  - Candidate count 5 and one assignment iteration are fixed a priori.
  - Arms open/abernethy/powell, the block-1 seed set, base realism stack (all
    stack flags explicitly False), C1 en-route rerouting OFF (this branch forks
    from main, which has no C1 code).
  - Verdict bar identical to the freeway campaign: unanimous sign across the 8
    paired seeds AND |t| > 3.
  - The result is reported whatever it shows, including still-null, and no
    parameter is tuned until I-5 moves. The headline closure numbers remain the
    base campaign's (ledger section 19) regardless of the outcome here.

One task per SLURM array index, each writing its own uniquely named files
(one-writer rule); finished tasks skip on their summary, so resubmitting after
a partial failure is safe.

    python src/freeway_corridor_levers.py --check              # inputs sanity
    python src/freeway_corridor_levers.py --lever A --list     # task table
    python src/freeway_corridor_levers.py --lever A --task 7   # run one task
    python src/freeway_corridor_levers.py --lever A --readout  # paired verdicts
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
import metro_calibrated_experiment as mce  # noqa: E402  (the realism-flag names)

# Block-1 seeds only (the campaign design pre-registered Aug 11): 3 arms x 8
# seeds = 24 tasks per lever. Same pinned set as the freeway campaign so the
# paired differences are comparable run for run.
SEEDS = (42, 7, 13, 99, 314, 777, 2024, 8)
ARMS = ("open", "abernethy", "powell")

# Which config flag each lever sets; every task sets BOTH explicitly (one True
# at most), so a task can never inherit a lever from a stale interpreter.
LEVER_FLAGS = {
    "A": "THROUGH_CORRIDOR_CHOICE",
    "B": "ROUTE_ITERATED_ASSIGNMENT",
}
PREFIX = {"A": "fwla", "B": "fwlb"}

# The realism-stack flag names, referenced from metro_calibrated_experiment so
# this campaign can never drift from the others. All set explicitly False: the
# base stack is what the section-19 headline and the fwrr rerouting campaign
# ran, so a lever's effect is attributable to the lever alone.
REALISM_FLAGS = tuple(mce.ARMS["realism"])

# Routes tracked per run: I-5 is the diversion hypothesis, I-205 the closed
# route (sanity: it must drop), the rest the surface alternates.
TRACK_ROUTES = ("I 5", "I 205", "OR 213", "OR 99E", "US 26")


def tasks():
    return [(arm, seed) for arm in ARMS for seed in SEEDS]


def run_name(lever, arm, seed):
    return f"{PREFIX[lever]}_{arm}_s{seed}"


def summary_path(lever, arm, seed):
    return os.path.join(config.PROCESSED_DIR,
                        f"{run_name(lever, arm, seed)}_summary.json")


def run_task(lever, idx):
    arm, seed = tasks()[idx]
    out = summary_path(lever, arm, seed)
    if os.path.exists(out):
        print(f"task {idx} (lever {lever}, {arm}, seed {seed}) already done -> {out}")
        return

    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        raise SystemExit(f"no cached graph at {graph_file}; refusing to "
                         f"download mid-experiment")
    G = ox.load_graphml(graph_file)

    # the seed is what this campaign varies; set it before anything draws
    config.RANDOM_SEED = seed
    config.RUN_NAME = run_name(lever, arm, seed)

    # every stack flag explicitly False (base model), every lever flag explicit
    for k in REALISM_FLAGS:
        setattr(config, k, False)
    for lv, flag in LEVER_FLAGS.items():
        setattr(config, flag, lv == lever)

    removed = []
    if arm != "open":
        removed = generate.apply_freeway_closure(G, SCENARIOS[arm])
        print(f"[{config.RUN_NAME}] removed {len(removed)} freeway edges")

    generate.set_seeds(seed)
    totals, nox, thru = generate.run_simulation(G, use_checkpoint=False)
    generate.save_results(totals, nox, thru)

    # Compact summary: per-edge values for the tracked mainlines, so the readout
    # can run without the parquets (same shape as the freeway campaign's).
    routes = {}
    for ref in TRACK_ROUTES:
        keys = generate.freeway_mainline_edges(G, ref)
        if not keys:
            continue
        routes[ref] = {f"{u}_{v}_{k}": [float(nox.get((u, v, k), 0.0)),
                                        float(thru.get((u, v, k), 0.0))]
                       for u, v, k in keys}
    rec = {
        "lever": lever, "arm": arm, "seed": seed, "stack": "base",
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
    field 0 = NOx grams, 1 = throughput. Removed edges are read as zero in the
    closed run so the route total stays comparable rather than silently shorter."""
    diffs, rel = [], []
    for seed in SEEDS:
        o = summaries.get(("open", seed))
        c = summaries.get((arm, seed))
        if not o or not c or ref not in o["routes"] or ref not in c["routes"]:
            continue
        ko = o["routes"][ref]
        kc = c["routes"][ref]
        so = sum(v[field] for v in ko.values())
        sc = sum(kc.get(key, [0.0, 0.0])[field] for key in ko)
        diffs.append(sc - so)
        rel.append(100.0 * (sc - so) / so if so else float("nan"))
    return np.array(diffs), np.array(rel)


def readout(lever):
    summaries = {}
    for arm, seed in tasks():
        p = summary_path(lever, arm, seed)
        if os.path.exists(p):
            with open(p) as f:
                summaries[(arm, seed)] = json.load(f)
    # a summary from another campaign mixed in under this prefix would corrupt
    # the pairing silently; the recorded lever field makes that fatal instead
    for (arm, seed), s in summaries.items():
        if s.get("lever") != lever:
            raise SystemExit(f"{summary_path(lever, arm, seed)} records "
                             f"lever={s.get('lever')} but this readout is for "
                             f"lever {lever}; wrong file")
    have = {a: sum(1 for (arm, _) in summaries if arm == a) for a in ARMS}
    print(f"lever {lever} ({LEVER_FLAGS[lever]}), base stack")
    print("summaries found: " +
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
            # the pre-registered bar, identical to the freeway campaign: every
            # seed agrees in sign (p = 2^-8 = 0.004 under a fair coin) AND the
            # mean sits >3 standard errors from zero
            unanimous = pos == len(d) or pos == 0
            t = abs(rel.mean()) / (rel.std(ddof=1) / np.sqrt(len(rel))) \
                if rel.std(ddof=1) > 0 else float("inf")
            verdict = ("SUPPORTED" if unanimous and t > 3
                       else "weak" if unanimous else "NOT SUPPORTED")
            print(f"{ref:>8s} {len(d):3d} {rel.mean():+8.2f} {rel.std(ddof=1):7.2f} "
                  f"{rel.min():+7.2f} {rel.max():+7.2f} {pos:3d}/{len(d):<3d} "
                  f" {verdict} (t={t:.1f})")
        d, _ = _paired(summaries, arm, "I 5", 0)
        if len(d):
            print(f"\n  I-5 mainline NO2 shift: "
                  f"{f_no2 * d.mean():+.1f} g/run (sd {f_no2 * d.std(ddof=1):.1f}, "
                  f"n={len(d)} seeds)")


def check():
    """Verify the inputs a task will need, without running anything."""
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        raise SystemExit(f"MISSING graph cache: {graph_file}")
    G = ox.load_graphml(graph_file)
    print(f"graph: {G.number_of_nodes():,} nodes / {G.number_of_edges():,} edges")
    generate.prepare_network(G)
    bad = 0
    for scen, spec in SCENARIOS.items():
        try:
            edges = generate.closed_freeway_edges(G, spec)
        except ValueError as e:   # e.g. no motorway edges on the cached graph
            print(f"closure '{scen}': FAILED ({e})  <-- wrong graph?")
            bad += 1
            continue
        print(f"closure '{scen}': {len(edges)} edges"
              + ("" if edges else "  <-- EMPTY, wrong graph?"))
        bad += 0 if edges else 1
    for ref in TRACK_ROUTES:
        n = len(generate.freeway_mainline_edges(G, ref))
        print(f"tracked route '{ref}': {n} mainline edges"
              + ("" if n else "  <-- EMPTY"))
        bad += 0 if n else 1
    for lv, flag in LEVER_FLAGS.items():
        assert hasattr(config, flag), f"config.{flag} missing"
        print(f"lever {lv}: config.{flag} present (default {getattr(config, flag)})")
    print(f"tasks per lever: {len(tasks())} ({len(ARMS)} arms x {len(SEEDS)} seeds)")
    if bad:
        raise SystemExit(f"check FAILED: {bad} closure/route lookups came up empty "
                         f"(is this the metro graph?)")
    print("check OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lever", choices=("A", "B"))
    ap.add_argument("--task", type=int)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--readout", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if args.check:
        check()
        return
    if args.count:
        print(len(tasks()))
        return
    if not args.lever:
        ap.error("--lever A|B is required for --task/--list/--readout")
    if args.list:
        for i, (arm, seed) in enumerate(tasks()):
            done = "done" if os.path.exists(summary_path(args.lever, arm, seed)) \
                else ""
            print(f"{i:3d}  {arm:10s} seed {seed:<5d} {done}")
    elif args.readout:
        readout(args.lever)
    elif args.task is not None:
        run_task(args.lever, args.task)
    else:
        ap.error("give one of --task/--list/--count/--readout/--check")


if __name__ == "__main__":
    main()
