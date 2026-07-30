"""Static shortest-path reassignment ablation for the closure experiment
(Christof's review item 1, Jul 30).

THE OBJECTION IT ANSWERS: the chapter's closure comparison is analytic -- a
land-use surface cannot respond because its inputs are fixed, so the experiment
confirms the specification. A plain all-or-nothing shortest-path reassignment
on the closed network ALSO redistributes traffic, with no car-following, no
signals, no queues. If the ABM's magnitudes differ materially from that cheap
baseline, the dynamics layers earn their place in the headline result; if they
do not, that is a finding too.

WHAT THIS SCRIPT DOES (no simulation -- deterministic, minutes):
1. Rebuilds the powell_through corridor demand EXACTLY as the ABM does, by
   calling the same make_vehicle() (gravity origins/destinations, 30% through
   trips, mixed-fleet class draw, shortest-TIME routing) with a pinned seed.
   No re-implementation: the trips are drawn by the committed code.
2. OPEN assignment: each trip credits every segment on its route once
   (all-or-nothing). Static NOx per segment = crossings x length x the
   vehicle's own HBEFA g/km at the segment's free-flow speed -- emissions with
   the DYNAMICS REMOVED (no idling, no stop-and-go, no queue time).
3. CLOSED assignment: the SAME OD pairs re-routed on the closure-applied
   graph; pairs that lose an endpoint or all connectivity are counted and
   dropped (reported -- a real closure displaces those few local trips).
4. Reads the committed ABM parquets (powell_through_open/_closed) and reports
   both methods' percent changes side by side, on the same street matcher:
   Powell / Division / Holgate NOx, network total, plus a pure-traffic
   veh-km version so the redistribution is visible independent of the
   emission weighting.

DISCIPLINE: corridor overrides live visibly here (config.py describes the
metro run); analysis-only reads of the committed parquets; writes nothing to
data/; seed pinned below and reported with the numbers.

Run: python src/closure_static_reassignment.py
"""
import os
import random
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

import config

# --- corridor overrides (the chapter's closure scale), visible up front ------
config.STUDY_RADIUS_M = 1500
config.THROUGH_TRAFFIC_FRACTION = 0.30
config.DEMAND_LODES_OD = False
config.DEMAND_GRAVITY = True
config.FLEET_MIXED = True          # the chapter's live emissions setting
config.RANDOM_SEED = 42            # the chapter's representative seed

import emissions          # noqa: E402  (import after overrides, like the runners)
import generate           # noqa: E402

N_TRIPS = 5000            # static sample size; percent changes are invariant to it
STREETS = ("Powell", "Division", "Holgate")


def street_of(name_attr):
    nm = name_attr if isinstance(name_attr, list) else [name_attr]
    for s in STREETS:
        if any(n and s.lower() in str(n).lower() for n in nm):
            return s
    return None


def static_assign(G, trips):
    """All-or-nothing: credit each route segment once per trip; static NOx =
    length_km x the trip vehicle's g/km at the segment's free-flow speed."""
    veh_km = {e: 0.0 for e in G.edges(keys=True)}
    nox = {e: 0.0 for e in G.edges(keys=True)}
    for coeffs, route in trips:
        for (u, v, k, length_m, v0) in route:
            km = length_m / 1000.0
            veh_km[(u, v, k)] += km
            # steady free-flow emission rate: g/s at v0 over length/v0 seconds
            nox[(u, v, k)] += emissions.nox_g_per_s(v0, 0.0, coeffs) * (length_m / v0)
    return veh_km, nox


def reroute_on(Gc, od_pairs, fleet_coeffs):
    """Route the SAME OD pairs on the closed graph; drop unroutable ones."""
    trips, dropped = [], 0
    for (o, d, coeffs) in od_pairs:
        if o not in Gc or d not in Gc:
            dropped += 1
            continue
        try:
            path = nx.shortest_path(Gc, o, d, weight="travel_time_s")
        except nx.NetworkXNoPath:
            dropped += 1
            continue
        route = [generate._edge_between(Gc, path[i], path[i + 1])
                 for i in range(len(path) - 1)]
        trips.append((coeffs, route))
    return trips, dropped


