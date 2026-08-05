"""Demand-magnitude (N vehicles) sensitivity sweep at metro scale.

Every metro number this project cites rests on a demand of 16,500 vehicles per
simulated hour, an UNTUNED a-priori level (scaled up from the corridor's
AADT-derived 240 by window area when the metro graph was first cut, and never
tested since). After the patience sweep (ledger section 18) and the
through-share sweep (section 20), it is the last unsourced constant a reviewer
can point at under the count-agreement and closure results: "why 16,500, and
does your answer survive a different guess?".

This sweep answers it under the same discipline as the other two.

WHAT IS SWEPT

Only the demand level. The sweep values are fixed multipliers of the a-priori
16,500, declared here before any result existed: 0.5x (8,250), 0.75x (12,375),
1.25x (20,625), and 1.5x (24,750). The span brackets halving and half-again,
which covers every demand anyone could reasonably argue for from the ODOT
AADT conversion. Demand is a per-job parameter (n_veh), not an ARMS key, so
unlike the through sweep no arm registration is needed and the complement-off
trap in run_one cannot arise: every task runs the plain realism arm, and the
through share stays at the METRO default of 0.15 throughout.

THE MEASURE

Busiest-Powell throughput against the real ODOT peak-hour band, 1,400-1,745
veh/hr (ledger L5), the same yardstick as the ablation (section 12), the
patience sweep (section 18), and the through sweep (section 20), so all four
are directly comparable. run_one computes it into each run's summary JSON, so
the readout needs only the summaries.

WHAT A RESULT WOULD MEAN

Throughput obviously rises with demand; that is not the question. The question
is whether the in-band agreement at 16,500 is a knife-edge (a small demand
change leaves the band, so the a-priori guess was load-bearing) or a plateau
(capacity limits throughput, so conclusions are robust to the guess). Either
answer is honest; neither changes the cited value.

THE CITATION RULE, WRITTEN DOWN BEFORE THE RESULTS EXIST

16,500 STAYS the cited value whatever this sweep returns. The ODOT band is
validation data, so picking the demand that best hits the band would tune a
parameter against the very target the model is judged on. Sensitivity check
on an a-priori choice, never grounds to change it. Identical discipline to
the patience sweep, the through sweep, and the gravity decay scale.

THE 16,500 POINT IS JOINED FROM DISK, NOT RE-RUN: the existing
metrocal_realism_n16500_s* runs ARE that point, and --check refuses to
proceed unless config still agrees.

Usage:
    python src/metro_demand_sweep.py --check    # prerequisites, before submitting
    python src/metro_demand_sweep.py --count    # SLURM array size
    python src/metro_demand_sweep.py --list     # task id -> run name
    python src/metro_demand_sweep.py --task N   # run one job
    python src/metro_demand_sweep.py --readout  # band vs demand level
"""
import argparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import config
import metro_calibrated_experiment as mce

# The a-priori metro demand, and the pre-registered sweep around it.
BASELINE_N = 16500
MULTIPLIERS = [0.5, 0.75, 1.25, 1.5]
NEW_N = [int(round(BASELINE_N * m)) for m in MULTIPLIERS]
LEVELS = sorted(NEW_N + [BASELINE_N])

SEEDS = list(mce.SEEDS)     # the same 8 pinned seeds every metro experiment uses

# real ODOT peak-hour directional band for Powell (ledger L5). The yardstick,
# never a fitting target -- see the citation rule in the docstring.
BAND = (1400.0, 1745.0)

# where the already-run 16,500 point lives: the realism arm of the metrocal runs
HOUR_BASELINE = "metrocal_realism"


def hour_stem(n, seed):
    if n == BASELINE_N:
        return f"{HOUR_BASELINE}_n{BASELINE_N}_s{seed}"
    return f"dmsw_hour_n{n}_s{seed}"


def build_jobs():
    """Hour-job list; index == SLURM array task id. 4 new levels x 8 seeds.
    Plain realism arm for every task: demand travels as n_veh, not as an arm
    key, so no ARMS mutation happens anywhere in this module."""
    return [{"arm": "realism", "seed": seed, "n_veh": n,
             "steps": mce.METRO["N_STEPS"], "name": hour_stem(n, seed)}
            for n in NEW_N for seed in SEEDS]


