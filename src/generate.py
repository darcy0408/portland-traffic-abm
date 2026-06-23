"""STAGE 1: GENERATE DATA.

Runs the agent-based simulation and writes its results to disk. This script does
no plotting. Its only job is to produce data files that visualize.py reads later.
Keeping it plot-free is what lets you redraw any figure without rerunning the sim.

Run it with:
    python src/generate.py            # full run from config.py
    python src/generate.py benchmark  # quick runtime read at several vehicle counts

This is the week-3 build: real vehicles driving on the OSMnx network with routes,
following each other via the IDM kernel. Signals/queueing come in week 4.
"""
import os
import sys
import time
import math
import random
from collections import defaultdict

import numpy as np
import pandas as pd
import osmnx as ox
import networkx as nx

# make sibling modules importable whether run from repo root or from src/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from checkpoint import save_checkpoint, load_checkpoint


def set_seeds(seed):
    random.seed(seed)
    np.random.seed(seed)


def idm_acceleration(v, gap, lead_v, v0,
                     a_max=config.IDM_A_MAX, b_comf=config.IDM_B_COMF,
                     T=config.IDM_T, s0=config.IDM_S0, delta=config.IDM_DELTA):
    """Intelligent Driver Model: how hard one car accelerates or brakes right now.

    This is the core of the whole simulation. It is a pure function: give it the
    car's situation, it returns an acceleration in m/s^2 (positive = speed up,
    negative = brake). It changes nothing and stores nothing, which makes it easy
    to test by eye.

    Arguments:
        v       current speed of this car (m/s)
        gap     clear distance to the back of the car ahead (m); use a large
                number or float('inf') when there is no car ahead
        lead_v  speed of the car ahead (m/s); ignored when there is no leader
        v0      this car's desired speed, i.e. the segment speed limit (m/s)

    The formula has two parts that pull against each other:

      free road:   a_max * (1 - (v/v0)**delta)
                   when v is well below v0 this is near a_max (accelerate);
                   as v approaches v0 it fades to zero (stop speeding up).

      interaction: -a_max * (s_star / gap)**2
                   s_star is the gap the driver *wants* given current speed and
                   how fast they are closing on the leader. If the real gap is
                   smaller than the wanted gap, this term grows and brakes hard.
    """
    # Floor the gap so an exact overlap can't divide by zero; treat it as bumper
    # contact, which the interaction term will then punish with heavy braking.
    gap = max(gap, 1e-3)

    # How fast we are closing on the leader (positive = catching up).
    delta_v = v - lead_v

    # The gap the driver *desires* right now: a standstill minimum (s0), plus a
    # speed-dependent following distance (v*T), plus an extra cushion that grows
    # when closing fast on the leader.
    s_star = s0 + max(0.0, v * T + (v * delta_v) / (2.0 * (a_max * b_comf) ** 0.5))

    free_term = 1.0 - (v / v0) ** delta
    interaction_term = (s_star / gap) ** 2
    return a_max * (free_term - interaction_term)


def get_network():
    """Download the street graph once, then reuse the cached copy.
    OSMnx downloads are slow, so we save the graph and load it on later runs."""
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if os.path.exists(graph_file):
        return ox.load_graphml(graph_file)
    G = ox.graph_from_point(config.STUDY_CENTER, dist=config.STUDY_RADIUS_M,
                            network_type=config.NETWORK_TYPE)
    ox.save_graphml(G, graph_file)
    return G


# --- network preparation ---------------------------------------------------
# Default desired speeds (km/h) by OSM road class, used when a segment has no
# usable maxspeed tag. Deliberately simple and transparent so it is easy to
# explain in the writeup; refine later if needed.
DEFAULT_KPH = {
    "motorway": 100, "motorway_link": 60, "trunk": 80, "trunk_link": 50,
    "primary": 65, "primary_link": 40, "secondary": 55, "secondary_link": 40,
    "tertiary": 45, "residential": 30, "living_street": 15, "unclassified": 40,
    "service": 20,
}


