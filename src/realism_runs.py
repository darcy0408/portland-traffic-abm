"""Four seeded corridor runs for the realism readout (Phases 2 + 3 payoff).

This is the deliberate run decision deferred since Phase 2 shipped: no realism
flag has ever been exercised on a full authoritative simulation, only scenario
gates and short smoke tests. This script produces that evidence, at CORRIDOR
scale (the committed 1.5 km baseline), as FOUR sequential runs of the same
seeded hour that differ only in which realism flag is on:

    realism_base     all flags off (the committed spec, re-run to carry the new
                     v_sum/v2_sum speed-moment columns the old parquets lack)
    realism_drivers  DRIVER_HETEROGENEITY on (Phase 2)
    realism_mobil    MOBIL_ENABLED on (Phase 3 explicit lanes + lane changing)
    realism_both     both on (their interaction, unmeasured until now -- and the
                     physically interesting MOBIL case, since homogeneous drivers
                     have little reason to overtake)

Discipline (CLAUDE.md): the runs are SEQUENTIAL in one process, so exactly one
simulation writes data at a time; the seed is pinned (config.RANDOM_SEED = 42,
asserted below); each run has its own RUN_NAME so nothing already on disk --
in particular the committed powell_through baseline -- can be overwritten; and
the readout (src/realism_readout.py) only ever READS the parquets this writes.

Config overrides: the checked-in config.py currently carries the metro20k
settings (20 km radius, 16.5k vehicles, LODES OD). These runs override it back
to the corridor baseline that reproduces powell_through -- 1.5 km radius (the
cached graph here IS the corridor graph; the radius must match it or the
through-traffic boundary, a fraction of the radius, would select no nodes),
500 vehicles, 3600 steps, 30% through-traffic, LODES off. FLEET_MIXED stays
True (the mentor-approved live setting): the fleet draw uses its own RNG stream
and changes emissions only, never dynamics, so it cannot touch the speed or
volume comparisons made here. Overrides live HERE, visibly, not as silent edits
to config.py, so the checked-in config still describes the metro run.

Run it:  python src/realism_runs.py            (~1-2 min per run)
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osmnx as ox

import config
import generate


# corridor-baseline overrides shared by all four runs (see module docstring)
CORRIDOR = {
    "STUDY_RADIUS_M": 1500,            # must match the cached corridor graph
    "N_VEHICLES": 500,                 # the 1.5 km baseline vehicle count
    "N_STEPS": 3600,                   # one simulated hour
    "THROUGH_TRAFFIC_FRACTION": 0.30,  # the powell_through corridor setting
    "DEMAND_LODES_OD": False,          # corridor OD is too thin (config.py caveat)
    "DEMAND_GRAVITY": True,
    "LANES_ENABLED": False,            # Phase 1 virtual lanes stay out of this matrix
}

# the run matrix: name -> the one/two flags it turns on
RUNS = [
    ("realism_base",    {"DRIVER_HETEROGENEITY": False, "MOBIL_ENABLED": False}),
    ("realism_drivers", {"DRIVER_HETEROGENEITY": True,  "MOBIL_ENABLED": False}),
    ("realism_mobil",   {"DRIVER_HETEROGENEITY": False, "MOBIL_ENABLED": True}),
    ("realism_both",    {"DRIVER_HETEROGENEITY": True,  "MOBIL_ENABLED": True}),
]


def main():
    # the seed must be the pinned one before any run whose numbers get cited
    assert config.RANDOM_SEED == 42, "pin config.RANDOM_SEED before citing these runs"

    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        raise SystemExit(f"no cached graph at {graph_file}; refusing to download "
                         f"mid-experiment (cache the corridor graph first)")

    for name, flags in RUNS:
        print(f"\n{'=' * 66}\nRUN {name}  flags: {flags}\n{'=' * 66}")
        for k, v in {**CORRIDOR, **flags}.items():
            setattr(config, k, v)
        config.RUN_NAME = name

        # a FRESH graph per run: prepare_network mutates edge attributes in
        # place, so reloading prevents any cross-run leakage through the graph
        G = ox.load_graphml(graph_file)

        generate.set_seeds(config.RANDOM_SEED)
        speed_stats = {}                     # opt-in: filled by run_simulation
        totals, nox, thru = generate.run_simulation(G, speed_stats=speed_stats)
        generate.save_results(totals, nox, thru, speed_stats)

    print("\nAll four runs saved. Read them with: python src/realism_readout.py")


if __name__ == "__main__":
    main()
