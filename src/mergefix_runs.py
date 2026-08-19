"""Merge-fix re-validation: 8 seeds with MERGE_ENTRY_IMPROVED, graded by the
frozen 91-station PORTAL harness. Predictions REGISTERED HERE BEFORE ANY TASK
RUNS (this file is committed first; the commit date is the registration date).

WHAT THIS RUNS
--------------
One arm, 8 tasks: the exact configuration of the validated
lcap_realism_reallanes_n16500 campaign (realism stack, corrected real lanes,
the cited 16,500 demand, same 8 seeds, same widened graph) with ONE change:
config.MERGE_ENTRY_IMPROVED = True. Any difference from the saved baseline
runs is therefore attributable to the improved junction entry rule alone.

Grading is the UNCHANGED portal_speed_check harness: same frozen mainline-2DS
station set, same real PORTAL days (Aug 11-13 2026, cached), same snapping.
The real data cannot move; only the model side does.

MECHANISM BASIS (all committed before this file)
------------------------------------------------
src/blackspot_trace.py: 4 of the 5 too-hard stations pin on merge/diverge
junctions discharging ~1,000 veh/hr per contested lane into a FREE downstream
edge; the 5th (N Columbia, station 3124) pins on a signalized ramp terminus.
src/merge_scenarios.py: through the real kernel, the improved entry rule takes
the I-205-shaped toy merge from 41% to 100% of the control discharge rate and
leaves the no-junction control bit-identical (0.0% drift).

REGISTERED PREDICTIONS (graded on the 8-seed mean, like the harness itself)
---------------------------------------------------------------------------
The four merge/diverge blackspots: 10587 (NB I-205 Burnside), 10585 (NB I-205
Division), 3163 (EB US-26 Jefferson), 3180 (EB US-26 at OR-217). The signal
case: 3124 (NB I-5 N Columbia).

  P1  Each of the four merge/diverge stations at least DOUBLES its model/real
      ratio, and at least 3 of the 4 end above 0.5.
  P2  Station 3124 stays BELOW 0.5. Its mechanism is the signalized ramp
      terminus, which this fix does not touch; if it heals anyway, the
      blackspot diagnosis was wrong about it.
  P3  The 86 currently-good stations stay good: their median ratio stays in
      [0.90, 1.05] (baseline 0.97) and at most 2 of them fall below 0.5.
  P4  SB I-5 at Russell (the Rose Quarter, too FAST at ratio ~1.7) stays
      above 1.3. The fix adds junction capacity; overspeed there needs
      weaving friction, which is explicitly out of scope. If Russell heals,
      the improvement came from somewhere unmodeled and the fix should be
      distrusted, not celebrated.

  Exploratory readouts, NO prediction registered: the overall 91-station
  median ratio; busiest-Powell throughput vs the 1,400-1,745 ODOT band (the
  entry rule also runs at arterial junctions, so Powell numbers may move;
  whatever they do is reported, not selected on).

CITATION RULE: the baseline arm stays the citable configuration until the
mentor accepts the fix at a calibration gate. These runs exist to grade the
fix, not to replace published numbers.

Usage:
  python src/mergefix_runs.py --check     # refuse-fast preflight
  python src/mergefix_runs.py --count
  sbatch --array=0-7 orca/job_mergefix.sh
  python src/mergefix_runs.py --readout   # grades P1-P4 vs the baseline arm
"""
import argparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import metro_calibrated_experiment as mce

GRAPH_NAME = "graph_metro20k_lanes.graphml"
MIN_GRAPH_MB = 50
SEEDS = list(mce.SEEDS)
N_VEH = 16500

BASE_ARM = "lcap_realism_reallanes_n16500"   # the saved baseline runs
FIX_ARM = "mfix_n16500"                      # this campaign's parquet stem

MERGE_STATIONS = [10587, 10585, 3163, 3180]  # P1: merge/diverge blackspots
SIGNAL_STATION = 3124                        # P2: signalized ramp terminus


def stem(seed):
    return f"{FIX_ARM}_s{seed}"


def build_jobs():
    return [{"arm": "realism", "seed": s, "n_veh": N_VEH,
             "steps": mce.METRO["N_STEPS"], "name": stem(s)} for s in SEEDS]


def graph_path():
    return os.path.join(config.NETWORK_DIR, GRAPH_NAME)


def check():
    """Every prerequisite, verified BEFORE cluster time is spent."""
    ok = True
    g = graph_path()
    if os.path.exists(g):
        mb = os.path.getsize(g) / 1e6
        print(f"  ok       widened graph: {g} ({mb:.0f} MB)")
        if mb < MIN_GRAPH_MB:
            print(f"  REFUSE   too small to be the 20 km metro graph")
            ok = False
    else:
        print(f"  MISSING  widened graph at {g}")
        ok = False

    if not hasattr(config, "MERGE_ENTRY_IMPROVED"):
        print(f"  REFUSE   config.MERGE_ENTRY_IMPROVED missing; wrong branch?")
        ok = False
    elif config.MERGE_ENTRY_IMPROVED:
        print(f"  REFUSE   MERGE_ENTRY_IMPROVED is True in config.py; the "
              f"committed default must stay False (tasks set it themselves)")
        ok = False
    else:
        print(f"  ok       MERGE_ENTRY_IMPROVED exists, default False")

    have = sum(os.path.exists(os.path.join(
        config.PROCESSED_DIR, f"{BASE_ARM}_s{s}_segments.parquet"))
        for s in SEEDS)
    print(f"  {'ok      ' if have == len(SEEDS) else 'WARNING '} baseline "
          f"parquets on disk: {have}/{len(SEEDS)} (readout needs them)")

    print(f"\n{'READY' if ok else 'NOT READY'}: {len(build_jobs())} tasks")
    return ok


