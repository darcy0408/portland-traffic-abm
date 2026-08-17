"""End-to-end check that the corrected lane counts survive into the network the
simulation actually drives on.

src/lanes_real.py proved the parser works in isolation. This runs the real
generate.prepare_network() on the widened metro graph and reads `n_lanes` back
off the edges, which is the value the car-following and MOBIL code consumes.
It runs no simulation.

Three configurations, so the wiring is visible rather than assumed:
  base            LANES_ENABLED off  -> every edge single file (committed spec)
  lanes (old)     LANES_ENABLED on, LANES_REAL off
  lanes (fixed)   LANES_ENABLED on, LANES_REAL on

Usage: python src/verify_lane_wiring.py
"""
import collections
import os
import sys

import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import generate
import lanes_real

GRAPH = os.path.join(config.NETWORK_DIR, config.LANES_REAL_GRAPH)
POWELL = ("Southeast Powell Boulevard", "SE Powell Blvd")


def names(d):
    v = d.get("name")
    return [str(x) for x in (v if isinstance(v, list) else [v]) if x is not None]


def run(G, lanes_on, real_on):
    config.LANES_ENABLED = lanes_on
    config.MOBIL_ENABLED = False
    config.LANES_REAL = real_on
    generate.prepare_network(G)

    dist = collections.Counter()
    powell = []
    total = 0
    for _u, _v, d in G.edges(data=True):
        n = d["n_lanes"]
        dist[n] += 1
        total += n
        if any(nm in POWELL for nm in names(d)):
            powell.append(n)
    p = sorted(powell)
    return dist, total, (p[len(p) // 2] if p else 0), len(p)


def main():
    print(f"loading {GRAPH}")
    G = ox.load_graphml(GRAPH)
    print(f"{G.number_of_edges():,} directed edges\n")

    hdr = f"{'configuration':<22}{'lane-km of supply':>19}{'Powell lanes':>14}{'lane histogram'}"
    print(hdr)
    print("-" * 96)
    for label, lanes_on, real_on in (("base (single file)", False, False),
                                     ("lanes, old parser", True, False),
                                     ("lanes, corrected", True, True)):
        dist, total, p_med, p_n = run(G, lanes_on, real_on)
        hist = "  ".join(f"{k}:{v:,}" for k, v in sorted(dist.items()))
        print(f"{label:<22}{total:>19,}{p_med:>14}   {hist}")
    print(f"\nPowell edges matched: {p_n}")
    print("real observed Powell directional peak: 1,400 to 1,745 veh/hr")
    print(f"one lane at the model's 50% green split: "
          f"{1 * config.WEBSTER_SAT_FLOW * 0.5:,.0f} veh/hr")
    print(f"two lanes at the model's 50% green split: "
          f"{2 * config.WEBSTER_SAT_FLOW * 0.5:,.0f} veh/hr")


if __name__ == "__main__":
    main()
