"""One seeded corridor run with Webster signal timing (Phase 4 payoff readout).

This is the deliberate run decision deferred since Phase 4 increment 2a shipped:
Webster per-node timing has only ever been exercised by scenario gates plus a
short read-only smoke (250 vehicles / 200 steps, where every node clamped to the
30 s minimum cycle at that low demand). This script produces the first FULL
authoritative hour with WEBSTER_ENABLED, at CORRIDOR scale, so the readout can
answer two questions at once:

  1. verification -- do the per-node cycles actually SPREAD at real demand
     (500 vehicles), or is the smoke's all-clamped-to-30s behavior demand-
     independent? Any pathology in a full run?
  2. payoff -- how does per-node Webster timing shift segment volumes and
     speeds vs the uniform 60 s / 50-50 signal (the committed base model)?

The comparator is the existing realism_base_segments.parquet (Jul 24, same
seed, same corridor overrides, same code path -- the 2a wiring is proven
bit-identical with the flag off by src/kernel_regression.py, so that base run
is still exactly what today's kernel produces with no flags). Because the
Webster measurement pre-pass runs on its OWN RNG stream (RANDOM_SEED + 11),
this run drives the byte-for-byte same vehicle population as realism_base --
only the signal timing differs -- so per-segment deltas are cleanly paired.

Discipline (CLAUDE.md): single process, one simulation at a time; the seed is
pinned (config.RANDOM_SEED = 42, asserted below); the RUN_NAME is new so
nothing already on disk can be overwritten (asserted below); the readout only
ever READS what this writes.

Config overrides: the checked-in config.py carries the metro20k settings; this
run overrides back to the corridor baseline VISIBLY HERE (same override block
as src/realism_runs.py), so config.py keeps honestly describing the metro run.

Besides the parquet, this script dumps the Webster plans themselves
(per-node cycle/split, clearance, measured approach flows) to
data/processed/realism_webster_plans.json for the readout. The dump comes from
a side pass that replays exactly what run_simulation does internally -- valid
because _measure_approach_flows seeds its own private RNG stream, so the side
pass and the in-run pre-pass compute identical flows and hence identical plans.

Run it:  python src/webster_runs.py            (~2 min: warmup pre-pass x2 + hour)
"""
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osmnx as ox

import config
import generate


# corridor-baseline overrides, identical to src/realism_runs.py (see its docstring)
CORRIDOR = {
    "STUDY_RADIUS_M": 1500,            # must match the cached corridor graph
    "N_VEHICLES": 500,                 # the 1.5 km baseline vehicle count
    "N_STEPS": 3600,                   # one simulated hour
    "THROUGH_TRAFFIC_FRACTION": 0.30,  # the powell_through corridor setting
    "DEMAND_LODES_OD": False,          # corridor OD is too thin (config.py caveat)
    "DEMAND_GRAVITY": True,
    "LANES_ENABLED": False,            # isolate Webster: no lane flags
    "DRIVER_HETEROGENEITY": False,
    "MOBIL_ENABLED": False,
    "WEBSTER_ENABLED": True,           # the one flag under test
}

RUN_NAME = "realism_webster"


def main():
    # the seed must be the pinned one before any run whose numbers get cited
    assert config.RANDOM_SEED == 42, "pin config.RANDOM_SEED before citing this run"

    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        raise SystemExit(f"no cached graph at {graph_file}; refusing to download "
                         f"mid-experiment (cache the corridor graph first)")

    # refuse to clobber an existing run of this name -- delete it deliberately
    # first if a re-run is intended (single-source-of-truth rule)
    out = os.path.join(config.PROCESSED_DIR, f"{RUN_NAME}_segments.parquet")
    if os.path.exists(out):
        raise SystemExit(f"{out} already exists; delete it first if you mean to re-run")

    for k, v in CORRIDOR.items():
        setattr(config, k, v)
    config.RUN_NAME = RUN_NAME

    # --- side pass: dump the Webster plans the run will use -----------------
    # Replays run_simulation's own sequence (prepare_network -> pre-pass ->
    # prepare_signals). The pre-pass seeds its own private RNG (RANDOM_SEED+11),
    # so these plans are byte-identical to the ones computed inside the run.
    # The mutated graph is then DISCARDED and the run gets a fresh load.
    G = ox.load_graphml(graph_file)
    generate.set_seeds(config.RANDOM_SEED)
    generate.prepare_network(G)
    flows = generate._measure_approach_flows(G, config.N_VEHICLES,
                                             config.WEBSTER_WARMUP_STEPS)
    signals = generate.prepare_signals(G, flows=flows)
    plans = {
        "run": RUN_NAME,
        "seed": config.RANDOM_SEED,
        "warmup_steps": config.WEBSTER_WARMUP_STEPS,
        "clearance_s": signals["clearance"],
        "n_signals": len(signals["nodes"]),
        "tagged": signals["tagged"],
        # JSON keys must be strings; node ids are OSM ints
        "node_cycle": {str(n): c for n, c in signals["node_cycle"].items()},
        "node_split": {str(n): s for n, s in signals["node_split"].items()},
        "offset": {str(n): signals["offset"][n] for n in signals["nodes"]},
        "flows_veh_h": {f"{u}|{v}|{k}": f for (u, v, k), f in flows.items()},
    }
    plans_file = os.path.join(config.PROCESSED_DIR, f"{RUN_NAME}_plans.json")
    with open(plans_file, "w") as fh:
        json.dump(plans, fh, indent=1)
    cyc = list(signals["node_cycle"].values())
    print(f"plans dumped to {plans_file}: {len(cyc)} nodes, "
          f"cycle {min(cyc):.0f}-{max(cyc):.0f}s")

    # --- the authoritative run, on a FRESH graph ----------------------------
    print(f"\n{'=' * 66}\nRUN {RUN_NAME}  (WEBSTER_ENABLED, corridor, seed 42)\n{'=' * 66}")
    G = ox.load_graphml(graph_file)
    generate.set_seeds(config.RANDOM_SEED)
    speed_stats = {}                     # opt-in: filled by run_simulation
    totals, nox, thru = generate.run_simulation(G, speed_stats=speed_stats)
    generate.save_results(totals, nox, thru, speed_stats)

    print("\nSaved. Compare against realism_base_segments.parquet (same seed, "
          "same population -- only the signal timing differs).")


if __name__ == "__main__":
    main()
