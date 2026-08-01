"""Hand-checkable scenarios for the NON-WORK DEMAND LAYER (real-demand upgrade
plan, Phase B3: a share of local trips ends at consumer-facing service jobs
instead of at commute destinations).

Same discipline as scenarios.py / demand_profile_scenarios.py (Christof's
Jun 24 ask: values predictable by hand, through the REAL kernel, never a
reimplementation).

  A) INERTNESS + ZERO-DRAW. Attaching a non-work layer with share = 0.0 must
     leave a run BITWISE identical to one with no layer at all -- every car's
     (id, idx, pos, v) at the end AND the final RNG state (the share > 0 guard
     in make_vehicle means a zero share consumes not one extra draw). Then
     share = 1.0 with ALL service mass hand-placed on one node must send every
     single local trip to exactly that node.

  B) THE BUILD ARITHMETIC, BY HAND. build_nonwork_demand on a hand-made
     4-node graph and a monkeypatched 3-block-group service table: the Voronoi
     split must give hand-computed origin/destination weights, a block group
     with zero service jobs must contribute zero destination weight, and the
     refusals must all fire loudly -- share out of [0,1], an empty table, a
     table that raises, and the flag on with no work demand layer under it.
     Plus flag-off: build_demand_weights must not attach anything.

  C) SPATIAL SANITY, REAL GRAPH. On the real corridor graph with the real
     Census/WAC masses: non-work trips (service-job destinations, 800 m decay)
     must be SHORTER on average than work trips (total-job destinations,
     1500 m decay) -- NHTS says shopping/errand trips run about half the
     length of commutes, and the layer must reproduce the direction.

  D) REPRODUCIBILITY. Two independent builds and identically seeded draw
     sequences must produce the identical trip list.

(kernel_regression.py additionally proves the surrounding edit changed no base
physics with the flag off.)

Run: python src/nonwork_scenarios.py
"""
import os
import sys
import random
from collections import defaultdict

import numpy as np
import networkx as nx
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import emissions
import landuse_data
from generate import (step_vehicles, make_vehicle, prepare_network,
                      build_nonwork_demand, build_demand_weights)

PASS, FAIL = "PASS", "FAIL"


def _check(label, ok, detail):
    print(f"   [{PASS if ok else FAIL}] {label}: {detail}")
    return bool(ok)


def _no_signals():
    return {"nodes": set(), "offset": {}, "edge_phase": {},
            "cycle": 60.0, "green_split": 0.5}


def _ring_graph():
    """The same 4-node, 8-directed-edge ring the demand-profile gates use:
    small enough that trips finish in tens of seconds, so the respawn path
    (where the non-work draw lives) is exercised hard."""
    G = nx.MultiDiGraph()
    coords = {0: (0.0, 0.0), 1: (150.0, 0.0), 2: (150.0, 150.0), 3: (0.0, 150.0)}
    for n, (x, y) in coords.items():
        G.add_node(n, x=x, y=y)
    for u, v in ((0, 1), (1, 2), (2, 3), (3, 0)):
        for a, b in ((u, v), (v, u)):
            G.add_edge(a, b, length=150.0, maxspeed="50", highway="residential")
    return prepare_network(G)


def _hand_demand(nodes):
    """A hand-built gravity-mode work demand dict for the ring: uniform
    origin/destination weights, no decay. The point is a demand context the
    non-work layer can sit inside, with none of the draws depending on real
    Census data."""
    n = len(nodes)
    return {
        "origin_w": [1.0] * n,
        "dest_w": np.ones(n),
        "dest_w_list": [1.0] * n,
        "node_x": np.zeros(n), "node_y": np.zeros(n),
        "index": {nd: i for i, nd in enumerate(nodes)},
        "scale": 0.0,
    }


