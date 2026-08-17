"""A real per-direction lane count for each directed edge.

Replaces generate._parse_lanes, which loses road capacity three ways (measured
by src/capacity_audit.py and src/lane_tag_survey.py on the 20 km metro graph):

  1. it never sees `lanes:forward` / `lanes:backward`, so on a two-way street it
     halves the total with integer division. A 3-lane street becomes 1 lane each
     way instead of 2 and 1, silently deleting a lane. That hits 20.6% of
     two-way tagged arterials;
  2. an edge with no `lanes` tag falls back to 1, which is right for a
     residential street and wrong for the 32% of arterials that lack the tag;
  3. a single flat LANES_MAX clamps freeways to the same ceiling as a
     neighbourhood street.

The rules here, in priority order:

  A. DIRECTIONAL TAG WINS. `lanes:forward` on the forward edge and
     `lanes:backward` on the reversed edge are OSM stating the split outright.
  B. ONE-WAY: the `lanes` tag is already this direction's count.
  C. TWO-WAY, TOTAL PRESERVED. Drop `lanes:both_ways` first (a centre turn lane
     is shared and carries no through traffic), then split what is left. When
     the remainder is odd the extra lane goes to the forward edge, so the two
     directions sum to exactly the tagged total. This is the fix for cause 1:
     the old rule floored both directions and threw the odd lane away.
  D. UNTAGGED: impute the MEDIAN directional count of the edges of the same
     highway class that ARE tagged, in this same graph. The imputation comes
     from the map itself, not from a guess and not from the held-out PBOT
     traffic counts, so the validation test stays independent.

Lanes reserved for buses, transit or HOV are subtracted where OSM marks them,
because they do not carry general traffic.

Every count is finally clamped by CLASS_CAP, so a freeway may be wide and a
residential street may not.

Run standalone to see the before/after table:
    python src/lanes_real.py [path-to-graphml]
"""
import collections
import os
import statistics
import sys

import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# NOTE: `generate` is imported inside main() only. generate.py imports this
# module to build its lane counts, so importing it back at module scope would
# be circular. main() needs it purely to print the old parser for comparison.

DEFAULT_GRAPH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "network", "graph_metro20k_lanes.graphml")

# Per-direction ceiling by road class. Replaces the single flat LANES_MAX, whose
# value of 3 clamped 100 of the 438 freeway edges on this network. These are
# generous physical bounds meant only to stop a mistagged edge running away, not
# calibration targets: nothing here was fitted to any traffic count.
CLASS_CAP = {
    "motorway": 6, "motorway_link": 3,
    "trunk": 5, "trunk_link": 2,
    "primary": 4, "primary_link": 2,
    "secondary": 3, "secondary_link": 2,
    "tertiary": 2, "tertiary_link": 2,
    "residential": 2, "unclassified": 2, "living_street": 1, "service": 1,
}
DEFAULT_CAP = 2


def _tag_list(v):
    return v if isinstance(v, list) else [v]


def _as_int(v):
    """First readable integer in a tag value, else None. OSM lane tags can be
    lists (from merged ways) or strings like '2' or malformed junk."""
    vals = []
    for x in _tag_list(v):
        if x is None:
            continue
        try:
            vals.append(int(float(str(x).strip())))
        except ValueError:
            continue          # unreadable piece, e.g. a 'turn:lanes' word list
    return min(vals) if vals else None      # bottleneck rule for merged edges


def _is_reversed(d):
    r = d.get("reversed")
    if isinstance(r, list):
        r = r[0] if r else False
    return str(r).strip().lower() in ("true", "1", "yes")


def _is_oneway(d):
    o = d.get("oneway")
    if isinstance(o, list):
        o = o[0] if o else False
    return str(o).strip().lower() in ("true", "1", "yes", "-1")


def highway_class(d):
    h = d.get("highway")
    if isinstance(h, list):
        h = h[0] if h else "unknown"
    return str(h)


def _reserved_lanes(d):
    """Lanes OSM marks as EXCLUSIVE to buses/transit/HOV, which carry no general
    traffic. The `*:lanes` tags are pipe-delimited per-lane strings, one slot per
    lane. Only `designated` means the lane is reserved; `yes` merely means the
    mode is permitted there, which most general-traffic lanes are. Counting
    `yes` as reserved wrongly stripped two of Division's three lanes, where the
    FX bus line runs in shared lanes."""
    n = 0
    for key in ("bus:lanes", "psv:lanes", "hov:lanes"):
        raw = d.get(key)
        if raw is None:
            continue
        for piece in _tag_list(raw):
            n += sum(1 for slot in str(piece).split("|")
                     if slot.strip() == "designated")
    return n


