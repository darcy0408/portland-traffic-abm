"""Freeway closure experiment: I-205, metro scale (mentor redirect, Jul 30).

"Closing Powell is not really that interesting... closures is one thing you use
to sell your model." This runs the closure experiment the mentor asked for: shut
a stretch of I-205 and let the metro-scale demand find its way around.

Three simulations, same demand, same seed:
    fw205_open              the metro network as it is (shared baseline)
    fw205_abernethy_closed  Abernethy Bridge closed (the real ODOT precedent:
                            the nighttime closures for bridge repair; 15.2 km
                            from the study center, where demand support is thin)
    fw205_powell_closed     the stretch through the Powell/Division interchanges
                            closed (5.7 km out, the best-supported demand)

Running both stretches makes the distance-from-center tradeoff a finding
instead of a footnote: same mechanism, one where the real closure happened,
one where the model's demand is strongest.

The runs are SEQUENTIAL in one process (one simulation at a time, per the
project rule) and land in this worktree's own data/processed, so they cannot
collide with any other session's files. Checkpointing stays on: a metro run is
hours, and the unique RUN_NAMEs keep the three checkpoints separate. Remember
the known limitation: a finished run's checkpoint is never cleared, so delete
the *_checkpoint.pkl files before a deliberate rerun.

    python src/freeway_runs.py            # the real thing (hours)
    python src/freeway_runs.py --smoke    # tiny wiring check (minutes)
"""
import argparse
import json
import os
import sys

import osmnx as ox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import generate        # noqa: E402

# The two closures under test. Abernethy selects by OSM structure name. The
# Powell/Division stretch has no named structure, so it selects by a point on
# the mainline and a reach; both were verified with freeway_closure_check.py
# (composition freeway-only, local grid untouched, both diversions exist).
SCENARIOS = {
    "abernethy": {
        "ref": "I 205", "name": "Abernethy Bridge",
        "center": None, "radius_m": None, "close_ramps": True,
    },
    "powell": {
        "ref": "I 205", "name": None,
        "center": (45.4995, -122.5655), "radius_m": 900.0,
        "close_ramps": True,
    },
}

BASE = "fw205"


def fresh_graph():
    """Each run gets its own load: prepare_network and the signal pre-pass
    mutate edge attributes, and a closure removes edges. Sharing one graph
    object across runs would leak state from one into the next."""
    path = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(path):
        raise SystemExit(f"no cached graph at {path}; refusing to download "
                         f"mid-experiment (stage the metro graph first)")
    return ox.load_graphml(path)


def one_run(run_name, closure_spec, smoke):
    """One simulation: fresh graph, pinned seed, optional closure, save."""
    G = fresh_graph()
    removed = []
    if closure_spec is not None:
        removed = generate.apply_freeway_closure(G, closure_spec)
        print(f"[{run_name}] removed {len(removed)} freeway edges before routing")
    generate.set_seeds(config.RANDOM_SEED)

    config.RUN_NAME = run_name
    kw = {}
    if smoke:
        kw = {"n_vehicles": 400, "n_steps": 600, "use_checkpoint": False}
    totals, nox, thru = generate.run_simulation(G, **kw)
    generate.save_results(totals, nox, thru)

    # Bank the closed-edge list beside the results, so figures and analysis
    # mark the closure from the run's own record instead of recomputing it
    # against config (which may have moved on by then).
    if closure_spec is not None:
        out = os.path.join(config.PROCESSED_DIR, f"{run_name}_closed_edges.json")
        with open(out, "w") as f:
            json.dump({"spec": closure_spec,
                       "removed": [[u, v, k] for u, v, k in removed]}, f)
        print(f"[{run_name}] {len(removed)} closed edges recorded at {out}")
    return config.F_NO2 * sum(nox.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="tiny run to validate the wiring, numbers meaningless")
    args = ap.parse_args()

    # the seed must be the pinned one before any run whose numbers get cited
    assert config.RANDOM_SEED == 42, "pin config.RANDOM_SEED before citing this run"
    prefix = f"smoke_{BASE}" if args.smoke else BASE
    base_run = config.RUN_NAME

    results = {}
    try:
        print(f"{'=' * 66}\nRUN {prefix}_open  (shared baseline, seed 42)\n{'=' * 66}")
        results["open"] = one_run(f"{prefix}_open", None, args.smoke)

        for scen, spec in SCENARIOS.items():
            print(f"\n{'=' * 66}\nRUN {prefix}_{scen}_closed  (seed 42)\n{'=' * 66}")
            results[scen] = one_run(f"{prefix}_{scen}_closed", spec, args.smoke)
    finally:
        config.RUN_NAME = base_run

    print(f"\n{'=' * 66}\nNetwork-total NO2, g (spatial shift is the point, "
          f"not the total):")
    for name, no2 in results.items():
        rel = ""
        if name != "open" and results.get("open"):
            rel = f"  ({100 * (no2 - results['open']) / results['open']:+.1f}% vs open)"
        print(f"  {name:12s} {no2:10.1f}{rel}")


if __name__ == "__main__":
    main()