def _parse_maxspeed_kph(maxspeed):
    """Turn an OSM maxspeed tag into km/h, or None if it can't be read.
    Tags come as '30 mph', '50', or a list like ['30', '40']; handle all three."""
    if maxspeed is None:
        return None
    if isinstance(maxspeed, list):
        maxspeed = maxspeed[0]
    try:
        s = str(maxspeed).lower().strip()
        if "mph" in s:
            return float(s.replace("mph", "").strip()) * 1.60934
        return float(s.split()[0])
    except (ValueError, IndexError):
        return None


def _default_kph(highway):
    if isinstance(highway, list):
        highway = highway[0]
    return DEFAULT_KPH.get(highway, 40)


def prepare_network(G):
    """Give every edge a desired speed in m/s ('v0_mps') and ensure a length.
    Each car uses its current segment's v0_mps as its target speed in the IDM."""
    for _u, _v, _k, data in G.edges(keys=True, data=True):
        if "length" not in data or data["length"] is None:
            data["length"] = 10.0
        kph = _parse_maxspeed_kph(data.get("maxspeed"))
        if kph is None:
            kph = _default_kph(data.get("highway"))
        data["v0_mps"] = max(kph, 8.0) / 3.6   # floor at 8 km/h so nothing is stuck
    return G


# --- traffic signals -------------------------------------------------------
# A signalized intersection runs two phases. Each incoming edge is assigned to a
# phase by its compass bearing: roughly east-west approaches share one phase,
# north-south approaches the other, so cross streets alternate green. The current
# green phase at a node is a function of the clock plus a per-node offset (so the
# whole grid is not synchronized). This is a deliberately simple, transparent
# model; real per-signal timing plans are not public (see DATASETS.md).


def _approach_phase(G, u, v):
    """Phase (0 = east-west, 1 = north-south) for travel from node u to node v,
    from the bearing of the segment. Used to decide which approaches share green."""
    x1, y1 = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
    x2, y2 = float(G.nodes[v]["x"]), float(G.nodes[v]["y"])
    ang = math.degrees(math.atan2(x2 - x1, y2 - y1)) % 180   # 0 = N/S, 90 = E/W
    return 0 if 45 <= ang < 135 else 1


def prepare_signals(G):
    """Find signalized nodes and precompute each edge's phase and each node's
    cycle offset. Prefers real OSM 'traffic_signals' node tags; if the graph has
    none, falls back to treating every 4-way+ intersection as signalized."""
    signal_nodes = {n for n, d in G.nodes(data=True)
                    if "traffic_signals" in str(d.get("highway", ""))}
    tagged = len(signal_nodes)
    if not signal_nodes:
        signal_nodes = {n for n in G.nodes if G.degree(n) >= 4}

    sig_rng = random.Random(config.RANDOM_SEED + 1)   # own stream, reproducible
    offset = {n: sig_rng.uniform(0.0, config.SIGNAL_CYCLE_S) for n in signal_nodes}
    edge_phase = {(u, v, k): _approach_phase(G, u, v)
                  for u, v, k in G.edges(keys=True)}
    return {
        "nodes": signal_nodes, "offset": offset, "edge_phase": edge_phase,
        "cycle": config.SIGNAL_CYCLE_S, "green_split": config.SIGNAL_GREEN_SPLIT,
        "tagged": tagged,
    }


def is_green(signals, node, phase, t):
    """Is `phase` showing green at this signalized node at time t (seconds)?"""
    frac = ((t + signals["offset"][node]) % signals["cycle"]) / signals["cycle"]
    green_phase = 0 if frac < signals["green_split"] else 1
    return phase == green_phase


# --- vehicles --------------------------------------------------------------
# A vehicle is a plain dict (so it pickles cleanly into a checkpoint):
#   id    unique integer
#   route list of (u, v, k, length_m, v0_mps), one per edge it will traverse
#   idx   index of the edge it is currently on
#   pos   metres travelled along that edge
#   v     current speed (m/s)