def scenario_inertness():
    print("\nA) INERTNESS + ZERO-DRAW: share 0.0 is bitwise no-layer; share 1.0")
    print("   with all service mass on node 2 sends EVERY local trip to node 2.")
    n_steps = 600
    G = _ring_graph()
    nodes = list(G.nodes)
    coeffs = emissions.active_coeffs()
    signals = _no_signals()

    def run(nonwork):
        rng = random.Random(7)
        demand = _hand_demand(nodes)
        if nonwork is not None:
            demand["nonwork"] = nonwork
        vehs = []
        for vid in range(30):
            veh = make_vehicle(G, nodes, rng, vid, demand)
            if veh is not None:
                vehs.append(veh)
        # count respawns via route-object identity, so the gate proves the
        # respawn path (not just the initial spawn) went through the draw
        route_ids = {v["id"]: id(v["route"]) for v in vehs}
        respawns = 0
        seg_tot, seg_nox, seg_thru = (defaultdict(float), defaultdict(float),
                                      defaultdict(float))
        for s in range(n_steps):
            step_vehicles(vehs, config.DT, s * config.DT, seg_tot, seg_nox,
                          seg_thru, coeffs, G, nodes, rng, signals, demand, None)
            for v in vehs:
                if id(v["route"]) != route_ids.get(v["id"]):
                    respawns += 1
                    route_ids[v["id"]] = id(v["route"])
        traj = np.array(sorted((v["id"], v["idx"], v["pos"], v["v"]) for v in vehs))
        return traj, rng.getstate(), respawns, vehs

    def hand_nonwork(share, dest_node=None):
        n = len(nodes)
        dest = np.ones(n)
        if dest_node is not None:
            dest = np.zeros(n)
            dest[nodes.index(dest_node)] = 1.0
        return {"share": share, "origin_w": [1.0] * n,
                "dest_w": dest, "dest_w_list": dest.tolist(),
                "node_x": np.zeros(n), "node_y": np.zeros(n),
                "index": {nd: i for i, nd in enumerate(nodes)}, "scale": 0.0}

    base_traj, base_rng, respawns, _ = run(nonwork=None)
    zero_traj, zero_rng, _, _ = run(nonwork=hand_nonwork(0.0))

    ok = []
    ok.append(_check("the base arm exercises the respawn path hard",
                     respawns >= 50, f"{respawns} completed trips in {n_steps} s"))
    same = base_traj.shape == zero_traj.shape and np.array_equal(base_traj, zero_traj)
    ok.append(_check("share 0.0: trajectories bitwise identical", same,
                     "bitwise equal" if same else "trajectories DIVERGED"))
    ok.append(_check("share 0.0: not one extra RNG draw consumed",
                     base_rng == zero_rng,
                     "final getstate() equal" if base_rng == zero_rng
                     else "RNG states DIVERGED -- the guard leaked a draw"))

    # share = 1.0, every unit of service mass hand-placed on node 2: every trip
    # alive at any point must be headed to node 2 (routes end there)
    _, _, _, vehs = run(nonwork=hand_nonwork(1.0, dest_node=2))
    dests = {v["route"][-1][1] for v in vehs}
    ok.append(_check("share 1.0 + all mass on node 2: every trip ends at node 2",
                     dests == {2}, f"destinations seen at close: {sorted(dests)}"))
    return all(ok)


