"""Realism-stack ABLATION at metro scale: which feature does the work?

The Jul 29 metrocal campaign showed the full realism stack (MOBIL + driver
heterogeneity + Webster + green-wave) reaches the real Powell band while the
base model saturates ~1,000 veh/hr. But the stack ran all-on, so the result
cannot say WHICH mechanism carries the entry into the band -- the first
question a reviewer (or Christof) asks, and a figure the journal paper needs.
Corridor-scale hints exist (Phase 2: Webster alone FAILED, MOBIL+heterogeneity
hit the band on one seed but not robustly) but were never run at metro scale,
where the answer actually matters.

THE GRID: 8 new arms x 8 seeds at the untuned a-priori demand (16,500 -- the
demand level where "realism enters the band" is the headline claim):
  singles      mobil / hetero / webster / signals (webster+green-wave)
  leave-one-out full minus each of the same four
The all-off and all-on arms are NOT re-run: they exist as the Jul 29
metrocal_base_n16500_s* / metrocal_realism_n16500_s* results (same graph, same
demand, same seeds, same steps), and the readout joins them in.

CONSTRAINT baked into the arms: WEBSTER_GREENWAVE_ENABLED without
WEBSTER_ENABLED is refused by generate.py (no per-node cycle to coordinate),
so no arm here ever has green-wave without Webster; "minus webster" therefore
also drops green-wave (leaving mobil+hetero, the corridor Phase 2 pair).

DISCIPLINE (CLAUDE.md): reuses metro_calibrated_experiment.run_one unchanged
(unique RUN_NAME per job, per-job seed, one writer per file, SKIP on existing
parquet, metro graph guard). All parameters a-priori; nothing tuned to the
held-out PBOT counts or the ODOT band.

Usage:
    python src/metro_ablation_experiment.py --count   # job count (SLURM array size)
    python src/metro_ablation_experiment.py --list    # job list
    python src/metro_ablation_experiment.py --task N  # run one job (SLURM)
    python src/metro_ablation_experiment.py --smoke   # tiny local code-path proof
    python src/metro_ablation_experiment.py --readout # aggregate table (local, read-only)
"""
import argparse
import glob
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import metro_calibrated_experiment as mce

# The four feature flags, named once. Keys are short arm-name fragments.
FLAGS = {
    "mobil": "MOBIL_ENABLED",
    "hetero": "DRIVER_HETEROGENEITY",
    "webster": "WEBSTER_ENABLED",
    "greenwave": "WEBSTER_GREENWAVE_ENABLED",
}

# Ablation arms. Singles first, then leave-one-out. green-wave never appears
# without webster (generate.py refuses that combination, correctly).
ABLATION_ARMS = {
    # singles
    "only_mobil":   {FLAGS["mobil"]: True},
    "only_hetero":  {FLAGS["hetero"]: True},
    "only_webster": {FLAGS["webster"]: True},
    "only_signals": {FLAGS["webster"]: True, FLAGS["greenwave"]: True},
    # leave-one-out from the full stack
    "no_mobil":     {FLAGS["hetero"]: True, FLAGS["webster"]: True,
                     FLAGS["greenwave"]: True},
    "no_hetero":    {FLAGS["mobil"]: True, FLAGS["webster"]: True,
                     FLAGS["greenwave"]: True},
    "no_greenwave": {FLAGS["mobil"]: True, FLAGS["hetero"]: True,
                     FLAGS["webster"]: True},
    # minus webster forces green-wave off too -> the mobil+hetero pair
    "no_signals":   {FLAGS["mobil"]: True, FLAGS["hetero"]: True},
}

# validity guard: no arm may enable green-wave without webster
for _name, _arm in ABLATION_ARMS.items():
    if _arm.get(FLAGS["greenwave"]) and not _arm.get(FLAGS["webster"]):
        raise SystemExit(f"arm {_name} has green-wave without webster")

# register with the shared runner so run_one's arm lookup and its
# complement-off loop (which iterates all registered arms) see these arms
mce.ARMS.update(ABLATION_ARMS)

