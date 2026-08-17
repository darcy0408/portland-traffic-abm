"""Where does the capacity ceiling actually come from: lanes, or green time?

The network-wide lane correction (src/lanes_real.py) moved mean arterial lanes
only 1.50 -> 1.60, far too little to close the gap between the model's ~1,070
veh/hr ceiling and Powell's real 1,400-1,745 veh/hr. So this asks the question
on the specific streets that matter, using the standard signalized-approach
capacity identity:

    capacity (veh/hr) = lanes x saturation flow x green fraction

with the HCM saturation flow of 1,900 veh/hr/lane already in config
(WEBSTER_SAT_FLOW). The model currently assumes a 50 percent green split at
every signal. A real coordinated arterial gives its major approach far more.

Printing capacity under each assumption shows which term is short.

Usage: python src/corridor_capacity.py [path-to-graphml]
"""
import collections
import os
import sys

import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import lanes_real

DEFAULT_GRAPH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "network", "graph_metro20k_lanes.graphml")

SAT = config.WEBSTER_SAT_FLOW          # 1,900 veh/hr/lane, HCM standard

# The corridors the project actually cites, plus the freeways the closure work
# depends on. Matched on the OSM name/ref tag.
CORRIDORS = {
    "SE Powell (US 26)":  ("Southeast Powell Boulevard", "SE Powell Blvd"),
    "SE Division":        ("Southeast Division Street", "SE Division St"),
    "SE Holgate":         ("Southeast Holgate Boulevard", "SE Holgate Blvd"),
    "SE Foster":          ("Southeast Foster Road", "SE Foster Rd"),
}
FREEWAYS = {"I-5": "I 5", "I-205": "I 205", "I-84": "I 84", "I-405": "I 405"}

# Powell's real directional peak, from the ODOT count already in the ledger.
REAL_BAND = (1400, 1745)


def names(d):
    out = []
    for key in ("name", "ref"):
        v = d.get(key)
        if v is None:
            continue
        out.extend(str(x) for x in (v if isinstance(v, list) else [v]))
    return out


def main(path):
    G = ox.load_graphml(path)
    medians = lanes_real.class_medians(G)
    config.LANES_ENABLED = True
    import generate

    def report(label, matcher, green_now=0.50, green_real=0.50):
        lanes_old, lanes_new, n = [], [], 0
        for _u, _v, d in G.edges(data=True):
            if not matcher(d):
                continue
            n += 1
            lanes_old.append(generate._parse_lanes(d))
            lanes_new.append(lanes_real.directional_lanes(d, medians))
        if not n:
            print(f"{label:<20} no edges matched")
            return
        # The binding constraint on a corridor is its narrowest signalized
        # stretch, so report the median rather than the mean.
        lo = sorted(lanes_old)[len(lanes_old) // 2]
        ln = sorted(lanes_new)[len(lanes_new) // 2]
        cap_old = lo * SAT * green_now
        cap_new = ln * SAT * green_real
        print(f"{label:<20}{n:>6}{lo:>8}{ln:>8}{cap_old:>12,.0f}{cap_new:>13,.0f}")

    print(f"saturation flow {SAT:,.0f} veh/hr/lane; model green split 50%\n")
    hdr = (f"{'corridor':<20}{'edges':>6}{'lanes':>8}{'lanes':>8}"
           f"{'cap @50%':>12}{'cap @70%':>13}")
    print(hdr)
    print(f"{'':<20}{'':>6}{'(old)':>8}{'(new)':>8}{'(old lanes)':>12}{'(new lanes)':>13}")
    print("-" * len(hdr))
    for label, pats in CORRIDORS.items():
        report(label, lambda d, p=pats: any(nm in p for nm in names(d)),
               green_now=0.50, green_real=0.70)
    print("-" * len(hdr))
    print(f"Powell's real observed directional peak: "
          f"{REAL_BAND[0]:,} to {REAL_BAND[1]:,} veh/hr\n")

    # Freeways are unsignalized, so their capacity is lanes x per-lane capacity
    # (HCM basic freeway segment, ~2,200 veh/hr/lane at 60+ mph), no green term.
    FREE_LANE_CAP = 2200
    print(f"{'freeway':<20}{'edges':>6}{'lanes':>8}{'lanes':>8}"
          f"{'cap (old)':>12}{'cap (new)':>13}")
    print("-" * len(hdr))
    for label, ref in FREEWAYS.items():
        lo_l, ln_l, n = [], [], 0
        for _u, _v, d in G.edges(data=True):
            if ref not in names(d):
                continue
            if lanes_real.highway_class(d) not in ("motorway", "trunk"):
                continue
            n += 1
            lo_l.append(generate._parse_lanes(d))
            ln_l.append(lanes_real.directional_lanes(d, medians))
        if not n:
            print(f"{label:<20} no edges matched")
            continue
        lo = sorted(lo_l)[len(lo_l) // 2]
        ln = sorted(ln_l)[len(ln_l) // 2]
        print(f"{label:<20}{n:>6}{lo:>8}{ln:>8}"
              f"{lo * FREE_LANE_CAP:>12,.0f}{ln * FREE_LANE_CAP:>13,.0f}")
    print(f"\n(freeway per-lane capacity {FREE_LANE_CAP:,} veh/hr, HCM basic segment)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GRAPH)
