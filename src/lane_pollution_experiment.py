"""Lane-count vs pollution MAGNITUDE experiment (for the Aug 14 talk).

The question Christof actually cares about (not the rank correlation): when the
model uses realistic multi-lane capacity, what happens to the POLLUTION -- the
actual amount and where it is? The single-lane model caps every segment near
~1,070 veh/h, below Powell's real 1,400-1,745 peak, so it UNDER-COUNTS pollution
on the busiest corridors (it physically can't put enough cars on them). This
script measures that, two ways, across many seeds:

  Framing A  "capacity undercount": at a HIGH fixed demand where the 1-lane cap
             bites, one-lane vs real-lane-count (LANES_ENABLED). Expect: pollution
             RISES on the multi-lane corridors that can now carry their real
             traffic (and falls on the reroute paths); network total ~conserved
             because demand is fixed -- the honest "redistributed, not created."
  Framing B  "traffic growth": with real lanes on, sweep demand up (rush-hour
             buildup). Expect: total pollution RISES and concentrates at the
             congested signals -- more cars queuing and discharging = more NOx.

Both framings are run across SEEDS so we can report a mean +/- spread, not a
single-seed number (the standing weakness Christof flagged).

DISCIPLINE (CLAUDE.md): corridor overrides live visibly here (config.py still
describes the metro run); every run has a unique RUN_NAME so nothing on disk is
overwritten; the seed is set explicitly per run and recorded in the name; runs
are sequential in one process. LANES_ENABLED reads REAL OSM lane counts (209 of
2,838 corridor segments get >1 lane -- the actual arterials); it is a frictionless
virtual-lane model, an UPPER BOUND on the capacity effect (documented; MOBIL is
the realistic-friction follow-up).

HPC-READY: the runs are an independent job list. On a laptop, `--all` runs them
sequentially. On Orca (SLURM), submit an array and let each task run one job:
    sbatch --array=0-$(python src/lane_pollution_experiment.py --count) job.sh
    # inside job.sh:  python src/lane_pollution_experiment.py --task $SLURM_ARRAY_TASK_ID
Each task writes its own parquet; src/lane_pollution_readout.py reads them all.

Usage:
    python src/lane_pollution_experiment.py --count          # how many jobs
    python src/lane_pollution_experiment.py --list           # show the job list
    python src/lane_pollution_experiment.py --task 0         # run one job (SLURM)
    python src/lane_pollution_experiment.py --smoke          # 1 seed, A only (fast local check)
    python src/lane_pollution_experiment.py --all            # every job, sequential (local)
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osmnx as ox

import config
import generate

# --- corridor baseline shared by every run (see module docstring) -----------
CORRIDOR = {
    "STUDY_RADIUS_M": 1500,
    "N_STEPS": 3600,                   # one simulated hour
    "THROUGH_TRAFFIC_FRACTION": 0.30,
    "DEMAND_LODES_OD": False,
    "DEMAND_GRAVITY": True,
    "DRIVER_HETEROGENEITY": False,
    "MOBIL_ENABLED": False,            # LANES_ENABLED is the two-lane model here
    "WEBSTER_ENABLED": False,
}

# seeds: 8 for a solid mean +/- spread (was the single-seed weakness)
SEEDS = [42, 7, 13, 99, 2024, 314, 777, 8]

# Framing A: 1-lane vs real-lane at a HIGH demand where the cap bites (the lanes
# experiment showed 1-lane caps ~1,106 vs 2-lane ~1,388 at N=1200).
A_DEMAND = 1200
# Framing B: real lanes on, demand climbing toward Powell's real peak.
B_DEMANDS = [300, 600, 900, 1200, 1500]


def build_jobs():
    """The full independent job list; index == SLURM array task id."""
    jobs = []
    for seed in SEEDS:
        # Framing A -- the capacity-undercount contrast (both lane settings)
        for lanes in (False, True):
            tag = "2lane" if lanes else "1lane"
            jobs.append({"framing": "A", "seed": seed, "n_veh": A_DEMAND,
                         "lanes": lanes,
                         "name": f"lanepoll_A_{tag}_n{A_DEMAND}_s{seed}"})
        # Framing B -- growth sweep, real lanes on
        for n in B_DEMANDS:
            jobs.append({"framing": "B", "seed": seed, "n_veh": n,
                         "lanes": True,
                         "name": f"lanepoll_B_2lane_n{n}_s{seed}"})
    return jobs


def _powell_edges(G):
    """(u,v,k) of edges whose OSM name contains 'Powell' -- the busy corridor
    we expect the lane change to load up."""
    out = []
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        names = nm if isinstance(nm, list) else [nm]
        if any(n and "powell" in str(n).lower() for n in names):
            out.append((u, v, k))
    return out


def run_one(job, graph_file):
    """Run a single job: apply overrides, set the seed, simulate, save, and
    print a one-line pollution summary (total NOx, Powell-corridor NOx, busiest
    throughput). Returns nothing; the parquet on disk is the artifact."""
    for k, v in CORRIDOR.items():
        setattr(config, k, v)
    config.N_VEHICLES = job["n_veh"]
    config.LANES_ENABLED = job["lanes"]
    config.RANDOM_SEED = job["seed"]
    config.RUN_NAME = job["name"]

    out = os.path.join(config.PROCESSED_DIR, f"{job['name']}_segments.parquet")
    if os.path.exists(out):
        print(f"SKIP {job['name']} (already on disk)")
        return

    # fresh graph each run: prepare_network mutates edge attrs in place
    G = ox.load_graphml(graph_file)
    generate.set_seeds(config.RANDOM_SEED)
    totals, nox, thru = generate.run_simulation(G, verbose=False)
    generate.save_results(totals, nox, thru)

    powell = _powell_edges(G)
    powell_nox = sum(nox.get(e, 0.0) for e in powell)
    total_nox = sum(nox.values())
    busiest = max(thru.values()) if thru else 0.0
    print(f"{job['name']:34s}  total NOx {total_nox:8.0f} g | "
          f"Powell corridor NOx {powell_nox:7.0f} g | "
          f"busiest segment {busiest:5.0f} veh/hr")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", action="store_true", help="print job count and exit")
    ap.add_argument("--list", action="store_true", help="print the job list and exit")
    ap.add_argument("--task", type=int, help="run a single job by index (SLURM array)")
    ap.add_argument("--smoke", action="store_true", help="1 seed, framing A only")
    ap.add_argument("--all", action="store_true", help="run every job sequentially")
    args = ap.parse_args()

    jobs = build_jobs()
    if args.count:
        print(len(jobs))
        return
    if args.list:
        for i, j in enumerate(jobs):
            print(f"{i:3d}  {j['name']}")
        print(f"\n{len(jobs)} jobs = {len(SEEDS)} seeds x "
              f"(2 lane settings @ A + {len(B_DEMANDS)} demands @ B)")
        return

    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        raise SystemExit(f"no cached graph at {graph_file}; cache the 1.5 km "
                         f"corridor graph first (do NOT download mid-experiment)")

    if args.task is not None:
        run_one(jobs[args.task], graph_file)
    elif args.smoke:
        # framing A, first seed only: the fast local proof it works
        for j in [x for x in jobs if x["framing"] == "A" and x["seed"] == SEEDS[0]]:
            run_one(j, graph_file)
        print("\nsmoke done. Compare the two lines: 2lane should show MORE "
              "Powell-corridor NOx and a higher busiest-segment than 1lane.")
    elif args.all:
        for j in jobs:
            run_one(j, graph_file)
    else:
        raise SystemExit("pick one: --count | --list | --task N | --smoke | --all")


if __name__ == "__main__":
    main()
