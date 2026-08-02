"""C1 experiment: does en-route rerouting clear the day-scale freeze?

THE QUESTION, from DEMAND_EXIT_PLAN.md. Phase A2 found every 24-hour metro arm
ends in gridlock, with the profiled arms frozen at exact integers (9,591 and
13,455 stuck vehicle-hours) against an hour-23 quota of 2,876 -- because a
vehicle can leave this network only by REACHING its destination, so when
completions stop, nothing leaves. C1 gives the PATH a way to change without
removing any vehicle. Two outcomes, both publishable:

  - the freeze CLEARS  -> A2's gridlock was an artifact of routes planned once
    at spawn against free-flow times and never revised.
  - the freeze PERSISTS -> true spillback deadlock, where every alternative is
    itself blocked. That is the stronger claim, and it is what would motivate
    C2 (trip abandonment), which is deliberately unbuilt until this run decides.

TWO SUB-EXPERIMENTS, deliberately separate arrays because their SLURM shapes
differ by an order of magnitude:

  DAY (the actual question, `--day-task`, orca/job_c1_day.sh): the A2 PROFILED
    pair re-run with rerouting on, 2 jobs x 86,400 steps. Paired against the
    existing metrocal_dayprof_* controls from array 117428 -- same graph,
    demand, seed and steps, rerouting off -- joined from disk rather than
    re-run. That reuse is legitimate ONLY because C1 is proved bitwise inert
    when off (reroute_scenarios A + kernel_regression); if that ever breaks,
    the controls must be re-run.

  HOUR (the regression check, `--task`, orca/job_c1_hour.sh): 2 arms x the 8
    pinned seeds at one simulated hour. A day result is uninterpretable if C1
    wrecks the peak-hour band on the way, so this asks whether busiest-Powell
    stays in the real ODOT 1,400-1,745 band. Controls are the Jul 29
    metrocal_{base,realism}_n16500_s* runs, also joined from disk.

WHY BOTH A BASE AND A REALISM ARM: the A2 freeze happened in BOTH, and the
crossover finding (realism better in the morning, worse at night) means they
fail differently. Testing C1 on only one would leave open whether any relief
is C1 or the stack it sits on.

DISCIPLINE (CLAUDE.md): reuses metro_calibrated_experiment.run_one unchanged
(unique RUN_NAME per job, per-job seed, one writer per file, SKIP on existing
parquet, metro graph guard). C1's own arms are registered into mce.ARMS so
run_one's complement-off loop sees REROUTE_ENABLED and no task can inherit the
previous one's setting. Every parameter a-priori; nothing tuned to the held-out
PBOT counts or the ODOT band.

READ ANY RESULT WITH THESE TWO BOUNDS (DEMAND_EXIT_PLAN.md status block):
  - a car already committed to the blocked link cannot divert (no U-turn), so
    relief is bounded by how many cars are still upstream of a fork;
  - every driver re-plans on perfect instantaneous network-wide occupancy, the
    optimistic end of the information spectrum, so C1 measures an UPPER BOUND.
  - REROUTE_STUCK_S = 120 s is the softest constant in the phase and deserves a
    sensitivity sweep before any number is cited.

Usage:
    python src/metro_c1_experiment.py --check      # prerequisites, before submitting
    python src/metro_c1_experiment.py --count      # hour-job count (SLURM array size)
    python src/metro_c1_experiment.py --count-day  # day-job count
    python src/metro_c1_experiment.py --task N     # run one hour job
    python src/metro_c1_experiment.py --day-task N # run one day job
    python src/metro_c1_experiment.py --readout    # analyze what is on disk
"""
import argparse
import glob
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import config
import metro_calibrated_experiment as mce

# the full realism stack, referenced not retyped so it cannot drift from the
# metrocal/ablation/b13 definition of the same arm
REALISM = dict(mce.ARMS["realism"])
C1_FLAG = "REROUTE_ENABLED"

