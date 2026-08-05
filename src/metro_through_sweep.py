"""THROUGH_TRAFFIC_FRACTION sensitivity sweep at metro scale.

Every metro number this project cites rests on THROUGH_TRAFFIC_FRACTION = 0.15,
a share that was set A PRIORI (re-derived from the corridor's 0.30 on the
argument that a wider window makes more trips internal) and never tested. That
makes it the same kind of exposed constant REROUTE_STUCK_S was before the
patience sweep: a reviewer can ask "why 0.15, and does your answer survive a
different guess?", and until now the honest reply was that nobody had checked.

This sweep answers it the same way, and under the same discipline.

WHAT IS SWEPT, AND WHAT DELIBERATELY IS NOT

Only the through-traffic share. The obvious companion knob, GRAVITY_DECAY_SCALE_M,
is NOT swept here and sweeping it at metro scale would measure nothing: metro runs
set DEMAND_LODES_OD = True, and generate.build_demand_weights returns the LODES OD
table before it ever reads the decay scale, so the parameter is INERT at this
scale. It binds only at corridor scale, where DEMAND_LODES_OD is off, which is a
cheap corridor-scale experiment rather than a cluster job. Checked in
src/generate.py (build_demand_weights, the `if config.DEMAND_LODES_OD:` early
return) on Aug 5 2026 before this harness was written.

THE MEASURE

Busiest-Powell throughput against the real ODOT peak-hour band, 1,400-1,745
veh/hr (ledger L5) -- the same yardstick the ablation (section 12) and the
patience sweep (section 18) were judged on, so the three are directly
comparable. run_one already computes it into each run's summary JSON, so the
readout needs only those summaries, not the parquets or the metro graph.

THE CITATION RULE, WRITTEN DOWN BEFORE THE RESULTS EXIST

0.15 STAYS the cited value whatever this sweep returns. The ODOT band is
validation data, so picking the share that best hits the band would tune a
parameter against the very target the model is judged on, and would forfeit the
a-priori status that makes the comparison honest. This is a sensitivity check on
an a-priori choice, never grounds to change it. Identical discipline to the
patience sweep and to the gravity decay scale, both of which were left alone
after their checks.

THE 0.15 POINT IS JOINED FROM DISK, NOT RE-RUN: the existing
metrocal_realism_n16500_s* runs ARE that point, and --check refuses to proceed
unless config still agrees, so a mislabelled value can never land mid-curve.

Usage:
    python src/metro_through_sweep.py --check    # prerequisites, before submitting
    python src/metro_through_sweep.py --count    # SLURM array size
    python src/metro_through_sweep.py --list     # task id -> run name
    python src/metro_through_sweep.py --task N   # run one job
    python src/metro_through_sweep.py --readout  # band vs through share
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

# The a-priori metro share, and the sweep around it. The span is 0 (no regional
# traffic at all) to 0.45 (triple the a-priori value, and half again the
# corridor's 0.30), so the curve brackets every share anyone could reasonably
# argue for rather than probing a narrow neighbourhood of the chosen value.
BASELINE_F = 0.15
FRACTIONS = [0.0, 0.075, BASELINE_F, 0.30, 0.45]
NEW_F = [f for f in FRACTIONS if f != BASELINE_F]

DEMAND = 16500              # the untuned a-priori metro level, as ABL/C1/A2
SEEDS = list(mce.SEEDS)     # the same 8 pinned seeds every metro experiment uses

# real ODOT peak-hour directional band for Powell (ledger L5). The yardstick,
# never a fitting target -- see the citation rule in the docstring.
BAND = (1400.0, 1745.0)

# where the already-run 0.15 point lives: the realism arm of the metrocal runs
HOUR_BASELINE = "metrocal_realism"


def arm_name(f):
    return f"thsw_f{int(round(f * 1000)):03d}"


def hour_stem(f, seed):
    if f == BASELINE_F:
        return f"{HOUR_BASELINE}_n{DEMAND}_s{seed}"
    return f"thsw_hour_f{int(round(f * 1000)):03d}_n{DEMAND}_s{seed}"


# ---------------------------------------------------------------------------
# arm registration, and the one trap in it
#
# run_one applies METRO, then the arm's keys, then sets every key that appears
# in ANY registered arm but not in the running one to False. Registering
# THROUGH_TRAFFIC_FRACTION as an arm key therefore makes it a live wire: a later
# re-run of plain "base" or "realism" would get THROUGH_TRAFFIC_FRACTION = False,
# which is numerically ZERO, and would silently produce a no-through-traffic run
# wearing the name of the a-priori one. Nothing would raise.
#
# The setdefault below defuses that by making every pre-existing arm declare the
# key explicitly at the METRO default it already had. Since that value IS 0.15,
# this changes no behaviour and no number now, and it makes the module incapable
# of corrupting a metrocal re-run later. Same fix, same reason, as the patience
# sweep's REROUTE_STUCK_S setdefault.
# ---------------------------------------------------------------------------
SWEEP_ARMS = {arm_name(f): dict(mce.ARMS["realism"],
                                **{"THROUGH_TRAFFIC_FRACTION": f})
              for f in FRACTIONS}
mce.ARMS.update(SWEEP_ARMS)
for _a in mce.ARMS:
    mce.ARMS[_a].setdefault("THROUGH_TRAFFIC_FRACTION",
                            mce.METRO["THROUGH_TRAFFIC_FRACTION"])


def build_jobs():
    """Hour-job list; index == SLURM array task id. 4 new shares x 8 seeds."""
    return [{"arm": arm_name(f), "seed": seed, "n_veh": DEMAND,
             "steps": mce.METRO["N_STEPS"], "name": hour_stem(f, seed)}
            for f in NEW_F for seed in SEEDS]


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

    # THE LOAD-BEARING CHECK. The 0.15 point is joined from disk rather than
    # re-run, which is only valid while 0.15 is still what those runs used.
    if abs(mce.METRO["THROUGH_TRAFFIC_FRACTION"] - BASELINE_F) < 1e-12:
        print(f"  ok       METRO THROUGH_TRAFFIC_FRACTION is {BASELINE_F}, so "
              f"the existing {HOUR_BASELINE} runs ARE the {BASELINE_F} point")
    else:
        print(f"  REFUSE   METRO THROUGH_TRAFFIC_FRACTION is "
              f"{mce.METRO['THROUGH_TRAFFIC_FRACTION']}, not {BASELINE_F} -- "
              f"the existing {HOUR_BASELINE} runs are then NOT the "
              f"{BASELINE_F} point, and joining them would put a mislabelled "
              f"value in the middle of the curve")
        ok = False

    # the complement-off defusing above must actually have taken
    for a in ("base", "realism"):
        if a in mce.ARMS and "THROUGH_TRAFFIC_FRACTION" in mce.ARMS[a]:
            print(f"  ok       arm '{a}' declares THROUGH_TRAFFIC_FRACTION "
                  f"({mce.ARMS[a]['THROUGH_TRAFFIC_FRACTION']}), so run_one's "
                  f"complement-off cannot zero it")
        else:
            print(f"  REFUSE   arm '{a}' does not declare "
                  f"THROUGH_TRAFFIC_FRACTION; a re-run of it would silently "
                  f"get 0")
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
    stems = [hour_stem(BASELINE_F, s) for s in SEEDS]
    have = sum(1 for st in stems if _summary(st))
    good = have == len(stems)
    print(f"  {'ok      ' if good else 'MISSING '} {BASELINE_F} baseline runs: "
          f"{have}/{len(stems)} on disk")
    ok &= good

    print(f"\n{'READY' if ok else 'NOT READY'}: {len(build_jobs())} hour jobs "
          f"at n={DEMAND}; shares {NEW_F} new, {BASELINE_F} joined")
    return ok


def readout():
    """Busiest-Powell band membership versus through share, for what is on disk."""
    print(f"THROUGH_TRAFFIC_FRACTION sweep, realism stack, n={DEMAND}\n")
    print(f"busiest Powell veh/hr vs the real ODOT band "
          f"{BAND[0]:,.0f}-{BAND[1]:,.0f}\n")
    print(f"{'share':>7}  {'busiest Powell':>20}  {'in band':>8}  "
          f"{'network stuck veh-h':>20}  {'runs':>5}")

    base = {}
    for f in FRACTIONS:
        vals, stuck, n_band, got = [], [], 0, 0
        for seed in SEEDS:
            s = _summary(hour_stem(f, seed))
            if not s:
                continue
            got += 1
            v = float(s["busiest_powell_veh_hr"])
            vals.append(v)
            stuck.append(float(s["network_stuck_veh_h"]))
            if BAND[0] <= v <= BAND[1]:
                n_band += 1
            if f == BASELINE_F:
                base[seed] = v
        if not vals:
            print(f"{f:>7.3f}  {'(no runs on disk)':>20}")
            continue
        a = np.array(vals)
        mark = " IN BAND" if BAND[0] <= a.mean() <= BAND[1] else ""
        print(f"{f:>7.3f}  {a.mean():>10,.0f} +/- {a.std(ddof=1) if len(a) > 1 else 0:<6,.0f}"
              f"  {n_band:>3}/{got:<4}  {np.mean(stuck):>20,.0f}  {got:>5}"
              f"{mark}")

    # paired deltas against the a-priori point, seed by seed, which is the
    # comparison that actually controls for seed-to-seed variation
    if base:
        print(f"\npaired vs the a-priori {BASELINE_F} (same seed, same demand):")
        for f in FRACTIONS:
            if f == BASELINE_F:
                continue
            d = [float(s["busiest_powell_veh_hr"]) - base[seed]
                 for seed in SEEDS
                 if (s := _summary(hour_stem(f, seed))) and seed in base]
            if d:
                d = np.array(d)
                print(f"  {f:>6.3f}: {d.mean():>+8,.0f} +/- "
                      f"{d.std(ddof=1) if len(d) > 1 else 0:,.0f} veh/hr  "
                      f"(n={len(d)})")

    print(f"\nCITATION RULE: {BASELINE_F} stays the cited value whatever this "
          f"shows. The band is validation data; choosing the share that best "
          f"hits it would tune a parameter against the target the model is "
          f"judged on. Sensitivity check only.")


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
            print(f"{i:3d}  {j['arm']:12s} seed {j['seed']:<6} {j['name']}")
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