DEMAND = 16500          # the untuned a-priori level -- where the claim lives
SEEDS = mce.SEEDS       # same 8 pinned seeds as metrocal


def build_jobs():
    """Job list; index == SLURM array task id. 8 arms x 8 seeds = 64."""
    jobs = []
    for seed in SEEDS:
        for arm in ABLATION_ARMS:
            jobs.append({"arm": arm, "seed": seed, "n_veh": DEMAND,
                         "steps": mce.METRO["N_STEPS"],
                         "name": f"aba_{arm}_n{DEMAND}_s{seed}"})
    return jobs


def readout():
    """Aggregate table from saved *_summary.json files (read-only, local).
    Joins the Jul 29 metrocal base/realism at the same demand as the all-off /
    all-on rows. Prints mean +/- SD of busiest-Powell and network stuck."""
    import numpy as np
    rows = {}
    for path in glob.glob(os.path.join(config.PROCESSED_DIR, "aba_*_summary.json")):
        with open(path) as f:
            s = json.load(f)
        rows.setdefault(s["arm"], []).append(s)
    for path in glob.glob(os.path.join(config.PROCESSED_DIR,
                                       f"metrocal_*_n{DEMAND}_*_summary.json")):
        with open(path) as f:
            s = json.load(f)
        if s["name"].startswith("metrocal_day_") or "smoke" in s["name"]:
            continue
        label = {"base": "all_off (metrocal base)",
                 "realism": "all_on (metrocal realism)"}[s["arm"]]
        rows.setdefault(label, []).append(s)

    order = (["all_off (metrocal base)"] + [f"only_{k}" for k in
             ("mobil", "hetero", "webster", "signals")] +
             [f"no_{k}" for k in ("mobil", "hetero", "greenwave", "signals")] +
             ["all_on (metrocal realism)"])
    print(f"ABLATION at n={DEMAND}, mean +/- SD over seeds "
          f"(real band 1,400-1,745 veh/hr)")
    print(f"{'arm':28s} {'n':>2s} {'busiest Powell':>18s} {'net stuck veh-h':>18s}")
    for arm in order:
        if arm not in rows:
            print(f"{arm:28s}  - (no results yet)")
            continue
        b = np.array([s["busiest_powell_veh_hr"] for s in rows[arm]])
        st = np.array([s["network_stuck_veh_h"] for s in rows[arm]])
        flag = "IN BAND" if 1400 <= b.mean() <= 1745 else ""
        print(f"{arm:28s} {len(b):2d} {b.mean():8.0f} +/- {b.std(ddof=1):4.0f} "
              f"{st.mean():10.0f} +/- {st.std(ddof=1):5.0f}  {flag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--task", type=int)
    ap.add_argument("--smoke", action="store_true",
                    help="tiny non-authoritative code-path proof on the local graph")
    ap.add_argument("--readout", action="store_true")
    args = ap.parse_args()

    jobs = build_jobs()
    if args.count:
        print(len(jobs)); return
    if args.list:
        for i, j in enumerate(jobs):
            print(f"{i:3d}  {j['name']}")
        print(f"\n{len(jobs)} jobs = {len(SEEDS)} seeds x {len(ABLATION_ARMS)} arms")
        return
    if args.readout:
        readout(); return
    if args.smoke:
        # every arm once, tiny, on the local corridor graph: proves the flag
        # plumbing (including webster+green-wave together) end to end. Names
        # carry "smoke" so no readout ever counts them.
        graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
        for arm in ABLATION_ARMS:
            job = {"arm": arm, "seed": 42, "n_veh": 120, "steps": 120,
                   "name": f"aba_smoke_{arm}"}
            mce.run_one(job, graph_file, min_edges=0)
        print("smoke OK: all ablation arms ran end to end (non-authoritative)")
        return
    if args.task is not None:
        graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
        mce.run_one(jobs[args.task], graph_file)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
