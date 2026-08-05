"""Freeway closures at peak and quiet demand: does congestion amplify the
redistribution?

Every closure campaign so far (fwms, fwmsr, sections 13/15/19) runs one
steady-state hour at the flat average demand of 16,500 vehicles. The day work
(D2) showed the interaction effect directly: a car at the 08:00 peak emits
about a third more NO2 than at the 01:00 quiet hour purely from queueing. This
campaign asks the closure-shaped version of that question: is the same closure
WORSE at peak than at quiet, beyond what the demand ratio alone predicts? A
super-proportional answer is exactly the kind of interaction effect a static
reassignment cannot produce, and it feeds the journal paper's
congestion-amplification thread (Nik's Aug 5 question about what drives the
net increase points the same direction).

PRE-REGISTERED DESIGN, fixed before any result exists:
- Hours: PEAK_HOUR = 8 and QUIET_HOUR = 1, the same two hours D2 already uses,
  chosen there before this campaign existed. Demand for a level is the day
  machinery's own formula (run_day_experiment): n = round(16500 * profile[h] *
  24) with the PORTAL-derived hourly profile, so a level here reproduces the
  corresponding hour of the day experiment exactly.
- Seeds: SEEDS_BLOCK1 only (8 seeds), the same first block as sections 13/15.
  Extension to block 2 is append-only later if the intervals need it.
- Arms: the same three (open, abernethy, powell) and the same closure specs.
- Bar: per level, the same unanimity AND |t| > 3 rule as every freeway
  readout.
- Citation rule: the flat-demand fwmsr campaign (section 19) stays the
  headline closure result. This campaign is cited only for the peak-vs-quiet
  CONTRAST, and grams lead, because quiet-hour baselines are small and
  percentages on them mislead.

Files: fwpq_{level}_{arm}_s{seed}. The realism stack is ON for every task
(the fwmsr precedent). One simulated hour per task.

Usage:
    python src/freeway_peak_quiet.py --check
    python src/freeway_peak_quiet.py --count
    python src/freeway_peak_quiet.py --list
    python src/freeway_peak_quiet.py --task N
    python src/freeway_peak_quiet.py --readout
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
import demand_data     # noqa: E402
import freeway_multiseed as fwm  # noqa: E402  (seeds, arms, routes, _paired)
from freeway_runs import SCENARIOS  # noqa: E402

PREFIX = "fwpq"
LEVELS = {"peak": 8, "quiet": 1}   # hour of day; see the pre-registration note
SEEDS = fwm.SEEDS_BLOCK1
ARMS = fwm.ARMS


def level_demand(level):
    """The day machinery's own demand for that hour, computed from the same
    PORTAL profile the day experiment uses, so a level here matches the
    corresponding hour of run_day_experiment exactly."""
    profile = demand_data.hourly_demand_profile()
    h = LEVELS[level]
    return max(1, round(config.N_VEHICLES * profile[h] * 24))


def tasks():
    return [(level, arm, seed) for level in LEVELS
            for arm in ARMS for seed in SEEDS]


def run_name(level, arm, seed):
    return f"{PREFIX}_{level}_{arm}_s{seed}"


def summary_path(level, arm, seed):
    return os.path.join(config.PROCESSED_DIR,
                        f"{run_name(level, arm, seed)}_summary.json")


def run_task(idx):
    level, arm, seed = tasks()[idx]
    out = summary_path(level, arm, seed)
    if os.path.exists(out):
        print(f"task {idx} ({level}, {arm}, seed {seed}) already done -> {out}")
        return

    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        raise SystemExit(f"no cached graph at {graph_file}; refusing to "
                         f"download mid-experiment")
    G = ox.load_graphml(graph_file)

    n_veh = level_demand(level)
    config.RANDOM_SEED = seed
    config.RUN_NAME = run_name(level, arm, seed)

    # realism stack ON for every task, set explicitly flag by flag, the same
    # rule as fwm.run_task: a task never inherits stack state
    for k in fwm.REALISM_FLAGS:
        setattr(config, k, True)

    removed = []
    if arm != "open":
        removed = generate.apply_freeway_closure(G, SCENARIOS[arm])
        print(f"[{config.RUN_NAME}] removed {len(removed)} freeway edges")

    generate.set_seeds(seed)
    totals, nox, thru = generate.run_simulation(G, n_vehicles=n_veh,
                                                use_checkpoint=False)
    generate.save_results(totals, nox, thru)

    routes = {}
    for ref in fwm.TRACK_ROUTES:
        keys = generate.freeway_mainline_edges(G, ref)
        if not keys:
            continue
        routes[ref] = {f"{u}_{v}_{k}": [float(nox.get((u, v, k), 0.0)),
                                        float(thru.get((u, v, k), 0.0))]
                       for u, v, k in keys}
    rec = {
        "arm": arm, "seed": seed, "level": level, "hour": LEVELS[level],
        "stack": "realism",
        "n_vehicles": n_veh, "n_steps": config.N_STEPS,
        "removed": [[u, v, k] for u, v, k in removed],
        "network_nox_g": float(sum(nox.values())),
        "network_throughput": float(sum(thru.values())),
        "routes": routes,
    }
    with open(out, "w") as f:
        json.dump(rec, f)
    print(f"[{config.RUN_NAME}] summary -> {out}")


def _load_level(level):
    """Summaries for one level, keyed (arm, seed) the way fwm._paired wants."""
    summaries = {}
    for lv, arm, seed in tasks():
        if lv != level:
            continue
        p = summary_path(level, arm, seed)
        if not os.path.exists(p):
            continue
        with open(p) as f:
            rec = json.load(f)
        # a summary written by anything else must never mix in
        if rec.get("stack") != "realism" or rec.get("level") != level:
            raise SystemExit(f"{p} records stack={rec.get('stack')} "
                             f"level={rec.get('level')}; wrong file")
        summaries[(arm, seed)] = rec
    return summaries


def check():
    ok = True
    for level in LEVELS:
        n = level_demand(level)
        print(f"  ok       {level}: hour {LEVELS[level]}, demand {n:,}")
    graph = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if os.path.exists(graph) and os.path.getsize(graph) / 1e6 > 10:
        print(f"  ok       metro graph present")
    else:
        print(f"  MISSING  metro graph at {graph}")
        ok = False
    # hourly_demand_profile falls back to a synthetic shape silently, which
    # is the documented failure mode for profiled runs: refuse unless the
    # real PORTAL csv is what the profile would actually use. demand_data
    # owns the path (the C1 harness learned this same lesson at 64d70a4).
    if demand_data.is_using_real_data():
        print(f"  ok       PORTAL profile is the real csv, not synthetic")
    else:
        print(f"  REFUSE   demand profile would fall back to synthetic")
        ok = False
    print(f"\n{'READY' if ok else 'NOT READY'}: {len(tasks())} hour jobs")
    return ok


def readout():
    f_no2 = config.F_NO2
    for level in LEVELS:
        summaries = _load_level(level)
        have = {a: sum(1 for (arm, _) in summaries if arm == a) for a in ARMS}
        print(f"\n{'=' * 72}\n{level.upper()} (hour {LEVELS[level]}, demand "
              f"{level_demand(level):,}): paired per-seed differences, "
              + ", ".join(f"{a} {have[a]}/{len(SEEDS)}" for a in ARMS)
              + f"\n{'=' * 72}")
        if have.get("open", 0) < 2:
            print("  not enough paired seeds yet")
            continue
        print(f"{'route':>8s} {'arm':>10s} {'n':>3s} {'mean %':>8s} "
              f"{'sd %':>7s} {'signs':>7s}  verdict")
        for arm in ("abernethy", "powell"):
            for ref in fwm.TRACK_ROUTES:
                d, rel = fwm._paired(summaries, arm, ref, 0)
                if len(d) < 2:
                    continue
                pos = int((d > 0).sum())
                unanimous = pos == len(d) or pos == 0
                t = abs(rel.mean()) / (rel.std(ddof=1) / np.sqrt(len(rel))) \
                    if rel.std(ddof=1) > 0 else float("inf")
                verdict = ("SUPPORTED" if unanimous and t > 3
                           else "weak" if unanimous else "NOT SUPPORTED")
                print(f"{ref:>8s} {arm:>10s} {len(d):3d} {rel.mean():+8.2f} "
                      f"{rel.std(ddof=1):7.2f} {pos:3d}/{len(d):<3d} "
                      f" {verdict} (t={t:.1f})")
            d, _ = fwm._paired(summaries, arm, "I 5", 0)
            if len(d):
                print(f"  {arm}: I-5 mainline NO2 shift "
                      f"{f_no2 * d.mean():+.1f} g/run (sd "
                      f"{f_no2 * d.std(ddof=1):.1f}, n={len(d)})")
    print(f"\nCITATION RULE: the flat-demand fwmsr campaign (ledger section "
          f"19) stays the headline. This campaign is cited only for the "
          f"peak-vs-quiet contrast, grams first.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--task", type=int)
    ap.add_argument("--readout", action="store_true")
    args = ap.parse_args()

    if args.count:
        print(len(tasks()))
        return
    if args.list:
        for i, (level, arm, seed) in enumerate(tasks()):
            print(f"{i:3d}  {level:6s} {arm:10s} seed {seed:<6} "
                  f"{run_name(level, arm, seed)}")
        return
    if args.check:
        raise SystemExit(0 if check() else 1)
    if args.readout:
        readout()
        return
    if args.task is not None:
        run_task(args.task)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
