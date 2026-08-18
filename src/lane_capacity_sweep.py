"""Does correcting the lane counts raise the metro capacity ceiling?

BACKGROUND

Ledger section on demand magnitude (DM1-DM5) showed metro throughput saturates:
going from 16,500 to 24,750 vehicles moved the busiest Powell segment only
+135 veh/hr while network stuck vehicle-hours more than doubled. That sweep ran
the realism stack on the ORIGINAL graph, whose lane data was measurably wrong
(src/capacity_audit.py): OSMnx never downloaded lanes:forward / lanes:backward,
so two-way streets had their lane total halved and floored, 32% of arterial
edges had no lanes tag and fell back to 1, and a flat LANES_MAX of 3 clipped
100 freeway edges.

src/lanes_real.py fixes all three. Network lane supply rises 170,421 -> 172,764,
arterial mean 1.50 -> 1.61, and 304 freeway edges get the 4th and 5th lane the
flat cap was removing. This sweep asks whether that moves the ceiling.

WHAT IS SWEPT

Two arms, BOTH on the SAME widened graph, so the only difference is the parser
and the graph re-download cannot confound the comparison:

  realism_oldlanes   realism stack, config.LANES_REAL False (tag-only rules)
  realism_reallanes  realism stack, config.LANES_REAL True  (corrected)

Demand: the corrected arm gets the full curve 16,500 / 24,750 / 33,000 / 41,250
to locate the plateau. The control arm gets the two ends, 16,500 and 33,000,
which is enough to show whether the curves differ in shape. 8 pinned seeds
throughout. 48 tasks.

THE MEASURE

Busiest-Powell throughput against the real ODOT peak-hour band 1,400-1,745
veh/hr (ledger L5), plus network stuck vehicle-hours, the same two numbers the
demand sweep reported, so the curves are directly comparable.

REGISTERED PREDICTIONS, written before any task was submitted
---------------------------------------------------------------
Verdict bar for all three: the paired seed-level difference must hold in at
least 6 of 8 seeds. Fewer than 6 is NOT SUPPORTED and is reported that way.

  P1  At 16,500 the two arms agree on busiest-Powell throughput to within
      100 veh/hr. Reason: Powell already carries 2 lanes per direction under
      BOTH parsers (src/corridor_capacity.py), so correcting lanes should not
      move the corridor the model is judged on. If P1 fails, the corrected
      parser changed something on Powell that the static audit did not predict,
      and the audit is wrong.

  P2  At 33,000 the corrected arm has LOWER network stuck vehicle-hours than
      the control. Reason: the corrected parser adds ~2,300 lanes, concentrated
      on arterials and freeways, which is where queues form at high demand.

  P3  THE ACTUAL QUESTION. Throughput still saturates in the corrected arm:
      the Powell gain from 24,750 -> 33,000 is less than half the gain from
      16,500 -> 24,750. If P3 FAILS and throughput keeps scaling, then lane
      supply was the binding constraint after all and the audit's conclusion
      (that the single-file default, not the lane data, was the limiter) is
      wrong.

P3 is the one that decides whether the ceiling is real. It is written to be
falsifiable in the direction that would embarrass the audit.

CITATION RULE, fixed before the results exist

16,500 stays the cited demand whatever this returns, for the reason the demand
sweep already gave: the ODOT band is validation data, so choosing the demand or
the lane parser that best hits it would tune against the judging target. This
sweep measures a ceiling; it never selects a configuration.

Usage:
    python src/lane_capacity_sweep.py --check     # prerequisites, before submitting
    python src/lane_capacity_sweep.py --count     # SLURM array size
    python src/lane_capacity_sweep.py --list      # task id -> run name
    python src/lane_capacity_sweep.py --task N    # run one job
    python src/lane_capacity_sweep.py --readout   # the curves
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

GRAPH_NAME = "graph_metro20k_lanes.graphml"     # written by build_capacity_graph.py
MIN_GRAPH_MB = 50                                # the widened metro graph is ~83 MB

SEEDS = list(mce.SEEDS)
BAND = (1400.0, 1745.0)

# Demand levels per arm. The control gets the two ends only; cluster time buys
# the corrected arm's full curve, which is what locates the plateau.
CORRECTED_N = [16500, 24750, 33000, 41250]
CONTROL_N = [16500, 33000]

ARMS = {
    "realism_oldlanes":  {"LANES_REAL": False},
    "realism_reallanes": {"LANES_REAL": True},
}


def stem(arm, n, seed):
    return f"lcap_{arm}_n{n}_s{seed}"


def build_jobs():
    """Task list; index == SLURM array task id. Control first so a truncated
    run still yields a complete control arm to compare against."""
    jobs = []
    for arm, levels in (("realism_oldlanes", CONTROL_N),
                        ("realism_reallanes", CORRECTED_N)):
        for n in levels:
            for seed in SEEDS:
                jobs.append({"arm": "realism", "lane_arm": arm, "seed": seed,
                             "n_veh": n, "steps": mce.METRO["N_STEPS"],
                             "name": stem(arm, n, seed)})
    return jobs


def _summary(st):
    path = os.path.join(config.PROCESSED_DIR, f"{st}_summary.json")
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return json.load(fh)


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
            print(f"  REFUSE   that is too small to be the 20 km metro graph")
            ok = False
    else:
        print(f"  MISSING  widened graph at {g}")
        print(f"           build it with: python src/build_capacity_graph.py")
        ok = False

    # The graph must actually carry the directional tags, or the corrected arm
    # silently degrades to the tag-only rules and both arms become identical.
    if os.path.exists(g):
        import osmnx as ox
        G = ox.load_graphml(g)
        n_dir = sum(1 for _u, _v, d in G.edges(data=True)
                    if d.get("lanes:forward") is not None
                    or d.get("lanes:backward") is not None)
        if n_dir:
            print(f"  ok       directional lane tags present on {n_dir:,} edges")
        else:
            print(f"  REFUSE   no lanes:forward/backward on this graph; the two "
                  f"arms would be identical and the sweep would prove nothing")
            ok = False

    if hasattr(config, "LANES_REAL"):
        print(f"  ok       config.LANES_REAL exists (currently {config.LANES_REAL})")
    else:
        print(f"  REFUSE   config.LANES_REAL missing; branch not checked out?")
        ok = False

    jobs = build_jobs()
    print(f"\n{'READY' if ok else 'NOT READY'}: {len(jobs)} tasks "
          f"({len(CONTROL_N)}x8 control + {len(CORRECTED_N)}x8 corrected)")
    return ok


def readout():
    print("Lane-capacity sweep: does correcting lane counts move the ceiling?\n")
    print(f"busiest Powell veh/hr vs the real ODOT band "
          f"{BAND[0]:,.0f}-{BAND[1]:,.0f}\n")
    print(f"{'arm':<20}{'demand':>8}{'busiest Powell':>22}{'in band':>10}"
          f"{'stuck veh-h':>14}{'runs':>6}")
    print("-" * 80)
    got = {}
    for arm, levels in (("realism_oldlanes", CONTROL_N),
                        ("realism_reallanes", CORRECTED_N)):
        for n in levels:
            vals, stuck, in_band = [], [], 0
            for seed in SEEDS:
                s = _summary(stem(arm, n, seed))
                if not s:
                    continue
                v = float(s["busiest_powell_veh_hr"])
                vals.append(v)
                stuck.append(float(s["network_stuck_veh_h"]))
                in_band += BAND[0] <= v <= BAND[1]
                got[(arm, n, seed)] = (v, float(s["network_stuck_veh_h"]))
            if not vals:
                print(f"{arm:<20}{n:>8,}{'(no runs on disk)':>22}")
                continue
            a = np.array(vals)
            mark = "  IN BAND" if BAND[0] <= a.mean() <= BAND[1] else ""
            print(f"{arm:<20}{n:>8,}{a.mean():>14,.0f} +/- "
                  f"{a.std(ddof=1) if len(a) > 1 else 0:<5,.0f}"
                  f"{in_band:>6}/{len(vals):<3}{np.mean(stuck):>14,.0f}"
                  f"{len(vals):>6}{mark}")

    def paired(arm_a, arm_b, n, idx):
        d = [got[(arm_b, n, s)][idx] - got[(arm_a, n, s)][idx]
             for s in SEEDS if (arm_a, n, s) in got and (arm_b, n, s) in got]
        return np.array(d) if d else None

    def verdict(agree, have, bar=6, total=None):
        """Registered bar is an ABSOLUTE count: at least `bar` of 8 seeds.

        On a partial campaign that count can only RISE as runs land, so:
          - once `agree` reaches the bar the verdict is already final;
          - it is only refuted when the remaining seeds cannot get there;
          - otherwise it is PENDING, NOT 'not supported'.
        Calling an incomplete campaign NOT SUPPORTED would report a missing run
        as evidence against the prediction, which is exactly the error the
        pre-registration exists to prevent."""
        total = total or len(SEEDS)
        if agree >= bar:
            return "SUPPORTED"
        if agree + (total - have) < bar:
            return "NOT SUPPORTED"
        return f"PENDING ({have}/{total} seeds in; needs {bar - agree} more)"

    print("\nREGISTERED PREDICTIONS")
    d = paired("realism_oldlanes", "realism_reallanes", 16500, 0)
    if d is not None:
        agree = int(np.sum(np.abs(d) < 100))
        print(f"  P1 arms agree at 16,500 within 100 veh/hr: "
              f"mean {d.mean():+,.0f}, {agree}/{len(d)} seeds  "
              f"{verdict(agree, len(d))}")
    d = paired("realism_oldlanes", "realism_reallanes", 33000, 1)
    if d is not None:
        agree = int(np.sum(d < 0))
        print(f"  P2 corrected has less stuck time at 33,000: "
              f"mean {d.mean():+,.0f} veh-h, {agree}/{len(d)} seeds  "
              f"{verdict(agree, len(d))}")

    a = "realism_reallanes"
    g1 = [got[(a, 24750, s)][0] - got[(a, 16500, s)][0]
          for s in SEEDS if (a, 24750, s) in got and (a, 16500, s) in got]
    g2 = [got[(a, 33000, s)][0] - got[(a, 24750, s)][0]
          for s in SEEDS if (a, 33000, s) in got and (a, 24750, s) in got]
    if g1 and g2:
        n_sat = sum(1 for x, y in zip(g1, g2) if y < 0.5 * x)
        v = verdict(n_sat, len(g2))
        print(f"  P3 throughput still saturates (2nd gain < half the 1st): "
              f"+{np.mean(g1):,.0f} then +{np.mean(g2):,.0f} veh/hr, "
              f"{n_sat}/{len(g2)} seeds  {v}")
        if v == "NOT SUPPORTED":
            print(f"     -> P3 refuted means lane supply WAS the binding "
                  f"constraint and the capacity audit's conclusion is wrong.")

    print(f"\nCITATION RULE: 16,500 stays the cited demand whatever this shows. "
          f"The band is validation data; selecting the demand or parser that "
          f"best hits it would tune against the judging target.")


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
            print(f"{i:3d}  {j['lane_arm']:<18} n={j['n_veh']:<6} "
                  f"seed {j['seed']:<5} {j['name']}")
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
        # The lane arm is a config flag, not an mce ARM key, so set it here and
        # let run_one apply the realism stack on top. Set explicitly every task
        # so arm order can never leak between tasks in an array.
        for k, v in ARMS[job["lane_arm"]].items():
            setattr(config, k, v)
        mce.run_one(job, g, checkpoint=False)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