def scenario_build_arithmetic():
    print("\nB) BUILD ARITHMETIC: Voronoi weights by hand, and the loud refusals")
    print("   3 block groups, 4 nodes: BG1 (pop 100, svc 0) catches nodes 0+1,")
    print("   BG2 (pop 50, svc 20) catches node 2, BG3 (pop 0, svc 10) node 3.")
    lat0, lon0 = config.STUDY_CENTER
    # a hand graph whose nodes sit at known offsets from the study center; the
    # block-group centroids are placed so the nearest-centroid rule is obvious
    # (~0.001 deg latitude is ~110 m, far bigger than any rounding error)
    G = nx.MultiDiGraph()
    node_pos = {0: (0.0000, 0.0000), 1: (0.0002, 0.0000),   # both nearest BG1
                2: (0.0100, 0.0000),                        # nearest BG2
                3: (0.0000, 0.0100)}                        # nearest BG3
    for n, (dlat, dlon) in node_pos.items():
        G.add_node(n, x=lon0 + dlon, y=lat0 + dlat)
    nodes = list(G.nodes)
    hand_lu = pd.DataFrame({
        "bg_geoid": ["1", "2", "3"],
        "lat": [lat0 + 0.0001, lat0 + 0.0100, lat0],
        "lon": [lon0, lon0, lon0 + 0.0100],
        "population": [100.0, 50.0, 0.0],
        "service_jobs": [0.0, 20.0, 10.0],
    })

    real_table = landuse_data.service_landuse_table
    old_flag = config.DEMAND_NONWORK_ENABLED
    old_share = config.NONWORK_TRIP_SHARE
    ok = []
    try:
        landuse_data.service_landuse_table = lambda **kw: hand_lu
        nw = build_nonwork_demand(G, nodes)
        # hand values: BG1's 100 residents split over its 2 nodes -> 50 each,
        # 0 service jobs -> dest 0; BG2's node carries (50, 20); BG3's (0, 10)
        want_origin = [50.0, 50.0, 50.0, 0.0]
        want_dest = [0.0, 0.0, 20.0, 10.0]
        ok.append(_check("origin weights split population over Voronoi nodes",
                         nw["origin_w"] == want_origin,
                         f"{nw['origin_w']} (want {want_origin})"))
        ok.append(_check("destination weights are service jobs, zero-svc BG = 0",
                         nw["dest_w"].tolist() == want_dest,
                         f"{nw['dest_w'].tolist()} (want {want_dest})"))
        ok.append(_check("share and decay scale come from config",
                         nw["share"] == config.NONWORK_TRIP_SHARE
                         and nw["scale"] == config.NONWORK_DECAY_SCALE_M,
                         f"share {nw['share']}, scale {nw['scale']}"))

        # refusal: share outside [0, 1]
        config.NONWORK_TRIP_SHARE = 1.5
        try:
            build_nonwork_demand(G, nodes)
            refused = False
        except ValueError:
            refused = True
        config.NONWORK_TRIP_SHARE = old_share
        ok.append(_check("share 1.5 refused loudly", refused,
                         "ValueError raised" if refused else "accepted silently!"))

        # refusal: empty table
        landuse_data.service_landuse_table = lambda **kw: hand_lu.iloc[0:0]
        try:
            build_nonwork_demand(G, nodes)
            refused = False
        except ValueError:
            refused = True
        ok.append(_check("an empty service table refused loudly", refused,
                         "ValueError raised" if refused else "accepted silently!"))

        # refusal: the table itself failing (e.g. no cached WAC, no network)
        def boom(**kw):
            raise OSError("no such file")
        landuse_data.service_landuse_table = boom
        try:
            build_nonwork_demand(G, nodes)
            refused = False
        except ValueError:
            refused = True
        ok.append(_check("an unavailable service table refused loudly", refused,
                         "ValueError raised" if refused else "fell back silently!"))
    finally:
        landuse_data.service_landuse_table = real_table
        config.DEMAND_NONWORK_ENABLED = old_flag
        config.NONWORK_TRIP_SHARE = old_share

    # flag OFF: build_demand_weights must not attach a non-work layer; flag ON
    # over a None work layer (no gravity, no OD) must refuse rather than half-run
    old = (config.DEMAND_NONWORK_ENABLED, config.DEMAND_GRAVITY,
           config.DEMAND_LODES_OD)
    try:
        config.DEMAND_NONWORK_ENABLED = False
        config.DEMAND_GRAVITY = False
        config.DEMAND_LODES_OD = False
        d = build_demand_weights(G, nodes)
        ok.append(_check("flag off: no layer attached",
                         d is None or "nonwork" not in d,
                         "nothing attached"))
        config.DEMAND_NONWORK_ENABLED = True
        try:
            build_demand_weights(G, nodes)
            refused = False
        except ValueError:
            refused = True
        ok.append(_check("flag on with no work demand layer refused loudly",
                         refused,
                         "ValueError raised" if refused else "half-model ran!"))
    finally:
        (config.DEMAND_NONWORK_ENABLED, config.DEMAND_GRAVITY,
         config.DEMAND_LODES_OD) = old
    return all(ok)