# C1 on top of each A2 arm. Registered with the shared runner so run_one's arm
# lookup AND its complement-off loop both see the flag.
C1_ARMS = {
    "base_reroute": {C1_FLAG: True},
    "realism_reroute": dict(REALISM, **{C1_FLAG: True}),
}
mce.ARMS.update(C1_ARMS)

# the control each arm is paired against, by RUN_NAME stem (all already on disk)
DAY_CONTROL = {"base_reroute": "metrocal_dayprof_base",
               "realism_reroute": "metrocal_dayprof_realism"}
HOUR_CONTROL = {"base_reroute": "metrocal_base",
                "realism_reroute": "metrocal_realism"}

DEMAND = 16500          # the untuned a-priori level, same as A2 and B1xB3
SEEDS = mce.SEEDS       # the 8 pinned seeds
DAY_SEED = mce.DAY_SEED  # A2 ran one seed; a PAIRED comparison must use it
BAND = (1400, 1745)     # the real ODOT peak-hour band


def build_day_jobs():
    """Day-job list; index == SLURM array task id. 2 arms x 1 seed."""
    return [{"arm": arm, "seed": DAY_SEED, "n_veh": DEMAND,
             "steps": mce.DAY_STEPS, "profile": True, "by_hour": "segments",
             "name": f"c1_dayprof_{arm}_n{DEMAND}_s{DAY_SEED}"}
            for arm in C1_ARMS]


def build_jobs():
    """Hour-job list; index == SLURM array task id. 2 arms x 8 seeds = 16."""
    return [{"arm": arm, "seed": seed, "n_veh": DEMAND,
             "steps": mce.METRO["N_STEPS"],
             "name": f"c1_hour_{arm}_n{DEMAND}_s{seed}"}
            for seed in SEEDS for arm in C1_ARMS]


