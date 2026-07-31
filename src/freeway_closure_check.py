"""Verify a freeway closure before spending a simulation on it.

Reads a cached graph and checks the four things that have to be true for the
scenario to mean what we say it means:

  1. COMPOSITION  the closure removes freeway edges only, never surface streets
  2. EXTENT       what stretch it is, how long, and how far from the study center
  3. GRID INTACT  the local streets under and beside the freeway stay open, so
                  the detour traffic has somewhere to go
  4. DETOUR       the two ends are still connected, and the trip between them is
                  now longer (a closure that changes no route changes no NO2)

It also reports what the old circular closure would have done on the same
stretch, which is the measured justification for having a separate selector.

Read-only: loads a graph, runs no simulation, writes nothing.

    python src/freeway_closure_check.py [--graph PATH]
"""
import argparse
import os
import sys
from collections import Counter

import networkx as nx
import osmnx as ox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import generate        # noqa: E402


def default_graph_path():
    """Prefer the 20 km Orca graph if it is cached here, else the plain cache."""
    orca = os.path.join(config.NETWORK_DIR, "graph_metro20k_orca.graphml")
    return orca if os.path.exists(orca) else os.path.join(config.NETWORK_DIR,
                                                          "graph.graphml")


def edge_midpoint(G, u, v):
    return (0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"])),
            0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default=None, help="graphml to check against")
    args = ap.parse_args()
    path = args.graph or default_graph_path()

    spec = config.FREEWAY_CLOSURE
    if spec is None:
        raise SystemExit("config.FREEWAY_CLOSURE is None; set a closure first.")

    print(f"graph: {path}")
    G = ox.load_graphml(path)
    print(f"  {G.number_of_nodes():,} nodes / {G.number_of_edges():,} directed edges")
    label = spec.get("name") or f"{spec['ref']} near {spec.get('center')}"
    print(f"closure: {label}  (ref {spec['ref']}, "
          f"close_ramps={spec.get('close_ramps', True)})")

    closed = generate.closed_freeway_edges(G, spec)
    closed_set = set(closed)

    # --- 1. composition ------------------------------------------------------
    classes = Counter()
    for u, v, k in closed:
        for h in generate._as_tag_list(G.edges[u, v, k].get("highway")):
            classes[str(h)] += 1
    surface = {h: n for h, n in classes.items()
               if h not in ("motorway", "motorway_link")}
    print("\n1. COMPOSITION of the closed set")
    for h, n in classes.most_common():
        print(f"     {h:16s} {n:4d}")
    print(f"   surface streets closed: {sum(surface.values())} "
          f"{'OK' if not surface else 'FAIL -> ' + str(surface)}")

    # --- 2. extent -----------------------------------------------------------
    km = sum(float(G.edges[u, v, k].get("length", 0.0)) for u, v, k in closed) / 1000.0
    mains = [e for e in closed
             if generate._edge_is_class(G.edges[e[0], e[1], e[2]], ("motorway",))]
    mids = [edge_midpoint(G, u, v) for u, v, k in mains]
    lat_c, lon_c = config.STUDY_CENTER
    d_center = [generate._haversine_m(lat_c, lon_c, la, lo) / 1000.0 for la, lo in mids]
    print("\n2. EXTENT")
    print(f"   {len(mains)} mainline edges + {len(closed) - len(mains)} ramp edges")
    print(f"   {km:.2f} km of directed roadway removed")
    print(f"   latitude {min(la for la, _ in mids):.4f} .. "
          f"{max(la for la, _ in mids):.4f}")
    print(f"   distance from study center: {min(d_center):.1f} .. "
          f"{max(d_center):.1f} km")

    # --- 3. is the local grid still there? -----------------------------------
    # Every non-freeway edge whose midpoint sits within 500 m of the closed
    # stretch should survive. Those streets are what the detour actually uses.
    near_surface = kept = 0
    for u, v, k, d in G.edges(keys=True, data=True):
        if generate._edge_is_class(d, ("motorway", "motorway_link")):
            continue
        la, lo = edge_midpoint(G, u, v)
        if any(generate._haversine_m(la, lo, mla, mlo) <= 500.0 for mla, mlo in mids):
            near_surface += 1
            if (u, v, k) not in closed_set:
                kept += 1
    print("\n3. LOCAL GRID under and beside the closure")
    print(f"   surface edges within 500 m: {near_surface}, still open: {kept} "
          f"{'OK' if kept == near_surface else 'FAIL'}")

    # --- 4. detour -----------------------------------------------------------
    # The diversion, measured the way a driver meets it: approach the closure on
    # the open freeway, leave at the last interchange that still works, and get
    # back on at the first one past the closure.
    #
    # ENTRY nodes are where an open mainline edge arrives and a closed one would
    # continue: that is where traffic is forced off. EXIT nodes are the mirror,
    # where the freeway resumes. Testing entry -> exit is the right question.
    # Testing the tail of a closed segment is NOT: interchange nodes strictly
    # inside the closure lose their mainline edges and their ramps together, so
    # they end up with no edges at all. That is correct (nobody can be there,
    # since routes are planned on the closed graph) but it makes any path query
    # from such a node fail for a reason that has nothing to do with diversion.
    Gc = G.copy()
    Gc.remove_edges_from(closed)
    mains_set = set(mains)
    mainline_set = set(generate.freeway_mainline_edges(G, spec["ref"]))
    entries, exits = set(), set()
    for n in {node for e in mains for node in e[:2]}:
        into = [(a, n, k) for a, _, k in G.in_edges(n, keys=True)]
        outof = [(n, b, k) for _, b, k in G.out_edges(n, keys=True)]
        in_open = any(e in mainline_set and e not in mains_set for e in into)
        in_closed = any(e in mains_set for e in into)
        out_open = any(e in mainline_set and e not in mains_set for e in outof)
        out_closed = any(e in mains_set for e in outof)
        if in_open and out_closed:
            entries.add(n)      # traffic arrives here and can go no further
        if in_closed and out_open:
            exits.add(n)        # the freeway resumes here

    print("\n4. DETOUR (forced off at the last open interchange, back on after)")
    print(f"   {len(entries)} entry node(s) where traffic is pushed off, "
          f"{len(exits)} exit node(s) where the freeway resumes")
    if not entries or not exits:
        print("   inconclusive: the closure has no open freeway on one side, so "
              "there is no on-freeway trip to divert")
        return
    # Pair each entry with the exit on ITS OWN carriageway by walking the closed
    # mainline forward. Pairing by proximity instead would match an entry with
    # the opposite carriageway's exit sitting a few meters across the median,
    # and measure a trip that never used the closed road at all.
    nxt = {}
    for u, v, k in mains:
        nxt.setdefault(u, []).append((v, float(G.edges[u, v, k].get("length", 0.0))))

    def walk_to_exit(start):
        """Follow closed mainline edges from `start` to the exit it feeds,
        returning (exit_node, meters of closed freeway traversed)."""
        node, travelled, guard = start, 0.0, 0
        while node not in exits and node in nxt and guard < len(mains) + 1:
            v, L = nxt[node][0]
            travelled += L
            node = v
            guard += 1
        return (node if node in exits else None), travelled

    stranded = 0
    for e in sorted(entries):
        x, on_freeway = walk_to_exit(e)
        if x is None:
            stranded += 1
            print(f"     node {e}: its carriageway leads to no open exit")
            continue
        try:
            around = nx.shortest_path_length(Gc, e, x, weight="length")
        except nx.NetworkXNoPath:
            stranded += 1
            print(f"     node {e} -> {x}: no route at all once closed "
                  f"({on_freeway/1000:.2f} km of freeway removed)")
            continue
        extra = 100 * (around - on_freeway) / on_freeway if on_freeway else 0.0
        print(f"     node {e} -> {x}: {on_freeway/1000:5.2f} km of freeway "
              f"becomes a {around/1000:5.2f} km detour  ({extra:+.0f}%)")
    if stranded:
        print(f"   FAIL: {stranded} entry node(s) strand their traffic")
    else:
        print("   OK: every forced-off movement still has a way around")

    # --- why not just use a circle? -----------------------------------------
    # Same stretch, expressed the old way: a circle centered on the closure with
    # a radius that covers it. Reported to keep the design decision measured
    # rather than asserted.
    c_lat = sum(la for la, _ in mids) / len(mids)
    c_lon = sum(lo for _, lo in mids) / len(mids)
    reach = max(generate._haversine_m(c_lat, c_lon, la, lo) for la, lo in mids)
    circle = generate.closed_edges_in_zone(G, (c_lat, c_lon, reach))
    c_classes = Counter()
    for u, v, k in circle:
        for h in generate._as_tag_list(G.edges[u, v, k].get("highway")):
            c_classes[str(h)] += 1
    c_surface = sum(n for h, n in c_classes.items()
                    if h not in ("motorway", "motorway_link"))
    print(f"\n   for contrast, a {reach:.0f} m circle over the same stretch would "
          f"close {len(circle)} edges, {c_surface} of them surface streets "
          f"({100*c_surface/len(circle) if circle else 0:.0f}%)")


if __name__ == "__main__":
    main()
