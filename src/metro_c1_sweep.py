"""C1 sensitivity sweep: how much of the day result rests on REROUTE_STUCK_S?

WHY THIS EXISTS. DEMAND_EXIT_PLAN.md has called `REROUTE_STUCK_S = 120 s` the
weakest link in the phase since the mechanism was built, and the Aug 3 day result
made that worse rather than better: the freeze clears with network stuck time
down 84.7%, and that headline currently rests on a driver-patience constant with
NO direct source. Unlike IDM_T (kernel physics) or the NHTS trip shares (a
published table), 120 s is a judgement. It is not fitted to the held-out PBOT
counts or the ODOT band, which keeps it honest, but "not fitted" is not "not
load-bearing". This sweep asks whether the VERDICT -- freeze clears, band holds --
is stable across the plausible range, or whether it is an artifact of one number.

THE RANGE, and why these five values. Navigation apps re-plan within a minute or
two of detecting delay; an unaided driver with no app is the slow end. 30 s is
about as impatient as a human plausibly gets (roughly one signal cycle); 480 s is
eight minutes of sitting still, which is close to the limit of what a driver
tolerates before ANY behavioural response. The a-priori 120 s sits in the middle.
Nothing here is tuned: the range is a plausibility interval, chosen before the
runs, and the sweep is reported whichever way it comes out.

    30 s   60 s   [120 s]   240 s   480 s

**THE 120 s ARM IS NOT RE-RUN.** It is already on disk -- `c1_hour_realism_
reroute_*` (8 seeds) and `c1_dayprof_realism_reroute_*` (seed 42) ARE the 120 s
runs, because 120.0 is the config default they ran with. Joining them saves 9
cluster jobs. That join is valid ONLY while the default is still 120.0, so
`--check` REFUSES if config.REROUTE_STUCK_S has moved: a silently re-defaulted
constant would relabel the existing runs as some other patience and put a wrong
point in the middle of the curve.

REALISM ARM ONLY, deliberately. The base model is out of the ODOT band in every
seed of both the control and the C1 hour arm (0/8 either way), so its numbers do
not describe real Powell flow -- sweeping a constant on a model that is already
out of band would spend cluster time measuring the sensitivity of an unphysical
result. If the base day arm (117851_0) lands and changes that judgement, add
"base" here then, not before.

TWO SUB-EXPERIMENTS, separate arrays, same split and same reasoning as C1 itself:

  DAY (`--day-task`, orca/job_c1_sweep_day.sh): 4 new patience values x seed 42
    x 86,400 steps. This is the one that protects the headline -- it asks whether
    hour-23 stuck time still falls toward the PORTAL quota of 2,876 at every
    patience, or whether the freeze re-appears once drivers wait longer. Read it
    with `python src/day_readout.py --runs c1sweep`, which gives the same
    quota-aware per-hour verdict A2 and C1 were judged on.

  HOUR (`--task`, orca/job_c1_sweep_hour.sh): 4 new values x the 8 pinned seeds
    x one simulated hour. The band-regression half: a longer patience means fewer
    re-plans, a shorter one means more, and either could push busiest Powell out
    of the real ODOT band of 1,400-1,745 veh/hr. 8 seeds because the band claim
    is a per-seed membership claim, not a mean.

DISCIPLINE (CLAUDE.md). Its own harness rather than arms added to
metro_c1_experiment, for the same reason B1xB3 and the ablation got their own:
`build_jobs` indexes SLURM array tasks by order, so inserting arms renumbers
existing arrays. Reuses `mce.run_one` unchanged (unique RUN_NAME per job, per-job
seed, one writer per file, SKIP on existing parquet, metro graph guard). Every
value a-priori; nothing tuned to the held-out counts or the band.

READ ANY RESULT WITH C1'S TWO STANDING BOUNDS: no U-turn, so relief is bounded by
how many cars are still upstream of a fork; and perfect instantaneous
network-wide occupancy, so every point on this curve is an UPPER BOUND.

Usage:
    python src/metro_c1_sweep.py --check       # prerequisites, before submitting
    python src/metro_c1_sweep.py --count       # hour-job count (SLURM array size)
    python src/metro_c1_sweep.py --count-day   # day-job count
    python src/metro_c1_sweep.py --list        # task id -> run name
    python src/metro_c1_sweep.py --task N      # run one hour job
    python src/metro_c1_sweep.py --day-task N  # run one day job
    python src/metro_c1_sweep.py --readout     # hour band + efficiency vs patience
    python src/metro_c1_sweep.py --readout --deep     # + network-wide totals
    python src/day_readout.py --runs c1sweep   # the DAY verdict (quota-aware)
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import config
import metro_calibrated_experiment as mce
import metro_c1_experiment as m1

# the patience values, seconds. BASELINE is already on disk and is never re-run.
BASELINE_S = 120.0
PATIENCE_S = [30.0, 60.0, BASELINE_S, 240.0, 480.0]
NEW_S = [s for s in PATIENCE_S if s != BASELINE_S]

DEMAND = m1.DEMAND          # 16,500, the untuned a-priori level, as C1 and A2
SEEDS = m1.SEEDS            # the 8 pinned seeds
DAY_SEED = m1.DAY_SEED      # A2 ran one seed; a PAIRED comparison must use it
BAND = m1.BAND              # the real ODOT peak-hour band

# what each patience is paired against, and where the already-run 120 s point
# lives. The no-reroute controls are the same ones C1 used.
HOUR_CONTROL = "metrocal_realism"
DAY_CONTROL = "metrocal_dayprof_realism"
BASELINE_HOUR = "c1_hour_realism_reroute"
BASELINE_DAY = "c1_dayprof_realism_reroute"


def arm_name(s):
    return f"sweep_p{int(s)}"


def hour_stem(s, seed):
    if s == BASELINE_S:
        return f"{BASELINE_HOUR}_n{DEMAND}_s{seed}"
    return f"c1sw_hour_p{int(s)}_n{DEMAND}_s{seed}"


def day_stem(s):
    if s == BASELINE_S:
        return f"{BASELINE_DAY}_n{DEMAND}_s{DAY_SEED}"
    return f"c1sw_dayprof_p{int(s)}_n{DEMAND}_s{DAY_SEED}"


# ---------------------------------------------------------------------------
# arm registration
#
# Each sweep arm carries REROUTE_STUCK_S as an ARM KEY, which interacts with
# run_one's complement-off loop: any key appearing in ANY registered arm but not
# in the running one is set False. That is safe in both directions here, and the
# reasoning is worth writing down because it is not obvious:
#   - a NON-reroute arm (base/realism) gets REROUTE_STUCK_S = False, but
#     build_reroute_context returns at `if not config.REROUTE_ENABLED` before it
#     ever reads the trigger, so the value is inert;
#   - a reroute arm that somehow lacked the key would get False and then hit
#     `if config.REROUTE_STUCK_S <= 0: raise ValueError` -- a LOUD refusal, not a
#     silently wrong run. That is the failure mode this project wants.
# The two C1 arms are pinned to the default below for exactly that reason: they
# are the only registered reroute arms that do not declare a patience, and
# pinning them makes the sweep module incapable of breaking a C1 re-run. 120.0
# IS their default, so this changes no behaviour and no number.
# ---------------------------------------------------------------------------
SWEEP_ARMS = {arm_name(s): dict(m1.REALISM,
                                **{m1.C1_FLAG: True, "REROUTE_STUCK_S": s})
              for s in PATIENCE_S}
mce.ARMS.update(SWEEP_ARMS)
for _a in ("base_reroute", "realism_reroute"):
    mce.ARMS[_a].setdefault("REROUTE_STUCK_S", BASELINE_S)


def build_jobs():
    """Hour-job list; index == SLURM array task id. 4 new values x 8 seeds."""
    return [{"arm": arm_name(s), "seed": seed, "n_veh": DEMAND,
             "steps": mce.METRO["N_STEPS"], "name": hour_stem(s, seed)}
            for s in NEW_S for seed in SEEDS]


def build_day_jobs():
    """Day-job list; index == SLURM array task id. 4 new values x 1 seed."""
    return [{"arm": arm_name(s), "seed": DAY_SEED, "n_veh": DEMAND,
             "steps": mce.DAY_STEPS, "profile": True, "by_hour": "segments",
             "name": day_stem(s)}
            for s in NEW_S]


def check():
    """Verify every prerequisite BEFORE cluster time is spent."""
    ok = True
    for k, v in mce.METRO.items():
        setattr(config, k, v)

    # THE LOAD-BEARING CHECK. The 120 s point is joined from disk instead of
    # re-run, which is only valid while 120.0 is still what those runs used.
    if config.REROUTE_STUCK_S == BASELINE_S:
        print(f"  ok       config.REROUTE_STUCK_S is {BASELINE_S:.0f} s, so the "
              f"existing C1 runs ARE the {BASELINE_S:.0f} s point")
    else:
        print(f"  REFUSE   config.REROUTE_STUCK_S is {config.REROUTE_STUCK_S}, "
              f"not {BASELINE_S} -- the existing C1 runs are then NOT the "
              f"{BASELINE_S:.0f} s point and joining them would put a "
              f"mislabelled value in the middle of the curve")
        ok = False

    graph = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if os.path.exists(graph):
        print(f"  ok       graph: {graph} "
              f"({os.path.getsize(graph) / 1e6:.0f} MB)")
    else:
        print(f"  MISSING  graph at {graph}")
        ok = False

    # the day arms are profiled; without the real curve they fall back to a
    # synthetic hourly shape and stop being comparable to A2 or to C1. Ask
    # demand_data for the path it will actually read so this cannot drift.
    import demand_data
    portal = os.path.abspath(demand_data._DEFAULT_CSV)
    if os.path.exists(portal):
        print(f"  ok       PORTAL hourly curve: {portal}")
    else:
        print(f"  MISSING  {portal} -- the day arms would fall back to a "
              f"synthetic hourly shape and NOT be comparable to A2/C1")
        ok = False

    # the joined-from-disk points: the no-reroute controls and the 120 s runs
    for label, stems in (
            ("hour no-reroute controls",
             [f"{HOUR_CONTROL}_n{DEMAND}_s{s}" for s in SEEDS]),
            (f"hour {BASELINE_S:.0f} s runs",
             [hour_stem(BASELINE_S, s) for s in SEEDS]),
            ("day no-reroute control", [f"{DAY_CONTROL}_n{DEMAND}_s{DAY_SEED}"]),
            (f"day {BASELINE_S:.0f} s run", [day_stem(BASELINE_S)])):
        have = sum(1 for st in stems if m1._summary(st))
        good = have == len(stems)
        print(f"  {'ok      ' if good else 'MISSING '} {label}: "
              f"{have}/{len(stems)} on disk")
        ok &= good

    print(f"\n{'READY' if ok else 'NOT READY'}: {len(build_jobs())} hour jobs, "
          f"{len(build_day_jobs())} day jobs at n={DEMAND}; patience "
          f"{[int(s) for s in NEW_S]} s new, {int(BASELINE_S)} s joined")
    return ok


def readout(deep=False):
    """Band and efficiency versus patience, for whatever is on disk."""
    print(f"C1 REROUTE_STUCK_S sweep, realism stack, n={DEMAND}\n")
    print(f"HOUR (band regression): busiest Powell veh/hr, real band "
          f"{BAND[0]:,}-{BAND[1]:,}")
    print(f"{'patience':>10} {'n':>3} {'control':>16} {'sweep':>16} "
          f"{'paired delta':>16}  band/seed")

    sd = lambda a: a.std(ddof=1) if len(a) > 1 else 0.0
    for s in PATIENCE_S:
        pairs = []
        for seed in SEEDS:
            c = m1._summary(f"{HOUR_CONTROL}_n{DEMAND}_s{seed}")
            r = m1._summary(hour_stem(s, seed))
            if c and r:
                pairs.append((c["busiest_powell_veh_hr"],
                              r["busiest_powell_veh_hr"]))
        tag = f"{int(s)} s" + ("*" if s == BASELINE_S else "")
        if not pairs:
            print(f"{tag:>10} {0:3d} {'(not on disk yet)':>16}")
            continue
        cv = np.array([p[0] for p in pairs])
        rv = np.array([p[1] for p in pairs])
        d = rv - cv
        nb = sum(BAND[0] <= v <= BAND[1] for v in rv)
        print(f"{tag:>10} {len(pairs):3d} {cv.mean():8.0f} +/- {sd(cv):<5.0f} "
              f"{rv.mean():8.0f} +/- {sd(rv):<5.0f} "
              f"{d.mean():+8.0f} +/- {sd(d):<5.0f}  {nb}/{len(rv)}"
              f"{'  IN BAND' if BAND[0] <= rv.mean() <= BAND[1] else ''}")
    print(f"\n  * {int(BASELINE_S)} s is the a-priori value, joined from the "
          f"existing C1 runs, not re-run.\n  Band membership is per seed; the "
          f"IN BAND tag is the weaker arm-mean claim.")

    print(f"\nDAY (does the freeze still clear?): network stuck veh-h, "
          f"hour 23 vs the PORTAL quota of 2,876")
    print(f"{'patience':>10} {'whole-day stuck':>16} {'h23 stuck':>12} "
          f"{'x quota':>9}  verdict")
    ctrl = m1._summary(f"{DAY_CONTROL}_n{DEMAND}_s{DAY_SEED}")
    if ctrl:
        q23 = 2876.0
        ch = ctrl["network_stuck_veh_h_by_hour"][23]
        print(f"{'none':>10} {ctrl['network_stuck_veh_h']:16.0f} {ch:12.1f} "
              f"{ch / q23:8.2f}x  control (A2 freeze)")
        for s in PATIENCE_S:
            r = m1._summary(day_stem(s))
            tag = f"{int(s)} s" + ("*" if s == BASELINE_S else "")
            if not r:
                print(f"{tag:>10} {'(not on disk yet)':>16}")
                continue
            rh = r["network_stuck_veh_h_by_hour"][23]
            # the A2/C1 reading rule: a cleared freeze is h23 stuck FALLING
            # TOWARD the quota, not merely a whole-day total that moved
            v = "clears" if rh < q23 else "freeze persists"
            print(f"{tag:>10} {r['network_stuck_veh_h']:16.0f} {rh:12.1f} "
                  f"{rh / q23:8.2f}x  {v}")
        print("\n  Whole-day totals are the coarse view. Run "
              "`python src/day_readout.py --runs c1sweep`\n  for the "
              "quota-aware per-hour verdict and the deadlock flag, which is "
              "what\n  A2 and C1 were actually judged on.")
    else:
        print(f"{'':10} (day control {DAY_CONTROL} not on disk)")

    if deep:
        print("\nNETWORK (segment parquets), each patience vs the no-reroute "
              "control.\nFleet veh-s is fixed by construction for the HOUR runs, "
              "so those lines are\nefficiency differences, not demand "
              "differences.")
        print(f"\n{'':4}{'measure':24} {'control':>14} {'sweep':>14} "
              f"{'paired delta':>26}  {'seeds':>5}  {'pct':>7}")
        for s in PATIENCE_S:
            print(f"\n  HOUR  {int(s)} s vs {HOUR_CONTROL}")
            m1._deep([(f"{HOUR_CONTROL}_n{DEMAND}_s{seed}", hour_stem(s, seed))
                      for seed in SEEDS])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--count-day", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--task", type=int)
    ap.add_argument("--day-task", type=int)
    ap.add_argument("--readout", action="store_true")
    ap.add_argument("--deep", action="store_true",
                    help="with --readout: network-wide totals from the segment "
                         "parquets (slower, reads ~5 MB per run)")
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
        readout(deep=args.deep); return
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