def class_medians(G):
    """Median directional lane count per highway class, over the edges that
    carry a usable tag. This is the imputation source for untagged edges."""
    seen = collections.defaultdict(list)
    for _u, _v, d in G.edges(data=True):
        n = _tagged_directional(d)
        if n is not None:
            seen[highway_class(d)].append(n)
    return {cls: int(statistics.median(v)) for cls, v in seen.items() if v}


def _tagged_directional(d):
    """This direction's lane count from tags ALONE (rules A to C), or None if
    the edge carries no usable lane tag."""
    # A. OSM states the split for this direction outright.
    key = "lanes:backward" if _is_reversed(d) else "lanes:forward"
    n = _as_int(d.get(key))
    if n is not None:
        return max(n, 1)

    total = _as_int(d.get("lanes"))
    if total is None:
        return None

    # B. one-way: the tag already describes this direction only.
    if _is_oneway(d):
        return max(total, 1)

    # C. two-way: drop the shared centre turn lane, then split the remainder so
    # the two directions sum back to the tagged total instead of flooring both.
    both = _as_int(d.get("lanes:both_ways")) or 0
    through = max(total - both, 2)
    half, odd = divmod(through, 2)
    return max(half + (odd if not _is_reversed(d) else 0), 1)


def directional_lanes(d, medians=None):
    """Per-direction general-traffic lane count for one directed edge."""
    n = _tagged_directional(d)
    cls = highway_class(d)
    if n is None:                                   # D. impute from the map
        n = (medians or {}).get(cls, 1)
    n -= _reserved_lanes(d)
    return max(1, min(n, CLASS_CAP.get(cls, DEFAULT_CAP)))


# --- standalone report ------------------------------------------------------

def main(path):
    import generate                            # comparison only; see note above

    print(f"loading {path}")
    G = ox.load_graphml(path)
    print(f"{G.number_of_nodes():,} nodes, {G.number_of_edges():,} directed edges")

    medians = class_medians(G)
    print("\nimputation medians (from tagged edges of the same class):")
    for cls, m in sorted(medians.items(), key=lambda kv: -kv[1]):
        print(f"  {cls:<18}{m}")

    config.LANES_ENABLED = True                     # measure the real old path
    config.LANES_REAL = False                       # ...without this module in it
    rows = collections.defaultdict(lambda: {"n": 0, "old": 0, "new": 0})
    old_single = new_single = 0
    for _u, _v, d in G.edges(data=True):
        cls = highway_class(d)
        o = generate._parse_lanes(d)
        n = directional_lanes(d, medians)
        r = rows[cls]
        r["n"] += 1
        r["old"] += o
        r["new"] += n
        old_single += (o == 1)
        new_single += (n == 1)

    hdr = f"{'class':<16}{'edges':>9}{'old mean':>10}{'new mean':>10}{'change':>9}"
    print("\n" + hdr)
    print("-" * len(hdr))
    tot = collections.Counter()
    for cls, r in sorted(rows.items(), key=lambda kv: -kv[1]["n"]):
        if r["n"] < 100:
            continue
        o, n = r["old"] / r["n"], r["new"] / r["n"]
        print(f"{cls:<16}{r['n']:>9,}{o:>10.2f}{n:>10.2f}{n - o:>+9.2f}")
    for r in rows.values():
        for k, v in r.items():
            tot[k] += v
    print("-" * len(hdr))
    o, n = tot["old"] / tot["n"], tot["new"] / tot["n"]
    print(f"{'ALL':<16}{tot['n']:>9,}{o:>10.2f}{n:>10.2f}{n - o:>+9.2f}")

    print(f"\ntotal directional lane-count across the network: "
          f"{tot['old']:,} -> {tot['new']:,} (+{100 * (tot['new'] - tot['old']) / tot['old']:.1f}%)")
    print(f"edges stuck at exactly 1 lane: {old_single:,} -> {new_single:,}")

    art = ("motorway", "trunk", "primary", "secondary")
    a = [d for _u, _v, d in G.edges(data=True) if highway_class(d) in art]
    ao = sum(generate._parse_lanes(d) for d in a)
    an = sum(directional_lanes(d, medians) for d in a)
    a1o = sum(1 for d in a if generate._parse_lanes(d) == 1)
    a1n = sum(1 for d in a if directional_lanes(d, medians) == 1)
    print(f"\narterial + freeway ({len(a):,} edges): mean lanes "
          f"{ao / len(a):.2f} -> {an / len(a):.2f}; "
          f"stuck at 1 lane {a1o:,} ({100 * a1o / len(a):.1f}%) -> "
          f"{a1n:,} ({100 * a1n / len(a):.1f}%)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GRAPH)