def _edge_between(G, u, v):
    """Pick the edge from u to v (the shortest one if the streets are parallel)
    and return (u, v, key, length_m, v0_mps)."""
    datas = G.get_edge_data(u, v)
    k = min(datas, key=lambda kk: datas[kk].get("length", 1.0))
    d = datas[k]
    return (u, v, k, d.get("length", 10.0), d.get("v0_mps", 11.0))


def make_vehicle(G, nodes, rng, vid):
    """Create one vehicle with a random origin, destination, and shortest route.
    Returns None if it could not find a route after a few tries."""
    for _ in range(25):
        o, d = rng.choice(nodes), rng.choice(nodes)
        if o == d:
            continue
        try:
            path = nx.shortest_path(G, o, d, weight="length")
        except nx.NetworkXNoPath:
            continue
        if len(path) < 2:
            continue
        route = [_edge_between(G, path[i], path[i + 1]) for i in range(len(path) - 1)]
        return {"id": vid, "route": route, "idx": 0, "pos": 0.0, "v": 0.0}
    return None


def step_vehicles(vehicles, dt, t, segment_totals, G, nodes, rng, signals):
    """Advance every vehicle by one time step.

    Order matters: we read all positions first, compute each car's acceleration
    from that frozen snapshot, and only then move everyone. That simultaneous
    update is what keeps the car-following honest (no car reacts to a neighbour
    that has already moved this step).

    Two things slow a car: the car ahead on its own segment, and a red light at
    the segment's far end. A red light acts as a stationary 'virtual leader' at
    the stop line, so the IDM brakes for it smoothly; the car physically waits at
    the line until the light turns green. Queues then build behind the line by the
    ordinary car-following, and congestion emerges.

    Simplification still in place: a car only sees the leader on its own segment,
    so a queue longer than a block does not yet spill back through the upstream
    intersection. That cross-edge spillback is the next refinement.
    """
    # group cars by the segment they are on, and sort each group front-to-back
    by_edge = defaultdict(list)
    for veh in vehicles:
        by_edge[veh["route"][veh["idx"]][:3]].append(veh)
    for group in by_edge.values():
        group.sort(key=lambda x: x["pos"])

    # 1) compute accelerations from the frozen snapshot
    L = config.VEHICLE_LENGTH_M
    accel = {}
    for group in by_edge.values():
        for i, veh in enumerate(group):
            edge = veh["route"][veh["idx"]]
            v0 = edge[4]
            if i + 1 < len(group):                 # there is a car ahead on this edge
                lead = group[i + 1]
                gap = lead["pos"] - L - veh["pos"]
                lead_v = lead["v"]
            else:                                  # open road ahead
                gap = 1e6
                lead_v = veh["v"]

            # a red light at the downstream node is a stopped leader at the line
            node_v = edge[1]
            if node_v in signals["nodes"] and not is_green(
                    signals, node_v, signals["edge_phase"][edge[:3]], t):
                stop_gap = edge[3] - veh["pos"]
                if stop_gap < gap:                 # the light binds before any car
                    gap, lead_v = stop_gap, 0.0

            accel[veh["id"]] = idm_acceleration(veh["v"], gap, lead_v, v0)

    # 2) move everyone, credit the segment they travelled on, advance routes
    for veh in vehicles:
        a = accel[veh["id"]]
        v_new = max(0.0, veh["v"] + a * dt)
        veh["pos"] += 0.5 * (veh["v"] + v_new) * dt   # trapezoidal step
        veh["v"] = v_new

        # credit this segment with one vehicle-second of activity (a stand-in for
        # the per-vehicle emission/noise contribution that plugs in here later)
        segment_totals[veh["route"][veh["idx"]][:3]] += dt

        # cross into the next segment(s) if we ran past the end of this one
        while veh["pos"] > veh["route"][veh["idx"]][3]:
            edge = veh["route"][veh["idx"]]
            node_v = edge[1]
            # do not cross a red light: wait exactly at the stop line
            if node_v in signals["nodes"] and not is_green(
                    signals, node_v, signals["edge_phase"][edge[:3]], t):
                veh["pos"], veh["v"] = edge[3], 0.0
                break
            veh["pos"] -= edge[3]
            if veh["idx"] + 1 < len(veh["route"]):
                veh["idx"] += 1
            else:
                # reached the destination: respawn with a fresh trip so the
                # number of vehicles on the network stays steady
                fresh = make_vehicle(G, nodes, rng, veh["id"])
                if fresh is not None:
                    veh.update(fresh)
                else:
                    veh["pos"], veh["v"] = edge[3], 0.0
                break


