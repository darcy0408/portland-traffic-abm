"""OSM turn:lanes as a SIDECAR, for turn pockets (real-demand plan Phase B1).

WHY A SIDECAR. B1 models left-turn pockets, and it needs to know which
approaches have a dedicated left-turn lane. OSM carries that as `turn:lanes`
(e.g. 'left||' on a 3-lane arterial = a left-only lane plus two unmarked
lanes), but OSMnx's default `useful_tags_way` does NOT request it, so neither
cached graph has it -- verified Jul 31: zero turn-ish attributes on the 2,838
edge corridor graph AND the 159,425 edge metro graph, while an 800 m probe
with the tag requested found 10 of 33 Powell edges carrying one.

Re-downloading the graphs with the tag added would fix that and BREAK graph
identity: `graph_metro20k_orca.graphml` is the exact graph behind the Jul 29-31
metrocal and ablation numbers, and a fresh download is today's OSM. So this
module fetches the tag SEPARATELY and stores it keyed by OSM WAY ID, which is
graph-independent: the cached graphs are never rewritten, and the same sidecar
joins onto any graph covering the area.

WHAT A LEFT POCKET IS HERE. `turn:lanes` is a '|'-separated list, one token per
lane, leftmost first ('left|none|none', 'left;through|through', 'none|right').
A token of exactly 'left' is a DEDICATED left-turn lane -- the pocket. A shared
token like 'left;through' is NOT a pocket: that lane still carries through
traffic, so a left-turner in it dams the lane, which is the very failure B1
exists to model. That distinction is the whole point, so it is applied strictly.

DIRECTION. A cached-graph edge is directed. OSM tags a two-way street's turn
lanes per direction (`turn:lanes:forward` / `:backward`) and a one-way street's
with the unqualified `turn:lanes`. OSMnx marks an edge that runs AGAINST its
way's OSM direction with reversed=True, so: reversed edges read :backward,
forward edges read :forward, and either falls back to the unqualified tag.

MERGED EDGES. OSMnx simplification can merge several ways into one edge, whose
`osmid` is then a list. Such an edge is credited with a pocket if ANY of its
ways has one; the coverage report counts these separately so the ambiguity is
visible rather than assumed away. It is not small -- 64 of 163 tagged corridor
edges are merged -- and the rule can only ever ADD pockets, never remove them,
so it biases B1 toward MORE turn-pocket relief. Any B1 result therefore states
the pocket count it ran with, and treats the effect size as an upper-ish bound
on what these tags support.

Usage:
    python src/turn_lanes.py --build          # fetch + write the sidecar
    python src/turn_lanes.py --report         # coverage of an existing sidecar
    python src/turn_lanes.py --build --graph data/network/graph_metro20k_orca.graphml
"""
import argparse
import json
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osmnx as ox

import config

# the tags OSMnx must be told to keep; the default useful_tags_way has none
TURN_TAGS = ("turn:lanes", "turn:lanes:forward", "turn:lanes:backward")


def sidecar_path(radius_m=None):
    """Sidecar file for a study radius. Keyed by radius because that is what
    determines the fetched extent; the contents are way ids, so any graph of
    the same area can join against it."""
    r = config.STUDY_RADIUS_M if radius_m is None else radius_m
    return os.path.join(config.NETWORK_DIR, f"turn_lanes_{int(r)}m.json")


def has_left_pocket(value):
    """True if this turn:lanes value declares a DEDICATED left-turn lane.

    A lane token of exactly 'left' is dedicated. 'left;through' is shared and
    is NOT a pocket (a left-turner there still blocks the through movement).
    Accepts a string or a list of strings (OSMnx yields a list when several
    source ways disagree); a list counts if any member declares one."""
    if value is None:
        return False
    if isinstance(value, (list, tuple)):
        return any(has_left_pocket(v) for v in value)
    return any(tok.strip() == "left" for tok in str(value).split("|"))


def fetch_way_tags(center=None, radius_m=None, network_type=None, verbose=True):
    """Download the study area with the turn tags REQUESTED, and return
    {way_id: {tag: value}} for every way that carries one.

    Only the tags are kept -- the downloaded graph is thrown away, so this can
    never be confused with, or overwrite, the cached simulation graph."""
    center = config.STUDY_CENTER if center is None else center
    radius_m = config.STUDY_RADIUS_M if radius_m is None else radius_m
    network_type = config.NETWORK_TYPE if network_type is None else network_type

    original = list(ox.settings.useful_tags_way)
    try:
        missing = [t for t in TURN_TAGS if t not in original]
        ox.settings.useful_tags_way = original + missing
        if verbose:
            print(f"fetching {radius_m / 1000:.1f} km around {center} with "
                  f"{len(missing)} extra tag(s) requested...")
        G = ox.graph_from_point(center, dist=radius_m, network_type=network_type)
    finally:
        # always restore: leaving this set would silently change what a later
        # get_network() call downloads and caches
        ox.settings.useful_tags_way = original

    ways = {}
    for _u, _v, _k, d in G.edges(keys=True, data=True):
        present = {t: d[t] for t in TURN_TAGS if t in d}
        if not present:
            continue
        osmid = d.get("osmid")
        for wid in (osmid if isinstance(osmid, list) else [osmid]):
            # a way seen twice (both directions of a two-way street) carries
            # the same tags; merging is a no-op except for partial coverage
            ways.setdefault(str(wid), {}).update(present)
    if verbose:
        n_left = sum(1 for tags in ways.values()
                     if any(has_left_pocket(v) for v in tags.values()))
        print(f"  {len(ways):,} ways carry a turn tag; {n_left:,} declare a "
              f"dedicated left lane")
    return ways


