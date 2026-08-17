"""What lane-related OSM tags does the cached metro graph actually carry?

Read-only. The audit showed 56.6% of arterial and freeway edges get exactly one
lane. Before fixing that we need to know which better tags survived into the
graph: lanes:forward / lanes:backward give the true directional split, and
turn:lanes tells us about dedicated turn pockets at intersections.

If a tag is absent here it was dropped by the OSMnx download filter, not missing
from OSM, so the fix may be a re-download with a wider useful_tags_way list.

Usage: python src/lane_tag_survey.py [path-to-graphml]
"""
import collections
import os
import sys

import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_GRAPH = r"C:\dev\pta-realism\data\network\graph_metro20k_orca.graphml"

ARTERIAL = ("motorway", "trunk", "primary", "secondary", "tertiary")


def tag_of(d):
    h = d.get("highway")
    if isinstance(h, list):
        h = h[0] if h else "unknown"
    return str(h)


def main(path):
    G = ox.load_graphml(path)
    edges = list(G.edges(data=True))
    print(f"{len(edges):,} directed edges\n")

    # Every attribute key present anywhere, ranked by how many edges carry it.
    keys = collections.Counter()
    for _u, _v, d in edges:
        keys.update(d.keys())
    print("attributes present on the graph:")
    for k, n in keys.most_common():
        print(f"  {k:<24}{n:>9,}  ({100 * n / len(edges):.1f}%)")

    # The specific tags a proper directional lane count needs.
    print("\nlane-relevant tags, on arterial and freeway edges only:")
    art = [d for _u, _v, d in edges if tag_of(d) in ARTERIAL]
    for k in ("lanes", "lanes:forward", "lanes:backward", "turn:lanes",
              "turn:lanes:forward", "oneway", "maxspeed", "junction", "width"):
        n = sum(1 for d in art if d.get(k) is not None)
        print(f"  {k:<24}{n:>9,}  ({100 * n / len(art):.1f}% of {len(art):,})")

    # Two-way arterials with an ODD lanes tag are the ones the halving rule
    # floors: lanes=3 becomes 1 per direction when the truth is 2 and 1.
    odd = twoway = 0
    for d in art:
        raw = d.get("lanes")
        if raw is None:
            continue
        vals = raw if isinstance(raw, list) else [raw]
        try:
            n = min(int(float(str(x))) for x in vals)
        except ValueError:
            continue
        ow = d.get("oneway")
        if isinstance(ow, list):
            ow = ow[0]
        if str(ow).strip().lower() not in ("yes", "true", "1", "-1"):
            twoway += 1
            if n % 2:
                odd += 1
    print(f"\ntwo-way tagged arterials: {twoway:,}; of those an ODD lane tag "
          f"(floored by the halving rule): {odd:,} ({100 * odd / max(twoway, 1):.1f}%)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GRAPH)
