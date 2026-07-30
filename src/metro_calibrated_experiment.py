"""The calibrated real-demand experiment at METRO scale (CALIBRATED_DEMAND_PLAN
Phase 3/4) -- the run the corridor diagnosis said is required, built for Orca.

WHY METRO: the corridor Phases 0-2 (Jul 27-28, recorded in the plan) proved no
corridor-scale lever reaches Powell's real 1,400-1,745 veh/hr band robustly:
the 1.5 km extract is MISSING inner Powell's real signals (OSM hole -- the
metro graph carries 29 signalized Powell intersections), and its gravity/cordon
demand cannot deliver Powell-shaped through-flow. The metro graph has both the
real signals and, with LODES OD on, real origin-destination demand structure.

THE EXPERIMENT: {base, realism} x demand levels x seeds, one simulated hour
each (plus two full-DAY runs -- Christof's twice-made ask):
  base     the committed metro20k model (single-lane, uniform signals) -- the
           control every prior number came from.
  realism  the full gated stack: MOBIL explicit lanes + driver heterogeneity +
           Webster per-node timing + green-wave coordination along Powell.
Measured per run (all opt-in accumulators, all provably inert off):
  pollution (per-second NOx -> idling counts), cars-on-corridor (Powell
  vehicle-hours), cars-stuck (stuck_sum: vehicle-time below 5 km/h, MEASURED),
  and validation said plainly: busiest Powell segment veh/hr vs the real band.

DISCIPLINE (CLAUDE.md): metro overrides live visibly here (config.py already
describes metro20k; restating them makes this file self-contained against
config drift); every run has a unique RUN_NAME so nothing is overwritten; the
seed is set explicitly per run and recorded in the name; one sim per process.
Array tasks on Orca write DIFFERENT files, so parallel tasks respect the
one-writer-per-file rule.

GRAPH GUARD: the metro jobs REFUSE to run on a corridor-sized graph (the local
data/network/graph.graphml is the 1.5 km corridor, 2,838 edges, despite the
metro config -- an easy footgun). Cache the metro graph first (--cache-graph,
on Orca). --smoke deliberately uses the small local graph to prove the code
path end to end and is labeled non-authoritative.

Usage:
    python src/metro_calibrated_experiment.py --count        # hour-job count
    python src/metro_calibrated_experiment.py --list         # hour-job list
    python src/metro_calibrated_experiment.py --list-day     # day-job list
    python src/metro_calibrated_experiment.py --task N       # one hour job (SLURM)
    python src/metro_calibrated_experiment.py --day-task N   # one day job (SLURM)
    python src/metro_calibrated_experiment.py --smoke        # tiny local code-path proof
    python src/metro_calibrated_experiment.py --cache-graph  # download+cache metro graph
"""
import argparse
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osmnx as ox

import config
import generate

# --- the metro baseline shared by every run ---------------------------------
# Restated visibly even though the checked-in config.py already says metro20k:
# the harness must keep meaning THIS experiment if config.py later drifts.
METRO = {
    "STUDY_RADIUS_M": 20000,
    "N_STEPS": 3600,                    # one simulated hour (day jobs override)
    "THROUGH_TRAFFIC_FRACTION": 0.15,   # metro a-priori re-derivation (config.py)
    "DEMAND_GRAVITY": True,
    "DEMAND_LODES_OD": True,            # real Census OD -- the metro-scale lever
    "LANES_ENABLED": False,             # the frictionless model stays OFF here;
                                        # realism uses MOBIL (real friction) instead
}

# the two arms. base = the committed model every prior metro number came from;
# realism = every gated feature from the traffic-realism branch, together.
ARMS = {
    "base": {},
    "realism": {
        "MOBIL_ENABLED": True,           # explicit per-car lanes, real OSM counts
        "DRIVER_HETEROGENEITY": True,    # per-vehicle IDM draws
        "WEBSTER_ENABLED": True,         # per-node signal timing from measured flows
        "WEBSTER_GREENWAVE_ENABLED": True,  # coordination along Powell (29 real
                                            # signalized Powell nodes in this graph)
    },
}

# seeds: same 8 as the corridor lane-pollution grid, mean +/- spread not one draw
SEEDS = [42, 7, 13, 99, 2024, 314, 777, 8]

# demand levels: the a-priori metro scaling (config.py: 16,500) and 1.5x / 2x.
# The corridor showed demand STRUCTURE, not volume, was the binding constraint;
# these levels ask whether metro demand structure carries the real Powell band
# at plausible totals -- the calibration probe Phase 2 could not do at 1.5 km.
DEMANDS = [16500, 24750, 33000]