def by_street(G, per_edge):
    out = {s: 0.0 for s in STREETS}
    total = 0.0
    names = {(u, v, k): street_of(d.get("name"))
             for u, v, k, d in G.edges(keys=True, data=True)}
    for e, val in per_edge.items():
        total += val
        s = names.get(e)
        if s:
            out[s] += val
    out["network total"] = total
    return out


def pct_table(label, open_d, closed_d):
    print(f"\n=== {label} ===")
    for key in (*STREETS, "network total"):
        o, c = open_d[key], closed_d[key]
        pct = 100.0 * (c / o - 1.0) if o else float("nan")
        print(f"   {key:14s} {o:12.1f} -> {c:12.1f}   {pct:+6.1f}%")


def main():
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    assert G.number_of_edges() < 10_000, "expected the 1.5 km corridor graph"
    generate.prepare_network(G)
    nodes = list(G.nodes)
    rng = random.Random(config.RANDOM_SEED)
    generate.set_seeds(config.RANDOM_SEED)
    demand = generate.build_demand_weights(G, nodes)
    through = generate.build_through_context(G, nodes)
    fleet_ctx = generate.build_fleet_context()

    # 1) draw the trips with the COMMITTED sampler (routes on the open network)
    open_trips, od_pairs = [], []
    for vid in range(N_TRIPS):
        veh = generate.make_vehicle(G, nodes, rng, vid, demand, through, fleet_ctx)
        if veh is None:
            continue
        coeffs = veh.get("coeffs", emissions.active_coeffs())
        route = veh["route"]
        open_trips.append((coeffs, route))
        od_pairs.append((route[0][0], route[-1][1], coeffs))
    print(f"{len(open_trips)} trips drawn (seed {config.RANDOM_SEED}, "
          f"{config.THROUGH_TRAFFIC_FRACTION:.0%} through)")

    # 2) closed network: same closure the ABM used, same OD pairs re-routed
    Gc = G.copy()
    removed = generate.apply_closure(Gc)
    generate.prepare_network(Gc)
    closed_trips, dropped = reroute_on(Gc, od_pairs, fleet_ctx)
    print(f"closure removed {len(removed)} segments; {dropped} of "
          f"{len(od_pairs)} trips unroutable and dropped "
          f"({100 * dropped / len(od_pairs):.1f}%)")

    # 3) static assignment, open vs closed
    km_o, nox_o = static_assign(G, open_trips)
    km_c, nox_c = static_assign(Gc, closed_trips)
    pct_table("STATIC reassignment: traffic (veh-km)",
              by_street(G, km_o), by_street(Gc, km_c))
    pct_table("STATIC reassignment: free-flow NOx (g)",
              by_street(G, nox_o), by_street(Gc, nox_c))

    # 4) the ABM's committed numbers, same matcher, from the saved parquets
    def abm_street_nox(run):
        df = pd.read_parquet(os.path.join(config.PROCESSED_DIR,
                                          f"{run}_segments.parquet"))
        per_edge = {(r.u, r.v, r.key): r.nox_g for r in df.itertuples()}
        return by_street(G, per_edge)

    pct_table("ABM (committed powell_through run): NOx (g)",
              abm_street_nox("powell_through_open"),
              abm_street_nox("powell_through_closed"))

    print("\nReading: if the ABM's magnitudes differ materially from the static"
          "\nreassignment's, the dynamics (car-following, signals, queues) are"
          "\nload-bearing for the headline result; similar magnitudes would mean"
          "\nrerouting alone explains it. Either answer strengthens the chapter.")


if __name__ == "__main__":
    main()