def scenario_spatial_sanity():
    print("\nC) SPATIAL SANITY, REAL GRAPH: non-work trips shorter than work trips")
    print("   500 gravity work trips (total jobs, 1500 m decay) vs 500 non-work")
    print("   trips (service jobs, 800 m decay) on the corridor graph, routed")
    print("   through the real kernel; NHTS direction: non-work runs shorter.")
    import osmnx as ox
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if not os.path.exists(graph_file):
        print(f"   [FAIL] no corridor graph at {graph_file}")
        return False
    G = prepare_network(ox.load_graphml(graph_file))
    nodes = list(G.nodes)

    # the work arm: pure gravity (OD off so the comparison is gravity-vs-gravity,
    # total jobs vs service jobs, 1500 m vs 800 m -- one mechanism per arm)
    old = (config.DEMAND_NONWORK_ENABLED, config.DEMAND_LODES_OD,
           config.DEMAND_GRAVITY)
    try:
        config.DEMAND_NONWORK_ENABLED = False
        config.DEMAND_LODES_OD = False
        config.DEMAND_GRAVITY = True
        demand = build_demand_weights(G, nodes)
        if demand is None:
            print("   [FAIL] gravity demand unavailable on the corridor graph")
            return False
        nonwork = build_nonwork_demand(G, nodes)
    finally:
        (config.DEMAND_NONWORK_ENABLED, config.DEMAND_LODES_OD,
         config.DEMAND_GRAVITY) = old

    def mean_len(with_nonwork, seed, n_trips=500):
        d = dict(demand)
        if with_nonwork:
            d["nonwork"] = dict(nonwork, share=1.0)   # every local trip non-work
        rng = random.Random(seed)
        lengths = []
        for vid in range(n_trips):
            veh = make_vehicle(G, nodes, rng, vid, d)
            if veh is not None:
                lengths.append(sum(e[3] for e in veh["route"]))
        return float(np.mean(lengths)), len(lengths)

    work_m, n_work = mean_len(False, seed=42)
    nonwork_m, n_nonwork = mean_len(True, seed=42)
    ratio = nonwork_m / work_m
    ok = []
    ok.append(_check("both arms placed plenty of trips",
                     n_work >= 450 and n_nonwork >= 450,
                     f"{n_work} work, {n_nonwork} non-work of 500 attempted"))
    ok.append(_check("non-work trips are SHORTER on average (NHTS direction)",
                     nonwork_m < work_m,
                     f"non-work {nonwork_m:.0f} m vs work {work_m:.0f} m "
                     f"(ratio {ratio:.2f}; NHTS trip-length ratio is 0.54, but "
                     f"the 1.5 km window truncates both arms toward each other)"))
    return all(ok)


def scenario_reproducibility():
    print("\nD) REPRODUCIBILITY: two independent builds, identical seeded draws")
    import osmnx as ox
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    G = prepare_network(ox.load_graphml(graph_file))
    nodes = list(G.nodes)

    def build_and_draw():
        nw = build_nonwork_demand(G, nodes)
        demand = dict(_hand_demand(nodes), nonwork=dict(nw, share=1.0))
        rng = random.Random(2024)
        trips = []
        for vid in range(200):
            veh = make_vehicle(G, nodes, rng, vid, demand)
            if veh is not None:
                trips.append((veh["route"][0][0], veh["route"][-1][1]))
        return trips

    a, b = build_and_draw(), build_and_draw()
    same = a == b
    return _check("200 seeded (origin, destination) pairs identical across builds",
                  same, f"{len(a)} trips, {'identical' if same else 'DIVERGED'}")


if __name__ == "__main__":
    print("Non-work demand scenarios  (real kernel, hand-checkable)")
    print("=" * 66)
    results = {"inertness_zero_draw": scenario_inertness(),
               "build_arithmetic": scenario_build_arithmetic(),
               "spatial_sanity": scenario_spatial_sanity(),
               "reproducibility": scenario_reproducibility()}
    print("\n" + "=" * 66)
    for name, okay in results.items():
        print(f"   {PASS if okay else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} non-work demand scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
