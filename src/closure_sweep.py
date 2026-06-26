"""Closure sweep: robustness across seeds (#1) and generality across scenarios (#2).

A single closure under one random seed is an anecdote. This runs the closure
experiment across several seeds and across three different arterials, so we can
report the redistribution as a stable mean with spread (it is not seed noise) and
show it generalizes (it is a method, not a one-off).

The iron rule on this project: ONE simulation at a time, never two processes
writing the same data files. So every run here is serial, in this one process, and
each writes its own distinctly-named files (sweep_<scenario>_<seed>_open / _closed).
It reuses the real kernel via generate.run_closure_experiment; it does not
reimplement anything. closure_robustness.py reads these files and reports.

Run:  python src/closure_sweep.py     (~6-8 minutes; safe to run in the background)
"""
import os
import sys
import json

import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import generate

# Six seeds for the robustness spread. 42 is the project default (the cited run);
# the rest are arbitrary fixed values so the sweep itself is reproducible.
SEEDS = [42, 7, 13, 21, 99, 2024]

# Three scenarios: close a block of each of three parallel arterials in turn. Powell
# is the headline; Division and Holgate are the routes Powell's traffic detours onto,
# so closing THEM should push traffic back the other way. The center of each is
# resolved from the cached graph by street name (below) so the zone always lands on a
# real road instead of a hand-guessed coordinate.
SCENARIO_STREETS = {
    "powell": "Powell",
    "division": "Division",
    "holgate": "Holgate",
}
CLOSURE_RADIUS_M = 150.0
MANIFEST = os.path.join(config.PROCESSED_DIR, "sweep_manifest.json")


def _name_matches(data, target):
    name = data.get("name")
    if name is None:
        return False
    names = name if isinstance(name, list) else [name]
    return any(target.lower() in str(n).lower() for n in names)


def resolve_center(G, target):
    """Pick a closure center on the named street: the midpoint of the matching edge
    closest to the study center, so the zone sits well inside the network rather than
    at a boundary. Returns (lat, lon) or None if the street is not in this network."""
    lat0, lon0 = config.STUDY_CENTER
    best, best_d = None, float("inf")
    for u, v, _k, data in G.edges(keys=True, data=True):
        if not _name_matches(data, target):
            continue
        mlat = 0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"]))
        mlon = 0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"]))
        d = generate._haversine_m(lat0, lon0, mlat, mlon)
        if d < best_d:
            best, best_d = (mlat, mlon), d
    return best


def main():
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))

    # Resolve each scenario's closure zone and confirm it actually closes segments.
    scenarios = {}
    for key, street in SCENARIO_STREETS.items():
        if key == "powell":
            center = (config.CLOSURE[0], config.CLOSURE[1])   # the known headline zone
        else:
            center = resolve_center(G, street)
        if center is None:
            print(f"[skip] '{street}' not found in this network")
            continue
        zone = (center[0], center[1], CLOSURE_RADIUS_M)
        n_closed = len(generate.closed_edges_in_zone(G, zone))
        if n_closed == 0:
            print(f"[skip] '{street}' zone closes 0 segments")
            continue
        scenarios[key] = {"street": street, "zone": zone, "n_closed": n_closed}
        print(f"[scenario] {key:9s} {street:9s} center=({center[0]:.5f}, {center[1]:.5f}) "
              f"closes {n_closed} segments")

    manifest = {"seeds": SEEDS, "scenarios": scenarios, "radius_m": CLOSURE_RADIUS_M}
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nWrote manifest {MANIFEST}\n")

    total = len(scenarios) * len(SEEDS)
    done = 0
    # Save and restore the real config so the sweep leaves no trace in the defaults.
    saved = (config.RANDOM_SEED, config.CLOSURE, config.RUN_NAME)
    try:
        for key, info in scenarios.items():
            for seed in SEEDS:
                done += 1
                config.RANDOM_SEED = seed
                config.CLOSURE = info["zone"]
                config.RUN_NAME = f"sweep_{key}_{seed}"
                print(f"=== ({done}/{total}) scenario={key} seed={seed} ===")
                generate.run_closure_experiment(G)
    finally:
        config.RANDOM_SEED, config.CLOSURE, config.RUN_NAME = saved

    print(f"\nSweep complete: {total} closure experiments "
          f"({len(scenarios)} scenarios x {len(SEEDS)} seeds). "
          f"Analyze with: python src/closure_robustness.py")


if __name__ == "__main__":
    main()
