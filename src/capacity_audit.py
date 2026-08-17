"""Audit how much road capacity the model actually gives the metro network.

Read-only. Runs no simulation. Answers one question: when LANES_ENABLED is on,
how many lanes does each street actually get, and where does that fall short of
the real road?

Three things can silently cap capacity below reality:
  1. an edge with no OSM 'lanes' tag falls back to 1 lane;
  2. config.LANES_MAX clamps every edge, including freeways that really do
     carry more than that per direction;
  3. the two-way halving rule floors odd tags (a 3-lane two-way street becomes
     1 per direction, not 1.5).

Usage: python src/capacity_audit.py [path-to-graphml]
"""
import collections
import os
import sys

import osmnx as ox

# make sibling modules importable whether run from repo root or from src/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import generate

DEFAULT_GRAPH = r"C:\dev\pta-realism\data\network\graph_metro20k_orca.graphml"

# Real per-direction lane counts for the classes that carry the metro's traffic.
# Sourced from ODOT/PBOT roadway descriptions of the Portland freeways and
# arterials, used here only as a yardstick for the audit, never as a model input.
REAL_TYPICAL = {
    "motorway": 3, "motorway_link": 1, "trunk": 2, "trunk_link": 1,
    "primary": 2, "primary_link": 1, "secondary": 2, "secondary_link": 1,
    "tertiary": 1, "residential": 1, "unclassified": 1,
}


def tag_of(d):
    """Primary highway class for an edge whose tag may be a merged list."""
    h = d.get("highway")
    if isinstance(h, list):
        h = h[0] if h else "unknown"
    return str(h)


def main(path):
    print(f"loading {path}")
    G = ox.load_graphml(path)
    print(f"{G.number_of_nodes():,} nodes, {G.number_of_edges():,} directed edges\n")

    # Measure the real function, not a reimplementation of it.
    config.LANES_ENABLED = True

    per_class = collections.defaultdict(
        lambda: {"n": 0, "tagged": 0, "lanes": 0, "clamped": 0, "uncapped": 0}
    )
    for _u, _v, d in G.edges(data=True):
        cls = tag_of(d)
        row = per_class[cls]
        row["n"] += 1
        if d.get("lanes") is not None:
            row["tagged"] += 1

        n_lanes = generate._parse_lanes(d)
        row["lanes"] += n_lanes

        # Same rules with the clamp lifted, to isolate what LANES_MAX costs.
        saved, config.LANES_MAX = config.LANES_MAX, 99
        n_uncapped = generate._parse_lanes(d)
        config.LANES_MAX = saved
        row["uncapped"] += n_uncapped
        if n_uncapped > n_lanes:
            row["clamped"] += 1

    print(f"LANES_MAX = {config.LANES_MAX}\n")
    hdr = f"{'class':<16}{'edges':>9}{'% tagged':>10}{'mean lanes':>12}{'if uncapped':>13}{'clamped':>9}{'real':>7}"
    print(hdr)
    print("-" * len(hdr))

    tot = collections.Counter()
    for cls, row in sorted(per_class.items(), key=lambda kv: -kv[1]["n"]):
        if row["n"] < 50 and cls not in REAL_TYPICAL:
            continue
        real = REAL_TYPICAL.get(cls, "")
        print(f"{cls:<16}{row['n']:>9,}{100 * row['tagged'] / row['n']:>9.1f}%"
              f"{row['lanes'] / row['n']:>12.2f}{row['uncapped'] / row['n']:>13.2f}"
              f"{row['clamped']:>9,}{str(real):>7}")
    for row in per_class.values():
        for k, v in row.items():
            tot[k] += v

    print("-" * len(hdr))
    print(f"{'ALL':<16}{tot['n']:>9,}{100 * tot['tagged'] / tot['n']:>9.1f}%"
          f"{tot['lanes'] / tot['n']:>12.2f}{tot['uncapped'] / tot['n']:>13.2f}"
          f"{tot['clamped']:>9,}")

    # The headline: how much of the network is stuck at a single lane, and how
    # much of that is a real one-lane street versus a missing tag.
    single = sum(1 for _u, _v, d in G.edges(data=True)
                 if generate._parse_lanes(d) == 1)
    untagged = sum(1 for _u, _v, d in G.edges(data=True) if d.get("lanes") is None)
    print(f"\nedges the model gives exactly 1 lane: {single:,} "
          f"({100 * single / tot['n']:.1f}%)")
    print(f"edges with no OSM 'lanes' tag at all:  {untagged:,} "
          f"({100 * untagged / tot['n']:.1f}%)")

    # Arterials are where the volume is, so call them out separately.
    art = ("motorway", "trunk", "primary", "secondary")
    a_n = a_single = a_tagged = 0
    for _u, _v, d in G.edges(data=True):
        if tag_of(d) not in art:
            continue
        a_n += 1
        a_tagged += d.get("lanes") is not None
        a_single += generate._parse_lanes(d) == 1
    print(f"\narterial + freeway edges: {a_n:,}; tagged {100 * a_tagged / a_n:.1f}%; "
          f"given 1 lane {a_single:,} ({100 * a_single / a_n:.1f}%)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GRAPH)