def run_simulation(G, n_vehicles=None, n_steps=None, use_checkpoint=True, verbose=True):
    """Drive n_vehicles for n_steps and return per-segment activity totals."""
    n_vehicles = config.N_VEHICLES if n_vehicles is None else n_vehicles
    n_steps = config.N_STEPS if n_steps is None else n_steps

    prepare_network(G)
    signals = prepare_signals(G)
    if verbose:
        src = "OSM-tagged" if signals["tagged"] else "degree>=4 fallback"
        print(f"{len(signals['nodes'])} signalized intersections ({src})")
    nodes = list(G.nodes)
    rng = random.Random(config.RANDOM_SEED)   # own stream, so routes are reproducible

    state = load_checkpoint(config.RAW_DIR, config.RUN_NAME) if use_checkpoint else None
    if state is None:
        segment_totals = {edge: 0.0 for edge in G.edges(keys=True)}
        vehicles = []
        for vid in range(n_vehicles):
            veh = make_vehicle(G, nodes, rng, vid)
            if veh is not None:
                vehicles.append(veh)
        state = {"step": 0, "segment_totals": segment_totals, "vehicles": vehicles}
    else:
        print(f"Resuming from step {state['step']}")
        segment_totals = state["segment_totals"]
        vehicles = state["vehicles"]

    t0 = time.perf_counter()
    for step in range(state["step"], n_steps):
        step_vehicles(vehicles, config.DT, step * config.DT,
                      segment_totals, G, nodes, rng, signals)
        state["step"] = step + 1
        if use_checkpoint and state["step"] % config.CHECKPOINT_EVERY == 0:
            save_checkpoint(state, config.RAW_DIR, config.RUN_NAME)
            print(f"Checkpoint saved at step {state['step']}")
    elapsed = time.perf_counter() - t0

    if verbose:
        done = n_steps - 0
        rate = (max(len(vehicles), 1) * done) / elapsed if elapsed > 0 else float("inf")
        print(f"{len(vehicles):>5} vehicles x {n_steps} steps "
              f"in {elapsed:6.2f}s  ({rate:>10,.0f} vehicle-steps/s)")
    return segment_totals


def benchmark(G):
    """Early computational-complexity read (Christof, Jun 22): hold the network
    fixed and watch wall time grow with vehicle count. Small steps so it is fast."""
    print(f"Runtime read on the Powell network ({G.number_of_nodes()} nodes, "
          f"{G.number_of_edges()} edges):")
    for n_vehicles in (50, 100, 250, 500, 1000):
        run_simulation(G, n_vehicles=n_vehicles, n_steps=200,
                       use_checkpoint=False, verbose=True)


def save_results(segment_totals):
    """Write final per-segment results as one tidy table.
    parquet keeps data types and stays compact. Switch to .to_csv if you ever
    want a file you can open and read by eye."""
    rows = [{"u": u, "v": v, "key": k, "value": val}
            for (u, v, k), val in segment_totals.items()]
    df = pd.DataFrame(rows)
    out = os.path.join(config.PROCESSED_DIR, f"{config.RUN_NAME}_segments.parquet")
    df.to_parquet(out)
    print(f"Saved {len(df)} segment results to {out}")


if __name__ == "__main__":
    set_seeds(config.RANDOM_SEED)
    G = get_network()
    if len(sys.argv) > 1 and sys.argv[1] == "benchmark":
        benchmark(G)
    else:
        totals = run_simulation(G)
        save_results(totals)