# day runs (Christof's ask): 24 simulated hours, first seed, both arms. LODES
# is commute-shaped, so a flat-demand day is an acknowledged caveat -- the run
# answers "does the model survive and what accumulates over a day", not "is
# 3 AM realistic".
DAY_STEPS = 86400
DAY_SEED = SEEDS[0]
DAY_DEMAND = DEMANDS[0]

# a corridor graph is ~2,838 edges; any metro-scale graph is tens of thousands.
# Below this the metro jobs refuse to run (see GRAPH GUARD in the docstring).
MIN_METRO_EDGES = 10_000


def build_jobs():
    """Hour-job list; index == SLURM array task id. arms x DEMANDS x SEEDS."""
    jobs = []
    for seed in SEEDS:
        for n in DEMANDS:
            for arm in ARMS:
                jobs.append({"arm": arm, "seed": seed, "n_veh": n,
                             "steps": METRO["N_STEPS"],
                             "name": f"metrocal_{arm}_n{n}_s{seed}"})
    return jobs


def build_day_jobs():
    """Day-job list; index == SLURM array task id for the day array."""
    return [{"arm": arm, "seed": DAY_SEED, "n_veh": DAY_DEMAND,
             "steps": DAY_STEPS,
             "name": f"metrocal_day_{arm}_n{DAY_DEMAND}_s{DAY_SEED}"}
            for arm in ARMS]


def _powell_edges(G):
    """(u,v,k) of edges whose OSM name contains 'Powell' -- the validation
    corridor (same matcher as lane_pollution_experiment.py)."""
    out = []
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        names = nm if isinstance(nm, list) else [nm]
        if any(n and "powell" in str(n).lower() for n in names):
            out.append((u, v, k))
    return out