def _summary(stem):
    """Load one run's summary JSON, or None if it is not on disk."""
    path = os.path.join(config.PROCESSED_DIR, f"{stem}_summary.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


def check():
    """Verify every prerequisite BEFORE cluster time is spent."""
    ok = True
    for k, v in mce.METRO.items():
        setattr(config, k, v)

    # THE LOAD-BEARING CHECK. The 16,500 point is joined from disk rather than
    # re-run, which is only valid while the metrocal runs are still what a
    # 16,500 run would produce today: same through share, same realism arm.
    if abs(mce.METRO["THROUGH_TRAFFIC_FRACTION"] - 0.15) < 1e-12:
        print(f"  ok       METRO THROUGH_TRAFFIC_FRACTION is 0.15, matching "
              f"what the {HOUR_BASELINE} runs used")
    else:
        print(f"  REFUSE   METRO THROUGH_TRAFFIC_FRACTION is "
              f"{mce.METRO['THROUGH_TRAFFIC_FRACTION']}, not the 0.15 the "
              f"{HOUR_BASELINE} runs used; the joined baseline would be a "
              f"mislabelled point mid-curve")
        ok = False

    graph = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if os.path.exists(graph):
        size_mb = os.path.getsize(graph) / 1e6
        print(f"  ok       graph: {graph} ({size_mb:.0f} MB)")
        if size_mb < 10:
            print(f"  REFUSE   that is corridor-sized, not the metro graph")
            ok = False
    else:
        print(f"  MISSING  graph at {graph}")
        ok = False

    # the joined-from-disk baseline
    stems = [hour_stem(BASELINE_N, s) for s in SEEDS]
    have = sum(1 for st in stems if _summary(st))
    good = have == len(stems)
    print(f"  {'ok      ' if good else 'MISSING '} {BASELINE_N} baseline runs: "
          f"{have}/{len(stems)} on disk")
    ok &= good

    print(f"\n{'READY' if ok else 'NOT READY'}: {len(build_jobs())} hour jobs; "
          f"levels {NEW_N} new, {BASELINE_N} joined")
    return ok


def readout():
    """Busiest-Powell band membership versus demand, for what is on disk."""
    print(f"Demand-magnitude sweep, realism stack, through share 0.15\n")
    print(f"busiest Powell veh/hr vs the real ODOT band "
          f"{BAND[0]:,.0f}-{BAND[1]:,.0f}\n")
    print(f"{'demand':>7}  {'busiest Powell':>20}  {'in band':>8}  "
          f"{'network stuck veh-h':>20}  {'runs':>5}")

    base = {}
    for n in LEVELS:
        vals, stuck, n_band, got = [], [], 0, 0
        for seed in SEEDS:
            s = _summary(hour_stem(n, seed))
            if not s:
                continue
            got += 1
            v = float(s["busiest_powell_veh_hr"])
            vals.append(v)
            stuck.append(float(s["network_stuck_veh_h"]))
            if BAND[0] <= v <= BAND[1]:
                n_band += 1
            if n == BASELINE_N:
                base[seed] = v
        if not vals:
            print(f"{n:>7,}  {'(no runs on disk)':>20}")
            continue
        a = np.array(vals)
        mark = " IN BAND" if BAND[0] <= a.mean() <= BAND[1] else ""
        print(f"{n:>7,}  {a.mean():>10,.0f} +/- {a.std(ddof=1) if len(a) > 1 else 0:<6,.0f}"
              f"  {n_band:>3}/{got:<4}  {np.mean(stuck):>20,.0f}  {got:>5}"
              f"{mark}")

    # paired deltas against the a-priori point, seed by seed
    if base:
        print(f"\npaired vs the a-priori {BASELINE_N:,} (same seed):")
        for n in LEVELS:
            if n == BASELINE_N:
                continue
            d = [float(s["busiest_powell_veh_hr"]) - base[seed]
                 for seed in SEEDS
                 if (s := _summary(hour_stem(n, seed))) and seed in base]
            if d:
                d = np.array(d)
                print(f"  {n:>7,}: {d.mean():>+8,.0f} +/- "
                      f"{d.std(ddof=1) if len(d) > 1 else 0:,.0f} veh/hr  "
                      f"(n={len(d)})")

    print(f"\nCITATION RULE: {BASELINE_N:,} stays the cited value whatever "
          f"this shows. The band is validation data; choosing the demand that "
          f"best hits it would tune a parameter against the target the model "
          f"is judged on. Sensitivity check only.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--task", type=int)
    ap.add_argument("--readout", action="store_true")
    args = ap.parse_args()

    jobs = build_jobs()

    if args.count:
        print(len(jobs))
        return
    if args.list:
        for i, j in enumerate(jobs):
            print(f"{i:3d}  n={j['n_veh']:<6} seed {j['seed']:<6} {j['name']}")
        return
    if args.check:
        raise SystemExit(0 if check() else 1)
    if args.readout:
        readout()
        return
    if args.task is not None:
        graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
        if not os.path.exists(graph_file):
            raise SystemExit(f"no cached graph at {graph_file}; refusing to "
                             f"download mid-experiment")
        mce.run_one(jobs[args.task], graph_file, checkpoint=False)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