def readout():
    """Grade P1-P4: baseline arm vs the mergefix arm through the SAME frozen
    harness. Read-only; loads the graph twice (once per arm), no simulation."""
    import numpy as np
    import portal_speed_check as psc

    print("merge-fix re-validation readout (predictions registered in this "
          "file's docstring)\n\n--- baseline arm ---")
    base, _, _, nb = psc.build(BASE_ARM)
    print(f"\n--- mergefix arm ---")
    fix, _, _, nf = psc.build(FIX_ARM)
    print(f"\nseeds: baseline {nb}, mergefix {nf} (predictions are graded on "
          f"the {len(SEEDS)}-seed mean; a partial campaign is PENDING, "
          f"not evidence)")
    b = base.set_index("sid")
    f = fix.set_index("sid")
    both = b.index.intersection(f.index)

    print(f"\n{'station':<46}{'real':>6}{'base':>7}{'fix':>7}"
          f"{'ratio':>7} -> {'ratio':<6}")
    for sid in MERGE_STATIONS + [SIGNAL_STATION]:
        if sid not in both:
            print(f"  {sid}: not matched in one of the arms")
            continue
        r0, r1 = b.loc[sid], f.loc[sid]
        tag = "P2" if sid == SIGNAL_STATION else "P1"
        print(f"{tag} {r0['text']:<43}{r0['day']:>6.0f}{r0['model']:>7.1f}"
              f"{r1['model']:>7.1f}{r0['ratio']:>7.2f} -> {r1['ratio']:<6.2f}")

    p1_sids = [s for s in MERGE_STATIONS if s in both]
    doubled = sum(f.loc[s, "ratio"] >= 2 * b.loc[s, "ratio"] for s in p1_sids)
    above = sum(f.loc[s, "ratio"] > 0.5 for s in p1_sids)
    p1 = doubled == len(p1_sids) == 4 and above >= 3
    print(f"\nP1 all 4 double AND >=3 end above 0.5: doubled {doubled}/4, "
          f"above 0.5 {above}/4  -> {'SUPPORTED' if p1 else 'NOT SUPPORTED'}")

    if SIGNAL_STATION in both:
        r = f.loc[SIGNAL_STATION, "ratio"]
        print(f"P2 station {SIGNAL_STATION} stays below 0.5: ratio {r:.2f}  "
              f"-> {'SUPPORTED' if r < 0.5 else 'NOT SUPPORTED'}")

    others = [s for s in both if s not in MERGE_STATIONS + [SIGNAL_STATION]]
    med = float(np.median([f.loc[s, "ratio"] for s in others]))
    newly = sum(f.loc[s, "ratio"] < 0.5 and b.loc[s, "ratio"] >= 0.5
                for s in others)
    p3 = 0.90 <= med <= 1.05 and newly <= 2
    print(f"P3 the other {len(others)} stations stay good: median {med:.2f} "
          f"(bar [0.90, 1.05]), newly below half {newly} (bar <=2)  "
          f"-> {'SUPPORTED' if p3 else 'NOT SUPPORTED'}")

    russ = [s for s in both if "Russell" in str(b.loc[s, "text"])
            and b.loc[s, "ref"] == "I 5"]
    for s in russ:
        r = f.loc[s, "ratio"]
        print(f"P4 Russell stays above 1.3: {b.loc[s, 'text']} ratio "
              f"{b.loc[s, 'ratio']:.2f} -> {r:.2f}  "
              f"-> {'SUPPORTED' if r > 1.3 else 'NOT SUPPORTED'}")

    print(f"\nexploratory (no prediction): overall median ratio "
          f"{float(b['ratio'].median()):.2f} -> {float(f['ratio'].median()):.2f}; "
          f"stations below half {int((b['ratio'] < 0.5).sum())} -> "
          f"{int((f['ratio'] < 0.5).sum())} of {len(both)}")
    for s in SEEDS:
        p = os.path.join(config.PROCESSED_DIR, f"{stem(s)}_summary.json")
        if os.path.exists(p):
            with open(p) as fh:
                j = json.load(fh)
            print(f"  seed {s}: busiest Powell {j['busiest_powell_veh_hr']:,.0f} "
                  f"veh/hr, stuck {j['network_stuck_veh_h']:,.0f} veh-h")


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
            print(f"{i:3d}  seed {j['seed']:<5} {j['name']}")
        return
    if args.check:
        raise SystemExit(0 if check() else 1)
    if args.readout:
        readout()
        return
    if args.task is not None:
        job = jobs[args.task]
        g = graph_path()
        if not os.path.exists(g):
            raise SystemExit(f"no widened graph at {g}; refusing to download "
                             f"mid-experiment")
        # set explicitly every task so state can never leak between array tasks
        config.LANES_REAL = True
        config.MERGE_ENTRY_IMPROVED = True
        mce.run_one(job, g, checkpoint=False)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