def _summary(stem):
    p = os.path.join(config.PROCESSED_DIR, f"{stem}_summary.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def check():
    """Verify every prerequisite BEFORE cluster time is spent."""
    ok = True
    for k, v in mce.METRO.items():
        setattr(config, k, v)

    graph = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if os.path.exists(graph):
        mb = os.path.getsize(graph) / 1e6
        print(f"  ok       graph: {graph} ({mb:.0f} MB)")
    else:
        print(f"  MISSING  graph at {graph}")
        ok = False

    # the profiled day arms need the real PORTAL curve; without it they fall
    # back to a synthetic shape, which would silently not be the A2 comparison.
    # Ask demand_data for the path it will actually read rather than rebuilding
    # it here, so this check cannot drift from the loader it is checking.
    import demand_data
    portal = os.path.abspath(demand_data._DEFAULT_CSV)
    if os.path.exists(portal):
        print(f"  ok       PORTAL hourly curve: {portal}")
    else:
        print(f"  MISSING  {portal} -- the profiled arms would fall back to a "
              f"synthetic hourly shape and NOT be comparable to A2")
        ok = False

    for arm, stem in DAY_CONTROL.items():
        s = _summary(f"{stem}_n{DEMAND}_s{DAY_SEED}")
        if s and "network_stuck_veh_h_by_hour" in s:
            print(f"  ok       day control {stem}: hourly array present")
        else:
            print(f"  MISSING  day control {stem} (A2 array 117428 output)")
            ok = False

    n_hour = sum(1 for stem in HOUR_CONTROL.values()
                 for s in SEEDS if _summary(f"{stem}_n{DEMAND}_s{s}"))
    want = len(HOUR_CONTROL) * len(SEEDS)
    print(f"  {'ok      ' if n_hour == want else 'MISSING '} hour controls: "
          f"{n_hour}/{want} metrocal summaries on disk")
    ok &= n_hour == want

    print(f"\n{'READY' if ok else 'NOT READY'}: {len(build_jobs())} hour jobs, "
          f"{len(build_day_jobs())} day jobs at n={DEMAND}")
    return ok


def readout():
    """Paired C1-vs-control, for whatever is on disk."""
    print(f"C1 (en-route rerouting) vs control, n={DEMAND}\n")

    print("DAY (the A2 question): network stuck veh-h, profiled demand")
    print(f"{'arm':18} {'control':>12} {'C1':>12} {'delta':>12} "
          f"{'h23 ctrl':>10} {'h23 C1':>10}")
    any_day = False
    for arm in C1_ARMS:
        c = _summary(f"{DAY_CONTROL[arm]}_n{DEMAND}_s{DAY_SEED}")
        r = _summary(f"c1_dayprof_{arm}_n{DEMAND}_s{DAY_SEED}")
        if not c or not r:
            print(f"{arm:18} {'--':>12} {'(not on disk yet)':>25}")
            continue
        any_day = True
        cs, rs = c["network_stuck_veh_h"], r["network_stuck_veh_h"]
        ch = c["network_stuck_veh_h_by_hour"][23]
        rh = r["network_stuck_veh_h_by_hour"][23]
        print(f"{arm:18} {cs:12.0f} {rs:12.0f} {rs - cs:+12.0f} "
              f"{ch:10.0f} {rh:10.0f}")
    if any_day:
        print("\n  Read hour 23 against the PORTAL quota of 2,876 active "
              "vehicles:\n  the A2 freeze was 9,591 (base) and 13,455 "
              "(realism) held at exact\n  integers. A cleared freeze means h23 "
              "falls toward that quota, NOT\n  merely that the whole-day total "
              "moved.")

    print(f"\nHOUR (band regression): busiest Powell veh/hr, real band "
          f"{BAND[0]:,}-{BAND[1]:,}")
    print(f"{'arm':18} {'n':>3} {'control':>16} {'C1':>16} {'paired delta':>16}")
    for arm in C1_ARMS:
        pairs = []
        for s in SEEDS:
            c = _summary(f"{HOUR_CONTROL[arm]}_n{DEMAND}_s{s}")
            r = _summary(f"c1_hour_{arm}_n{DEMAND}_s{s}")
            if c and r:
                pairs.append((c["busiest_powell_veh_hr"],
                              r["busiest_powell_veh_hr"]))
        if not pairs:
            print(f"{arm:18} {0:3d} {'(not on disk yet)':>16}")
            continue
        cv = np.array([p[0] for p in pairs])
        rv = np.array([p[1] for p in pairs])
        d = rv - cv
        inband = BAND[0] <= rv.mean() <= BAND[1]
        sd = lambda a: a.std(ddof=1) if len(a) > 1 else 0.0
        print(f"{arm:18} {len(pairs):3d} {cv.mean():8.0f} +/- {sd(cv):<5.0f} "
              f"{rv.mean():8.0f} +/- {sd(rv):<5.0f} "
              f"{d.mean():+8.0f} +/- {sd(d):<5.0f}"
              f"{'  IN BAND' if inband else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--count-day", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--task", type=int)
    ap.add_argument("--day-task", type=int)
    ap.add_argument("--readout", action="store_true")
    args = ap.parse_args()

    jobs, day_jobs = build_jobs(), build_day_jobs()
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")

    if args.check:
        raise SystemExit(0 if check() else 1)
    if args.count:
        print(len(jobs)); return
    if args.count_day:
        print(len(day_jobs)); return
    if args.list:
        for i, j in enumerate(jobs):
            print(f"{i:3d}  hour  {j['name']}")
        for i, j in enumerate(day_jobs):
            print(f"{i:3d}  day   {j['name']}")
        return
    if args.readout:
        readout(); return
    if args.task is not None:
        mce.run_one(jobs[args.task], graph_file, checkpoint=False)
        return
    if args.day_task is not None:
        # 24x longer, so crash recovery IS worth the checkpoint I/O
        mce.run_one(day_jobs[args.day_task], graph_file, checkpoint=True)
        return
    ap.error("pick one of --check/--count/--count-day/--list/--task/"
             "--day-task/--readout")


if __name__ == "__main__":
    main()
