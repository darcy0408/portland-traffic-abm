"""Combined-arm re-validation: merge-entry fix + en-route rerouting together,
8 seeds, graded by the frozen 91-station PORTAL harness. Predictions
REGISTERED HERE BEFORE ANY TASK RUNS (this file is committed first; the
commit date is the registration date).

WHAT THIS RUNS
--------------
One arm, 8 tasks: the exact configuration of the validated
lcap_realism_reallanes_n16500 campaign with TWO changes:
config.MERGE_ENTRY_IMPROVED = True and config.REROUTE_ENABLED = True
(reroute constants pinned to the committed defaults: stuck 120 s, cooldown
300 s, <= 20 re-plans/step). Any difference from the saved baseline is
attributable to the two mechanisms together; their solo arms (mfix_n16500,
rrt_n16500) are already graded, so interaction effects are separable.

WHY A COMBINED ARM (the composition hypothesis, evidence committed first)
--------------------------------------------------------------------------
The two solo arms failed their headline predictions in complementary ways
at the same blackspot, NB I-205:
- mfix alone (ledger MF33): repaired the Banfield merge head, but the queue
  survived because route-once demand kept overloading one downtown ramp
  (the pin moved upstream to the ramp zipper; stations 0.03 / 0.09).
- rrt alone (ledger RR35): drained the queue tail by replanning the
  overload away (Division healed 0.08 -> 0.82, stuck time -23%), but
  stalled at the unrepaired merge head: the post-rrt trace pins the
  surviving 2.7 km Burnside queue at node 2449038690, the I-205-to-Banfield
  merge, EXACTLY the junction the merge fix heals.
Each mechanism's residual is the other's target. If the composition story
is right, running both heals Burnside; if Burnside still fails, the
residual is something neither mechanism models and the story is wrong.

REGISTERED PREDICTIONS (graded on the 8-seed mean, like the harness itself)
---------------------------------------------------------------------------
  P1  Composition headline: BOTH NB I-205 stations, 10587 (Burnside,
      baseline 0.03) and 10585 (Division, 0.08), end at or above 0.5.
  P2  The 86 currently-good stations stay good: median ratio in
      [0.90, 1.05] and at most 2 newly below 0.5.
  P3  Each mechanism's solo healing PERSISTS in the presence of the other:
      3180 (EB US-26 at OR-217, healed by mfix alone to 0.55) stays at or
      above 0.5, AND 3124 (N Columbia, healed by rrt alone to 1.11) stays
      at or above 0.5. If either reverts, the mechanisms interact
      destructively and the combined arm is distrusted regardless of P1.
  P4  Network stuck vehicle-hours drop vs the BASELINE arm in all 8 paired
      seeds with |t| > 3. Exploratory alongside (no prediction): whether
      the combo lands below rrt-alone's stuck time too.
  P5  SB I-5 Russell (too fast at 1.69) stays above 1.3: neither mechanism
      adds weaving friction. Solo arms moved it to 1.83 (mfix) and 1.69
      (rrt); a drop below 1.3 means an unmodeled interaction, distrust it.

  Exploratory readouts, NO prediction registered: 3163 (EB US-26
  Jefferson), which both solo arms only grazed (0.26 -> 0.23 mfix,
  0.26 -> 0.33 rrt); the overall median; the below-half count; busiest
  Powell vs the 1,400-1,745 ODOT band; and the per-task re-plan counts,
  now printed unconditionally (the verbose gate that ate them in the rrt
  campaign is removed in this same commit).

CITATION RULE: the baseline arm stays the citable configuration until the
mentor accepts any mechanism at a calibration gate. Solo-arm verdicts stand
as ledgered (MF33: P1 failed; RR35: P1 failed); this arm tests composition,
it does not retry those registrations.

Usage:
  python src/combo_runs.py --check     # refuse-fast preflight
  python src/combo_runs.py --count
  sbatch --array=0-7 orca/job_combo.sh
  python src/combo_runs.py --readout   # grades P1-P5 vs the baseline arm
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
RRT_ARM = "rrt_n16500"                       # rerouting-alone (context only)
FIX_ARM = "cmb_n16500"                       # this campaign's parquet stem

I205_PAIR = [10587, 10585]           # P1: the composition headline
PERSIST = [3180, 3124]               # P3: each solo arm's healed station
CAPACITY_LEFT = [3163]               # exploratory: Jefferson, still open
SIGNAL_STATION = 3124
BLACKSPOTS = [10587, 10585, 3163, 3180, 3124]

# pinned mechanism constants for every task (committed defaults, stated here
# so a task can never inherit swept or stale values)
PIN = {"MERGE_ENTRY_IMPROVED": True, "REROUTE_ENABLED": True,
       "REROUTE_STUCK_S": 120.0, "REROUTE_COOLDOWN_S": 300.0,
       "REROUTE_MAX_PER_STEP": 20}


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

    for flag in ("MERGE_ENTRY_IMPROVED", "REROUTE_ENABLED"):
        if not hasattr(config, flag):
            print(f"  REFUSE   config.{flag} missing; wrong branch?")
            ok = False
        elif getattr(config, flag):
            print(f"  REFUSE   {flag} is True in config.py; the committed "
                  f"default must stay False (tasks set it themselves)")
            ok = False
        else:
            print(f"  ok       {flag} exists, default False")

    for arm, why in ((BASE_ARM, "grading"), (RRT_ARM, "stuck-time context")):
        have = sum(os.path.exists(os.path.join(
            config.PROCESSED_DIR, f"{arm}_s{s}_segments.parquet"))
            for s in SEEDS)
        print(f"  {'ok      ' if have == len(SEEDS) else 'WARNING '} {arm} "
              f"parquets on disk: {have}/{len(SEEDS)} (readout needs them "
              f"for {why})")

    print(f"\n{'READY' if ok else 'NOT READY'}: {len(build_jobs())} tasks")
    return ok


def _stuck_by_seed(arm):
    """Network stuck vehicle-hours per seed, straight from the parquets."""
    import pandas as pd
    out = {}
    for s in SEEDS:
        p = os.path.join(config.PROCESSED_DIR, f"{arm}_s{s}_segments.parquet")
        if os.path.exists(p):
            out[s] = float(pd.read_parquet(p, columns=["stuck_sum"])
                           ["stuck_sum"].sum()) / 3600.0
    return out


def readout():
    """Grade P1-P5: baseline arm vs the combined arm through the SAME frozen
    harness. Read-only; loads the graph twice (once per arm), no simulation."""
    import numpy as np
    import portal_speed_check as psc

    print("combined-arm readout (predictions registered in this file's "
          "docstring)\n\n--- baseline arm ---")
    base, _, _, nb = psc.build(BASE_ARM)
    print(f"\n--- combined arm ---")
    fix, _, _, nf = psc.build(FIX_ARM)
    print(f"\nseeds: baseline {nb}, combined {nf} (predictions are graded on "
          f"the {len(SEEDS)}-seed mean; a partial campaign is PENDING, "
          f"not evidence)")
    b = base.set_index("sid")
    f = fix.set_index("sid")
    both = b.index.intersection(f.index)

    print(f"\n{'station':<46}{'real':>6}{'base':>7}{'fix':>7}"
          f"{'ratio':>7} -> {'ratio':<6}")
    for sid in BLACKSPOTS:
        if sid not in both:
            print(f"  {sid}: not matched in one of the arms")
            continue
        r0, r1 = b.loc[sid], f.loc[sid]
        tag = ("P1" if sid in I205_PAIR else
               "P3" if sid in PERSIST else "EX")
        print(f"{tag} {r0['text']:<43}{r0['day']:>6.0f}{r0['model']:>7.1f}"
              f"{r1['model']:>7.1f}{r0['ratio']:>7.2f} -> {r1['ratio']:<6.2f}")

    p1_sids = [s for s in I205_PAIR if s in both]
    above = sum(f.loc[s, "ratio"] >= 0.5 for s in p1_sids)
    p1 = above == len(p1_sids) == 2
    print(f"\nP1 both I-205 stations end at/above 0.5: {above}/2  "
          f"-> {'SUPPORTED' if p1 else 'NOT SUPPORTED'}")

    others = [s for s in both if s not in BLACKSPOTS]
    med = float(np.median([f.loc[s, "ratio"] for s in others]))
    newly = sum(f.loc[s, "ratio"] < 0.5 and b.loc[s, "ratio"] >= 0.5
                for s in others)
    p2 = 0.90 <= med <= 1.05 and newly <= 2
    print(f"P2 the other {len(others)} stations stay good: median {med:.2f} "
          f"(bar [0.90, 1.05]), newly below half {newly} (bar <=2)  "
          f"-> {'SUPPORTED' if p2 else 'NOT SUPPORTED'}")

    persist_ok = [s for s in PERSIST if s in both and f.loc[s, "ratio"] >= 0.5]
    p3 = len(persist_ok) == len(PERSIST)
    for s in PERSIST:
        if s in both:
            print(f"P3 solo healing persists at {s}: ratio "
                  f"{f.loc[s, 'ratio']:.2f} (bar >=0.5)")
    print(f"P3 both persist: {len(persist_ok)}/{len(PERSIST)}  "
          f"-> {'SUPPORTED' if p3 else 'NOT SUPPORTED'}")

    sb, sf = _stuck_by_seed(BASE_ARM), _stuck_by_seed(FIX_ARM)
    paired = [s for s in SEEDS if s in sb and s in sf]
    if len(paired) == len(SEEDS):
        d = np.array([(sf[s] - sb[s]) / sb[s] for s in paired])
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
        p4 = bool((d < 0).all() and abs(t) > 3)
        print(f"P4 network stuck veh-h drops vs baseline, all seeds, |t|>3: "
              f"mean {d.mean() * 100:+.1f}%, sign {int((d < 0).sum())}/"
              f"{len(d)} down, t {t:+.2f}  "
              f"-> {'SUPPORTED' if p4 else 'NOT SUPPORTED'}")
        sr = _stuck_by_seed(RRT_ARM)
        below_rrt = sum(sf[s] < sr[s] for s in paired if s in sr)
        print(f"   exploratory: combo below rrt-alone in {below_rrt}/"
              f"{len(paired)} seeds")
        for s in paired:
            extra = f", rrt {sr[s]:8,.0f}" if s in sr else ""
            print(f"     seed {s:<5} base {sb[s]:8,.0f} -> combo "
                  f"{sf[s]:8,.0f} veh-h ({(sf[s] - sb[s]) / sb[s] * 100:+.1f}%)"
                  f"{extra}")
    else:
        print(f"P4 PENDING: paired stuck data for {len(paired)}/{len(SEEDS)} "
              f"seeds")

    russ = [s for s in both if "Russell" in str(b.loc[s, "text"])
            and b.loc[s, "ref"] == "I 5" and b.loc[s, "ratio"] > 1.3]
    for s in russ:
        r = f.loc[s, "ratio"]
        print(f"P5 Russell overspeed control (baseline {b.loc[s, 'ratio']:.2f}"
              f"): ratio -> {r:.2f} (bar >1.3)  "
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
    print("  re-plan counts: per task in the SLURM logs (logs/cmb_*.out), "
          "printed unconditionally this time")


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
        for k, v in PIN.items():
            setattr(config, k, v)
        mce.run_one(job, g, checkpoint=False)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
