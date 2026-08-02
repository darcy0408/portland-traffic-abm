"""Phase B1 x B3 at metro scale: do turn pockets and non-work demand move the
peak-hour ceiling, and do they interact?

WHY THIS EXISTS SEPARATELY. Both features shipped gated and unrun (Jul 31,
Aug 1). Neither could get an arm in metro_calibrated_experiment.ARMS, because
build_jobs indexes SLURM array tasks by arm order and inserting one renumbers
the 48 existing jobs -- so B1/B3 get their own harness, exactly the way the
realism-stack ablation did.

THE GRID: a 2x2 factorial on top of the FULL realism stack, 3 new arms x 8
seeds = 24 one-hour jobs at the untuned a-priori demand (16,500):
  pockets   realism + TURN_POCKETS_ENABLED     (B1: left-turners leave the
            through queue where OSM says a dedicated left lane exists)
  nonwork   realism + DEMAND_NONWORK_ENABLED   (B3: 64% of local trips end at
            consumer-facing service jobs on a shorter decay, not at commutes)
  both      realism + both                     (the interaction: B1 relieves
            turn dams, B3 changes WHERE the turns are)
The CONTROL is not re-run. It already exists as the Jul 29
metrocal_realism_n16500_s* results -- same graph, same demand, same 8 seeds,
same steps, both flags off -- and the readout joins them in. That reuse is only
legitimate because both features are proved INERT when off (bitwise, including
the RNG stream: turn_pocket_scenarios flag-off inertness, nonwork_scenarios
share-0/no-layer inertness, and kernel_regression bit-identical after both
edits). If either inertness proof ever breaks, this control must be re-run.

WHY ON THE REALISM STACK, not the base model: B1 REQUIRES MOBIL_ENABLED (a
pocket is a claim about lane identity, and only the explicit-lane model has
one), and the Jul 31 ablation showed lane-changing is what carries the model
into the real ODOT Powell band at all. Adding B1/B3 to a base model would
measure them on a model that is already out of band.

WHAT TO EXPECT, so the result is read honestly:
  - B1's effect is BOUNDED by how often turn destinations are congested: this
    kernel has no opposing-traffic gap acceptance, so a left-turner onto a
    clear street blocks nobody. Permitted-left conflict is Phase B2's job.
  - B1 runs on a metro sidecar where 61% of tagged edges are merged-osmid,
    credited under an any-way rule that can only ADD pockets. State the pocket
    count with any B1 result and treat the effect as an upper bound.
  - B3's headline is not busiest-Powell at all: it changes WHERE cars go, so
    the payoff measure is agreement with the held-out counts, which is a
    LOCAL, read-only step over the saved segments parquets (validate_traffic
    path) -- never re-run here. This harness reports the band/stuck table.

DISCIPLINE (CLAUDE.md): reuses metro_calibrated_experiment.run_one unchanged
(unique RUN_NAME per job, per-job seed, one writer per file, SKIP on existing
parquet, metro graph guard). Every parameter a-priori; nothing tuned to the
held-out PBOT counts or the ODOT band.

Usage:
    python src/metro_b13_experiment.py --check     # prerequisites, BEFORE submitting
    python src/metro_b13_experiment.py --count     # job count (SLURM array size)
    python src/metro_b13_experiment.py --list      # job list
    python src/metro_b13_experiment.py --task N    # run one job (SLURM)
    python src/metro_b13_experiment.py --smoke     # tiny local code-path proof
    python src/metro_b13_experiment.py --readout   # aggregate table (local, read-only)
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

# the full realism stack every arm here sits on top of (the Jul 29 "realism"
# arm, verbatim -- referenced rather than retyped so the two can never drift)
REALISM = dict(mce.ARMS["realism"])

# the two new feature flags, named once
B1_FLAG = "TURN_POCKETS_ENABLED"
B3_FLAG = "DEMAND_NONWORK_ENABLED"

# 2x2 minus the control (which is metrocal_realism, already on disk)
B13_ARMS = {
    "pockets": dict(REALISM, **{B1_FLAG: True}),
    "nonwork": dict(REALISM, **{B3_FLAG: True}),
    "both":    dict(REALISM, **{B1_FLAG: True, B3_FLAG: True}),
}

# validity guard: B1 refuses to run without MOBIL (generate.py raises), so
# catch a malformed arm here rather than 24 SLURM tasks in
for _name, _arm in B13_ARMS.items():
    if _arm.get(B1_FLAG) and not _arm.get("MOBIL_ENABLED"):
        raise SystemExit(f"arm {_name} enables turn pockets without MOBIL")

# register with the shared runner so run_one's arm lookup AND its complement-off
# loop (which iterates every registered arm) see these flags -- without this,
# a task could inherit the previous job's B1/B3 setting
mce.ARMS.update(B13_ARMS)

DEMAND = 16500          # the untuned a-priori level -- where the band claim lives
SEEDS = mce.SEEDS       # same 8 pinned seeds as metrocal and the ablation
CONTROL_LABEL = "control (metrocal realism)"


def build_jobs():
    """Job list; index == SLURM array task id. 3 arms x 8 seeds = 24."""
    jobs = []
    for seed in SEEDS:
        for arm in B13_ARMS:
            jobs.append({"arm": arm, "seed": seed, "n_veh": DEMAND,
                         "steps": mce.METRO["N_STEPS"],
                         "name": f"b13_{arm}_n{DEMAND}_s{seed}"})
    return jobs


def check():
    """Verify every prerequisite BEFORE cluster time is spent. Both features
    refuse loudly at run time by design, but discovering that in 24 failed
    SLURM tasks is a waste; this says so in one second."""
    import turn_lanes
    import landuse_data
    ok = True

    # apply the metro overrides first: the sidecar is keyed by STUDY_RADIUS_M,
    # so checking at the default radius would check the wrong file
    for k, v in mce.METRO.items():
        setattr(config, k, v)

    path = turn_lanes.sidecar_path()
    sidecar = turn_lanes.load_sidecar()
    if sidecar is None:
        print(f"  MISSING  turn:lanes sidecar at {path}")
        print(f"           build: python src/turn_lanes.py --build --graph "
              f"data/network/graph.graphml")
        ok = False
    else:
        print(f"  ok       turn:lanes sidecar: {len(sidecar['ways']):,} ways, "
              f"fetched {sidecar['meta']['fetched_utc']} at "
              f"{sidecar['meta']['radius_m']} m")

    try:
        lu = landuse_data.service_landuse_table()
        print(f"  ok       service jobs: {len(lu)} block groups, "
              f"{int(lu['service_jobs'].sum()):,} consumer-facing jobs "
              f"(share {config.NONWORK_TRIP_SHARE}, decay "
              f"{config.NONWORK_DECAY_SCALE_M:.0f} m)")
    except Exception as e:
        print(f"  MISSING  service-jobs table: {e}")
        print(f"           needs data/raw/or_wac_{config.LODES_YEAR}.csv.gz "
              f"and cenpop2020_bg_or.txt")
        ok = False

    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        print(f"  MISSING  graph at {graph_file} (--cache-graph on Orca)")
        ok = False
    else:
        size_mb = os.path.getsize(graph_file) / 1e6
        note = "" if size_mb > 10 else "  <-- corridor-sized? metro jobs will refuse"
        print(f"  ok       graph: {graph_file} ({size_mb:.0f} MB){note}")

    # the control the readout joins: 8 seeds of metrocal realism at this demand
    ctrl = [p for p in glob.glob(os.path.join(
        config.PROCESSED_DIR, f"metrocal_realism_n{DEMAND}_s*_summary.json"))
        if "smoke" not in p]
    print(f"  {'ok      ' if ctrl else 'MISSING '} control on disk: "
          f"{len(ctrl)} metrocal_realism_n{DEMAND} summaries (want {len(SEEDS)}; "
          f"the readout joins these as the both-flags-off arm)")
    if not ctrl:
        ok = False

    print(f"\n{'READY' if ok else 'NOT READY'}: {len(build_jobs())} jobs "
          f"({len(B13_ARMS)} arms x {len(SEEDS)} seeds) at n={DEMAND}")
    return ok


def readout():
    """Aggregate table from saved *_summary.json files (read-only, local).
    Joins the Jul 29 metrocal realism runs as the both-flags-off control."""
    import numpy as np
    rows = {}
    for path in glob.glob(os.path.join(config.PROCESSED_DIR, "b13_*_summary.json")):
        with open(path) as f:
            s = json.load(f)
        if "smoke" in s["name"]:
            continue
        rows.setdefault(s["arm"], []).append(s)
    for path in glob.glob(os.path.join(
            config.PROCESSED_DIR, f"metrocal_realism_n{DEMAND}_s*_summary.json")):
        with open(path) as f:
            s = json.load(f)
        if s["name"].startswith("metrocal_day") or "smoke" in s["name"]:
            continue
        rows.setdefault(CONTROL_LABEL, []).append(s)

    order = [CONTROL_LABEL, "pockets", "nonwork", "both"]
    print(f"B1 x B3 at n={DEMAND}, mean +/- SD over seeds "
          f"(real ODOT band 1,400-1,745 veh/hr)")
    print(f"{'arm':28s} {'n':>2s} {'busiest Powell':>18s} {'net stuck veh-h':>18s}")
    stats = {}
    for arm in order:
        if arm not in rows:
            print(f"{arm:28s}  - (no results yet)")
            continue
        b = np.array([s["busiest_powell_veh_hr"] for s in rows[arm]])
        st = np.array([s["network_stuck_veh_h"] for s in rows[arm]])
        stats[arm] = (b, st)
        flag = "IN BAND" if 1400 <= b.mean() <= 1745 else ""
        sd_b = b.std(ddof=1) if len(b) > 1 else float("nan")
        sd_s = st.std(ddof=1) if len(st) > 1 else float("nan")
        print(f"{arm:28s} {len(b):2d} {b.mean():8.0f} +/- {sd_b:4.0f} "
              f"{st.mean():10.0f} +/- {sd_s:5.0f}  {flag}")

    # paired deltas vs the control, seed by seed: the seeds are pinned and
    # shared, so pairing removes the seed-to-seed spread that swamps a small
    # effect in the unpaired means above (the closure work learned this the
    # hard way -- single-seed diffs jitter enormously)
    if CONTROL_LABEL in rows:
        ctrl = {s["seed"]: s for s in rows[CONTROL_LABEL]}
        print(f"\nPAIRED vs control, same seed (mean +/- SD of the difference):")
        for arm in ("pockets", "nonwork", "both"):
            if arm not in rows:
                continue
            pairs = [(s["busiest_powell_veh_hr"]
                      - ctrl[s["seed"]]["busiest_powell_veh_hr"],
                      s["network_stuck_veh_h"]
                      - ctrl[s["seed"]]["network_stuck_veh_h"])
                     for s in rows[arm] if s["seed"] in ctrl]
            if not pairs:
                continue
            d_b = np.array([p[0] for p in pairs])
            d_s = np.array([p[1] for p in pairs])
            sd_b = d_b.std(ddof=1) if len(d_b) > 1 else float("nan")
            sd_s = d_s.std(ddof=1) if len(d_s) > 1 else float("nan")
            print(f"  {arm:12s} n={len(pairs)}  Powell {d_b.mean():+7.0f} +/- "
                  f"{sd_b:5.0f} veh/hr   stuck {d_s.mean():+8.0f} +/- "
                  f"{sd_s:6.0f} veh-h")
        print("\n  NOTE: busiest-Powell is B1's measure, not B3's. B3 changes")
        print("  WHERE cars go; its payoff is agreement with the held-out")
        print("  counts, read locally from the saved segments parquets.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="verify prerequisites before submitting")
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--task", type=int)
    ap.add_argument("--smoke", action="store_true",
                    help="tiny non-authoritative code-path proof on the local graph")
    ap.add_argument("--readout", action="store_true")
    args = ap.parse_args()

    jobs = build_jobs()
    if args.check:
        sys.exit(0 if check() else 1)
    if args.count:
        print(len(jobs)); return
    if args.list:
        for i, j in enumerate(jobs):
            flags = " ".join(sorted(k for k, v in B13_ARMS[j["arm"]].items()
                                    if v and k in (B1_FLAG, B3_FLAG)))
            print(f"{i:3d}  {j['name']:32s} {flags}")
        print(f"\n{len(jobs)} jobs = {len(SEEDS)} seeds x {len(B13_ARMS)} arms"
              f"\ncontrol NOT re-run: metrocal_realism_n{DEMAND}_s* (already on disk)")
        return
    if args.readout:
        readout(); return
    if args.smoke:
        # every arm once, tiny, on whatever graph is cached locally: proves the
        # flag plumbing (pockets + non-work together, through run_one's
        # complement-off loop) end to end. Names carry "smoke" so no readout
        # ever counts them.
        graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
        for arm in B13_ARMS:
            job = {"arm": arm, "seed": 42, "n_veh": 120, "steps": 120,
                   "name": f"b13_smoke_{arm}"}
            mce.run_one(job, graph_file, min_edges=0)
            # FLAG ISOLATION, checked not assumed: every arm here runs in ONE
            # process, so a flag left set by the previous arm would silently
            # mislabel a run. run_one's complement-off loop is supposed to
            # prevent that; this asserts it actually did, for both new flags.
            want = B13_ARMS[arm]
            for flag in (B1_FLAG, B3_FLAG):
                got = getattr(config, flag)
                if bool(got) != bool(want.get(flag, False)):
                    raise SystemExit(
                        f"FLAG LEAK: after arm '{arm}', {flag} is {got} but the "
                        f"arm wants {bool(want.get(flag, False))} -- run_one's "
                        f"complement-off loop did not clear it")
            print(f"  flag isolation OK for '{arm}': "
                  f"{B1_FLAG}={getattr(config, B1_FLAG)}, "
                  f"{B3_FLAG}={getattr(config, B3_FLAG)}")
        print("smoke OK: all B1xB3 arms ran end to end, no flag leaked "
              "between arms (non-authoritative)")
        return
    if args.task is not None:
        graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
        mce.run_one(jobs[args.task], graph_file)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
