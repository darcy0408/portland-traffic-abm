"""Rerouting re-validation: 8 seeds with REROUTE_ENABLED, graded by the frozen
91-station PORTAL harness. Predictions REGISTERED HERE BEFORE ANY TASK RUNS
(this file is committed first; the commit date is the registration date).

WHAT THIS RUNS
--------------
One arm, 8 tasks: the exact configuration of the validated
lcap_realism_reallanes_n16500 campaign (realism stack, corrected real lanes,
the cited 16,500 demand, same 8 seeds, same widened graph) with ONE change:
config.REROUTE_ENABLED = True (constants pinned to the committed defaults:
stuck 120 s, cooldown 300 s, <= 20 re-plans/step). MERGE_ENTRY_IMPROVED stays
False, so any difference from the saved baseline runs is attributable to
en-route replanning alone.

Grading is the UNCHANGED portal_speed_check harness: same frozen mainline-2DS
station set, same real PORTAL days (Aug 11-13 2026, cached), same snapping.
The real data cannot move; only the model side does.

MECHANISM BASIS (all committed before this file)
------------------------------------------------
The merge-entry fix (mfix arm, ledger section 33) healed only OR-217; the
post-fix trace (commit 8f28d40) reduced the surviving I-205 blackspot to
ROUTING CONCENTRATION: the model plans every route once at spawn on free-flow
times, so nearly all NB I-205 traffic (1,857/h) picks the same downtown-bound
ramp pair worth ~949/h combined, and no junction entry rule can fix a queue
whose cause is that everybody chose the same path. C1 en-route rerouting
(ported in the previous commit, gate 6/6 incl. flag-off bitwise identity)
attacks exactly that: a car stuck below the stuck speed for 120 s re-plans to
its unchanged destination on congestion-aware weights, conserving demand.

REGISTERED PREDICTIONS (graded on the 8-seed mean, like the harness itself)
---------------------------------------------------------------------------
The routing-concentration pair: 10587 (NB I-205 Burnside, baseline ratio
~0.03) and 10585 (NB I-205 Division, ~0.09). Controls and do-no-harm below.

  P1  Both I-205 stations at least DOUBLE their model/real ratio, and at
      least one of the two ends at or above 0.5. This is the mechanism's home
      turf: if replanning cannot move the one blackspot diagnosed as a
      routing problem, the mechanism does not do what the trace says is
      needed.
  P2  The 86 currently-good stations stay good: their median ratio stays in
      [0.90, 1.05] (baseline 0.97) and at most 2 of them fall below 0.5.
      This is the make-or-break claim: rerouting moves traffic ONTO parallel
      corridors, and a mechanism that heals two stations by jamming ten is a
      net loss, not a fix.
  P3  SB I-5 at Russell (too FAST at ratio ~1.7) stays above 1.3. Rerouting
      adds no weaving friction; it can only move demand. If Russell heals,
      the improvement came from diverted load slowing the mainline, which
      must be reported as load, not as physics.
  P4  Network stuck vehicle-hours DROP vs the baseline arm in all 8 paired
      seeds, |t| > 3 on the paired relative differences (the project's
      standing campaign bar). This is C1's core purpose: cars queueing for a
      path that stopped being good is exactly what replanning removes. If
      stuck time does not fall, the mechanism is not functioning at scale
      and the station results should be distrusted.

  Exploratory readouts, NO prediction registered: 3163 (EB US-26 Jefferson)
  and 3180 (EB US-26 at OR-217), whose mechanism is junction CAPACITY
  (feeders throttling to ~1,000/h per contested lane); rerouting adds no
  capacity and can help only via diversion to the thin parallels over the
  west hills, whose adequacy we cannot predict a priori. 3124 (NB I-5 N
  Columbia), a real signalized ramp terminus. The overall 91-station median;
  busiest-Powell throughput vs the 1,400-1,745 ODOT band; and the re-plan
  counts (printed per task in the SLURM logs; if the 20/step compute cap
  binds every step, a null result means the budget bound, not that
  replanning is ineffective, and must be re-run with a higher cap, which
  would be a NEW registration).

SENSITIVITY CAVEAT, registered up front: REROUTE_STUCK_S = 120 s is the
softest constant in the mechanism (an a-priori driver-patience guess, never
fit to counts). These runs pin it at the committed default. Any later sweep
of it is exploratory.

CITATION RULE: the baseline arm stays the citable configuration until the
mentor accepts the mechanism at a calibration gate. These runs exist to grade
replanning, not to replace published numbers. If P1, P2 and P4 hold, the
NEXT registered step is a separately labeled rerouting arm appended to
PREREG_I5_ROSEQUARTER.md BEFORE the Sept 11 closure.

Usage:
  python src/reroute_runs.py --check     # refuse-fast preflight
  python src/reroute_runs.py --count
  sbatch --array=0-7 orca/job_reroute.sh
  python src/reroute_runs.py --readout   # grades P1-P4 vs the baseline arm
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
FIX_ARM = "rrt_n16500"                       # this campaign's parquet stem

I205_PAIR = [10587, 10585]           # P1: the routing-concentration blackspot
CAPACITY_PAIR = [3163, 3180]         # exploratory: junction-capacity mechanism
SIGNAL_STATION = 3124                # exploratory: signalized ramp terminus
BLACKSPOTS = I205_PAIR + CAPACITY_PAIR + [SIGNAL_STATION]

# pinned mechanism constants for every task (the committed defaults, stated
# here so a task can never inherit swept or stale values -- the 4d4ca01 lesson)
PIN = {"REROUTE_ENABLED": True, "REROUTE_STUCK_S": 120.0,
       "REROUTE_COOLDOWN_S": 300.0, "REROUTE_MAX_PER_STEP": 20}


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

    for flag in ("REROUTE_ENABLED", "MERGE_ENTRY_IMPROVED"):
        if not hasattr(config, flag):
            print(f"  REFUSE   config.{flag} missing; wrong branch?")
            ok = False
        elif getattr(config, flag):
            print(f"  REFUSE   {flag} is True in config.py; the committed "
                  f"default must stay False (tasks set it themselves)")
            ok = False
        else:
            print(f"  ok       {flag} exists, default False")

    have = sum(os.path.exists(os.path.join(
        config.PROCESSED_DIR, f"{BASE_ARM}_s{s}_segments.parquet"))
        for s in SEEDS)
    print(f"  {'ok      ' if have == len(SEEDS) else 'WARNING '} baseline "
          f"parquets on disk: {have}/{len(SEEDS)} (readout needs them)")

    print(f"\n{'READY' if ok else 'NOT READY'}: {len(build_jobs())} tasks")
    return ok


def _stuck_by_seed(arm):
    """Network stuck vehicle-hours per seed, straight from the parquets (the
    per-segment stuck_sum column, seconds), so P4 needs no summary JSONs."""
    import pandas as pd
    out = {}
    for s in SEEDS:
        p = os.path.join(config.PROCESSED_DIR, f"{arm}_s{s}_segments.parquet")
        if os.path.exists(p):
            out[s] = float(pd.read_parquet(p, columns=["stuck_sum"])
                           ["stuck_sum"].sum()) / 3600.0
    return out


def readout():
    """Grade P1-P4: baseline arm vs the rerouting arm through the SAME frozen
    harness. Read-only; loads the graph twice (once per arm), no simulation."""
    import numpy as np
    import portal_speed_check as psc

    print("rerouting re-validation readout (predictions registered in this "
          "file's docstring)\n\n--- baseline arm ---")
    base, _, _, nb = psc.build(BASE_ARM)
    print(f"\n--- rerouting arm ---")
    fix, _, _, nf = psc.build(FIX_ARM)
    print(f"\nseeds: baseline {nb}, rerouting {nf} (predictions are graded on "
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
        tag = "P1" if sid in I205_PAIR else "EX"
        print(f"{tag} {r0['text']:<43}{r0['day']:>6.0f}{r0['model']:>7.1f}"
              f"{r1['model']:>7.1f}{r0['ratio']:>7.2f} -> {r1['ratio']:<6.2f}")

    p1_sids = [s for s in I205_PAIR if s in both]
    doubled = sum(f.loc[s, "ratio"] >= 2 * b.loc[s, "ratio"] for s in p1_sids)
    above = sum(f.loc[s, "ratio"] >= 0.5 for s in p1_sids)
    p1 = doubled == len(p1_sids) == 2 and above >= 1
    print(f"\nP1 both I-205 stations double AND >=1 ends at/above 0.5: "
          f"doubled {doubled}/2, at/above 0.5 {above}/2  "
          f"-> {'SUPPORTED' if p1 else 'NOT SUPPORTED'}")

    others = [s for s in both if s not in BLACKSPOTS]
    med = float(np.median([f.loc[s, "ratio"] for s in others]))
    newly = sum(f.loc[s, "ratio"] < 0.5 and b.loc[s, "ratio"] >= 0.5
                for s in others)
    p2 = 0.90 <= med <= 1.05 and newly <= 2
    print(f"P2 the other {len(others)} stations stay good: median {med:.2f} "
          f"(bar [0.90, 1.05]), newly below half {newly} (bar <=2)  "
          f"-> {'SUPPORTED' if p2 else 'NOT SUPPORTED'}")

    russ = [s for s in both if "Russell" in str(b.loc[s, "text"])
            and b.loc[s, "ref"] == "I 5"]
    for s in russ:
        r = f.loc[s, "ratio"]
        print(f"P3 Russell stays above 1.3: {b.loc[s, 'text']} ratio "
              f"{b.loc[s, 'ratio']:.2f} -> {r:.2f}  "
              f"-> {'SUPPORTED' if r > 1.3 else 'NOT SUPPORTED'}")

    sb, sf = _stuck_by_seed(BASE_ARM), _stuck_by_seed(FIX_ARM)
    paired = [s for s in SEEDS if s in sb and s in sf]
    if len(paired) == len(SEEDS):
        d = np.array([(sf[s] - sb[s]) / sb[s] for s in paired])
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d)))
        p4 = bool((d < 0).all() and abs(t) > 3)
        print(f"P4 network stuck veh-h drops, all seeds, |t|>3: "
              f"mean {d.mean() * 100:+.1f}%, sign {int((d < 0).sum())}/"
              f"{len(d)} down, t {t:+.2f}  "
              f"-> {'SUPPORTED' if p4 else 'NOT SUPPORTED'}")
        for s in paired:
            print(f"     seed {s:<5} {sb[s]:8,.0f} -> {sf[s]:8,.0f} veh-h "
                  f"({(sf[s] - sb[s]) / sb[s] * 100:+.1f}%)")
    else:
        print(f"P4 PENDING: paired stuck data for {len(paired)}/{len(SEEDS)} "
              f"seeds")

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
    print("  re-plan counts: per task in the SLURM logs (logs/rrt_*.out); "
          "check whether the 20/step cap bound")


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
        config.MERGE_ENTRY_IMPROVED = False
        for k, v in PIN.items():
            setattr(config, k, v)
        mce.run_one(job, g, checkpoint=False)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