def save_sidecar(ways, path=None, radius_m=None, center=None):
    """Write the sidecar with provenance (what was fetched, when, from where)."""
    path = sidecar_path(radius_m) if path is None else path
    meta = {
        "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "center": list(config.STUDY_CENTER if center is None else center),
        "radius_m": config.STUDY_RADIUS_M if radius_m is None else radius_m,
        "network_type": config.NETWORK_TYPE,
        "tags": list(TURN_TAGS),
        "osmnx_version": ox.__version__,
        "note": ("OSM turn:lanes keyed by way id. Fetched separately so the "
                 "cached simulation graphs are never re-downloaded or "
                 "rewritten; join by osmid."),
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"meta": meta, "ways": ways}, f, indent=1, sort_keys=True)
    return path


def load_sidecar(path=None, radius_m=None):
    """Load a sidecar, or None if it has not been built for this radius."""
    path = sidecar_path(radius_m) if path is None else path
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def edge_turn_value(data, ways):
    """The turn:lanes value that applies to ONE directed graph edge, or None.

    Direction: an edge with reversed=True runs against its way's OSM direction,
    so it reads `turn:lanes:backward`; a forward edge reads `:forward`; both
    fall back to the unqualified `turn:lanes` (how one-ways are tagged)."""
    rev = data.get("reversed")
    # graphml round-trips booleans as strings; lists appear on merged edges
    if isinstance(rev, (list, tuple)):
        rev = rev[0]
    reversed_edge = str(rev).lower() == "true"
    order = (("turn:lanes:backward", "turn:lanes") if reversed_edge
             else ("turn:lanes:forward", "turn:lanes"))
    osmid = data.get("osmid")
    for wid in (osmid if isinstance(osmid, list) else [osmid]):
        tags = ways.get(str(wid))
        if not tags:
            continue
        for tag in order:
            if tag in tags:
                return tags[tag]
    return None


def left_pocket_edges(G, sidecar):
    """{(u, v, k): True} for every directed edge with a dedicated left-turn
    lane at its downstream end. Empty dict if the sidecar is missing."""
    if not sidecar:
        return {}
    ways = sidecar["ways"]
    return {(u, v, k): True for u, v, k, d in G.edges(keys=True, data=True)
            if has_left_pocket(edge_turn_value(d, ways))}


def report(G, sidecar):
    """Print join coverage: how much of THIS graph the sidecar actually
    reaches, including the merged-edge ambiguity, so the number is trusted
    for what it is rather than assumed complete."""
    if not sidecar:
        print("no sidecar built yet -- run with --build")
        return
    ways = sidecar["ways"]
    print(f"sidecar: {len(ways):,} tagged ways, fetched "
          f"{sidecar['meta']['fetched_utc']} at "
          f"{sidecar['meta']['radius_m']} m")
    total = G.number_of_edges()
    tagged = pockets = merged_tagged = 0
    for _u, _v, _k, d in G.edges(keys=True, data=True):
        val = edge_turn_value(d, ways)
        if val is None:
            continue
        tagged += 1
        if isinstance(d.get("osmid"), list):
            merged_tagged += 1
        if has_left_pocket(val):
            pockets += 1
    print(f"graph edges: {total:,}")
    print(f"  with a turn:lanes value joined: {tagged:,} "
          f"({100 * tagged / total:.1f}%)")
    print(f"  with a DEDICATED left pocket:   {pockets:,} "
          f"({100 * pockets / total:.1f}%)")
    print(f"  of those tagged, merged-osmid edges (any-way rule applied): "
          f"{merged_tagged:,}")

    powell = [(u, v, k, d) for u, v, k, d in G.edges(keys=True, data=True)
              if any(n and "powell" in str(n).lower()
                     for n in (d.get("name") if isinstance(d.get("name"), list)
                               else [d.get("name")]))]
    p_tag = sum(1 for *_x, d in powell if edge_turn_value(d, ways) is not None)
    p_pkt = sum(1 for *_x, d in powell
                if has_left_pocket(edge_turn_value(d, ways)))
    print(f"Powell edges: {len(powell)}  tagged {p_tag}  with left pocket {p_pkt}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true",
                    help="fetch turn tags from OSM and write the sidecar")
    ap.add_argument("--report", action="store_true",
                    help="join an existing sidecar onto the graph and report")
    ap.add_argument("--graph", default=None,
                    help="graph to join against (default: the cached graph)")
    ap.add_argument("--radius", type=int, default=None,
                    help="fetch radius in m (default: config.STUDY_RADIUS_M)")
    args = ap.parse_args()

    graph_file = args.graph or os.path.join(config.NETWORK_DIR, "graph.graphml")
    if args.build:
        ways = fetch_way_tags(radius_m=args.radius)
        path = save_sidecar(ways, radius_m=args.radius)
        print(f"wrote {path}")
    if args.report or args.build:
        if not os.path.exists(graph_file):
            raise SystemExit(f"no graph at {graph_file}")
        G = ox.load_graphml(graph_file)
        print(f"\njoining onto {graph_file}")
        report(G, load_sidecar(radius_m=args.radius))
    if not (args.build or args.report):
        raise SystemExit("pick one: --build | --report")


if __name__ == "__main__":
    main()