def run_one(job, graph_file, checkpoint=False, min_edges=MIN_METRO_EDGES):
    """Run one job: apply overrides, seed, simulate with BOTH opt-in
    accumulators on, save, and print the Phase 3 one-line summary. The parquet
    on disk is the artifact; the readout script reads them all."""
    for k, v in METRO.items():
        setattr(config, k, v)
    for k, v in ARMS[job["arm"]].items():
        setattr(config, k, v)
    # and the arm's complement OFF, so arm order can never leak between tasks
    for other in ARMS.values():
        for k in other:
            if k not in ARMS[job["arm"]]:
                setattr(config, k, False)
    config.N_VEHICLES = job["n_veh"]
    config.N_STEPS = job["steps"]
    config.RANDOM_SEED = job["seed"]
    config.RUN_NAME = job["name"]

    out = os.path.join(config.PROCESSED_DIR, f"{job['name']}_segments.parquet")
    if os.path.exists(out):
        print(f"SKIP {job['name']} (already on disk)")
        return

    # fresh graph each run: prepare_network mutates edge attrs in place
    G = ox.load_graphml(graph_file)
    if G.number_of_edges() < min_edges:
        raise SystemExit(
            f"graph at {graph_file} has {G.number_of_edges()} edges -- that is "
            f"corridor-sized, not metro. Cache the metro graph first "
            f"(--cache-graph on Orca); refusing to mislabel a corridor run.")
    generate.set_seeds(config.RANDOM_SEED)
    speed_stats, stuck_stats = {}, {}
    totals, nox, thru = generate.run_simulation(
        G, verbose=False, use_checkpoint=checkpoint,
        speed_stats=speed_stats, stuck_stats=stuck_stats)
    generate.save_results(totals, nox, thru, speed_stats, stuck_stats)

    powell = _powell_edges(G)
    hours = config.N_STEPS * config.DT / 3600.0
    powell_nox = sum(nox.get(e, 0.0) for e in powell)
    total_nox = sum(nox.values())
    # throughput counts full traversals over the whole run; per-hour for the
    # validation sentence ("model carries X vs real 1,400-1,745")
    busiest_powell = max((thru.get(e, 0.0) for e in powell), default=0.0) / hours
    powell_veh_h = sum(totals.get(e, 0.0) for e in powell) / 3600.0
    stuck = stuck_stats["stuck_sum"]
    powell_stuck_h = sum(stuck.get(e, 0.0) for e in powell) / 3600.0
    net_stuck_h = sum(stuck.values()) / 3600.0
    print(f"{job['name']:34s}  busiest Powell {busiest_powell:5.0f} veh/hr | "
          f"Powell {powell_veh_h:6.1f} veh-h ({powell_stuck_h:6.1f} stuck) | "
          f"network stuck {net_stuck_h:7.1f} veh-h | "
          f"NOx Powell {powell_nox:7.0f} g / total {total_nox:8.0f} g")

    # per-run summary JSON: the headline numbers computed HERE, from the graph
    # this run actually used. The readout aggregates these, so it needs neither
    # the (Orca-side) metro graph nor a Powell matcher of its own.
    summary = dict(job, n_powell_edges=len(powell), sim_hours=hours,
                   busiest_powell_veh_hr=busiest_powell,
                   powell_veh_h=powell_veh_h, powell_stuck_veh_h=powell_stuck_h,
                   network_stuck_veh_h=net_stuck_h,
                   powell_nox_g=powell_nox, total_nox_g=total_nox,
                   graph_edges=G.number_of_edges())
    with open(os.path.join(config.PROCESSED_DIR,
                           f"{job['name']}_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)


def cache_graph():
    """One-time metro graph download+cache (run on Orca after cloning). Uses
    generate.get_network(), i.e. the same call every run uses, at the metro
    config -- so the cache IS what the jobs will load. NOTE: a fresh OSM
    download is today's OSM, not the Jul 6-7 Colab cache behind the M20.*
    numbers; this experiment stands on its own graph and never re-cites M20."""
    for k, v in METRO.items():
        setattr(config, k, v)
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if os.path.exists(graph_file):
        G = ox.load_graphml(graph_file)
        print(f"already cached: {graph_file} ({G.number_of_edges():,} edges)")
    else:
        print(f"downloading {config.STUDY_RADIUS_M / 1000:.0f} km drive network "
              f"around {config.STUDY_CENTER} (several minutes)...")
        G = generate.get_network()
        print(f"cached {graph_file}: {G.number_of_nodes():,} nodes, "
              f"{G.number_of_edges():,} edges")
    n_powell = len(_powell_edges(G))
    print(f"{n_powell} Powell edges in graph"
          + ("" if n_powell else "  <-- WRONG GRAPH? Powell missing"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", action="store_true", help="hour-job count")
    ap.add_argument("--count-day", action="store_true", help="day-job count")
    ap.add_argument("--list", action="store_true", help="hour-job list")
    ap.add_argument("--list-day", action="store_true", help="day-job list")
    ap.add_argument("--task", type=int, help="run one hour job (SLURM array id)")
    ap.add_argument("--day-task", type=int, help="run one day job (SLURM array id)")
    ap.add_argument("--smoke", action="store_true",
                    help="tiny non-authoritative code-path proof on the local graph")
    ap.add_argument("--cache-graph", action="store_true",
                    help="download+cache the metro graph (one-time, on Orca)")
    args = ap.parse_args()

    jobs, day_jobs = build_jobs(), build_day_jobs()
    if args.count:
        print(len(jobs)); return
    if args.count_day:
        print(len(day_jobs)); return
    if args.list:
        for i, j in enumerate(jobs):
            print(f"{i:3d}  {j['name']}")
        print(f"\n{len(jobs)} hour jobs = {len(SEEDS)} seeds x {len(DEMANDS)} "
              f"demands x {len(ARMS)} arms")
        return
    if args.list_day:
        for i, j in enumerate(day_jobs):
            print(f"{i:3d}  {j['name']}  ({j['steps']} steps)")
        return
    if args.cache_graph:
        cache_graph(); return

    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        raise SystemExit(f"no cached graph at {graph_file}; run --cache-graph "
                         f"first (do NOT download mid-experiment)")

    if args.task is not None:
        # hour jobs: no checkpoint -- short runs in a big batch, unique names
        run_one(jobs[args.task], graph_file, checkpoint=False)
    elif args.day_task is not None:
        # day jobs: 24x longer, so crash recovery IS worth the checkpoint I/O
        run_one(day_jobs[args.day_task], graph_file, checkpoint=True)
    elif args.smoke:
        # deliberately small and clearly labeled: proves the whole code path
        # (overrides + LODES + realism stack + both accumulators + save) on
        # whatever graph is cached locally. NOT a result; parquet name says smoke.
        job = {"arm": "realism", "seed": 42, "n_veh": 300, "steps": 300,
               "name": "metrocal_smoke_realism_n300_s42"}
        run_one(job, graph_file, checkpoint=False, min_edges=0)
        print("\nsmoke done (non-authoritative; delete the smoke parquet freely).")
    else:
        raise SystemExit("pick one: --count | --list | --task N | --day-task N "
                         "| --smoke | --cache-graph")


if __name__ == "__main__":
    main()
