"""Are any 'signals' sitting on freeway mainline nodes in the metro graph?

The PORTAL comparison shows the model's freeway speeds are right almost
everywhere (median model/real 0.97 over 91 stations) but collapse at a
handful of specific spots (NB I-205 at Burnside 1.7 mph vs real 56, EB US-26
at Jefferson 6.8 vs 26). A near-total standing jam at one point, with clean
flow on both sides, is the signature of a signal on the mainline: OSM tags
ramp meters and some interchange signals as highway=traffic_signals, and if
such a node touches a mainline edge the model puts a red light on a freeway.

Read-only; prints every traffic_signals node that touches a motorway edge,
with the street names around it.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osmnx as ox

import config

GRAPH = os.path.join(config.NETWORK_DIR, "graph_metro20k_lanes.graphml")


def main():
    G = ox.load_graphml(GRAPH)
    signals = {n for n, d in G.nodes(data=True)
               if "traffic_signals" in str(d.get("highway", ""))}
    print(f"traffic_signals nodes in graph: {len(signals):,}")

    hits = []
    for u, v, k, d in G.edges(keys=True, data=True):
        hw = d.get("highway")
        hw = hw[0] if isinstance(hw, list) else hw
        if str(hw) != "motorway":
            continue
        for node in (u, v):
            if node in signals:
                nm = d.get("name") or d.get("ref") or "?"
                if isinstance(nm, list):
                    nm = nm[0]
                nd = G.nodes[node]
                hits.append((node, str(nm), nd.get("y"), nd.get("x"),
                             "END" if node == v else "START"))
    seen = set()
    print(f"\nmotorway mainline edges touching a signal node: {len(hits)}")
    for node, nm, lat, lon, where in hits:
        if node in seen:
            continue
        seen.add(node)
        print(f"  node {node}  {lat:.5f},{lon:.5f}  on {nm}  ({where} of edge)")
        # what else meets this node
        for _u, _v, _k, dd in list(G.in_edges(node, keys=True, data=True)) + \
                list(G.out_edges(node, keys=True, data=True)):
            n2 = dd.get("name") or dd.get("ref") or dd.get("highway")
            if isinstance(n2, list):
                n2 = n2[0]
            print(f"      meets: {n2}")


if __name__ == "__main__":
    main()
