"""STAGE 1: GENERATE DATA.

Runs the agent-based simulation and writes its results to disk. This script does
no plotting. Its only job is to produce data files that visualize.py reads later.
Keeping it plot-free is what lets you redraw any figure without rerunning the sim.

Run it with:
    python src/generate.py            # full run from config.py
    python src/generate.py benchmark  # quick runtime read at several vehicle counts
    python src/generate.py closure    # before/after road-closure experiment
    python src/generate.py day        # 24-hour time-of-day NO2 (hourly surfaces)

The model: real vehicles drive the OSMnx network with routes, follow each other
via the IDM kernel, queue at signals, and back up across intersections (spillback).
Each vehicle's instantaneous speed and acceleration feed the HBEFA3 emission model,
so the run accumulates NOx grams per segment (the NO2 path, week 5) alongside raw
vehicle-seconds of activity.
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
import emissions
import fleet
import drivers
import mobil
import webster
import landuse_data
import lodes_od
import demand_data
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


def _parse_lanes(data):
    """Per-direction lane count for one directed edge, from the OSM 'lanes' tag.

    Three rules, all a priori from map data (see config LANES_ENABLED):
      - list values (OSMnx merged stretches with different counts) take the MIN:
        a road that narrows from 3 lanes to 2 carries what the 2-lane bottleneck
        allows, like the narrowest point of a pipe;
      - OSM 'lanes' counts BOTH directions on a two-way street, and our directed
        graph carries the same tag on each direction's edge, so halve it unless
        the street is one-way;
      - untagged edges (mostly residentials) default to 1, and everything is
        clamped to [1, LANES_MAX] so a mistagged edge cannot go wild.
    """
    # Both lane modes need the same physical fact (how many lanes this direction
    # has); they differ only in what they DO with it -- virtual follow-N-ahead
    # lanes (Phase 1) or explicit per-car lane identity with MOBIL (Phase 3).
    # With both flags off every count is 1 and the model is single file.
    if not (config.LANES_ENABLED or config.MOBIL_ENABLED):
        return 1
    raw = data.get("lanes")
    if raw is None:
        return 1
    vals = raw if isinstance(raw, list) else [raw]
    counts = []
    for x in vals:
        try:
            counts.append(int(float(str(x).strip())))
        except ValueError:
            continue                      # unreadable tag piece: ignore it
    if not counts:
        return 1
    n = min(counts)                       # bottleneck rule for merged edges
    oneway = data.get("oneway")
    if isinstance(oneway, list):
        oneway = oneway[0]
    is_oneway = (oneway is True) or (str(oneway).strip().lower()
                                     in ("yes", "true", "1", "-1"))
    if not is_oneway:
        n = n // 2                        # split the two-way total per direction
    return max(1, min(n, config.LANES_MAX))


# --- road closure -----------------------------------------------------------
# A closure removes street segments from the graph before routing, so vehicles
# reroute around the gap. This is the mentor's Jun 23 idea: the case where the ABM
# beats a static land-use model, because the land use is unchanged but the traffic
# moves. See config.CLOSURE for the zone definition.


def _haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters between two lat/lon points.
    Used to decide which edges fall inside a circular closure zone."""
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def closed_edges_in_zone(G, closure=None):
    """List the (u, v, k) edge keys whose midpoint falls inside the closure zone,
    without changing G. Both the simulation (to remove them) and the visualizer
    (to draw them) use this, so they always agree on what is closed."""
    closure = config.CLOSURE if closure is None else closure
    lat0, lon0, radius_m = closure
    closed = []
    for u, v, k in G.edges(keys=True):
        # midpoint of the segment from its two endpoints (x = lon, y = lat)
        mid_lat = 0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"]))
        mid_lon = 0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"]))
        if _haversine_m(lat0, lon0, mid_lat, mid_lon) <= radius_m:
            closed.append((u, v, k))
    return closed


def apply_closure(G, closure=None):
    """Remove every street segment in the closure zone. Mutates G in place and
    returns the list of removed (u, v, k) edge keys. Pass a copy of G if you need
    the open network afterward."""
    removed = closed_edges_in_zone(G, closure)
    G.remove_edges_from(removed)
    return removed


# --- freeway closure ---------------------------------------------------------
# Closing a freeway is a different shape of edit than closing a street, and the
# circular zone above cannot express it. Two reasons, both measured on the metro
# graph (62,299 nodes / 159,425 directed edges):
#   1. Freeway segments are long. I-205 mainline edges run 277 m to 4,411 m with
#      a 735 m median, so a circle small enough to spare the neighborhood catches
#      almost no freeway. A 150 m circle centered on an I-205 segment closes one
#      freeway edge.
#   2. A circle large enough to cut the freeway also deletes the surface streets
#      underneath and beside it. An 800 m circle closes 245 edges, of which 240
#      are surface streets, so it models a demolished district rather than a
#      closed freeway.
# A freeway closure therefore selects by ROUTE and ROAD CLASS, and only then by
# geometry. The streets under the viaduct stay open, which is the whole point:
# the detour traffic has to land somewhere, and that somewhere is the local grid.


def _as_tag_list(v):
    """OSM tags come back as a single value or a list, depending on whether the
    way carried one value or several. Normalize to a list so callers can just
    iterate."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _edge_is_class(d, classes):
    """True if the edge's highway tag names any of `classes`."""
    return any(str(h) in classes for h in _as_tag_list(d.get("highway")))


def _edge_on_route(d, ref):
    """True if the edge carries route `ref` (e.g. 'I 205') in its ref tag.
    Substring match, because a shared stretch tags as e.g. ['I 205', 'OR 213']."""
    return any(ref in str(x) for x in _as_tag_list(d.get("ref")))


def freeway_mainline_edges(G, ref):
    """Every (u, v, k) on route `ref` tagged highway=motorway. This is the
    through-lanes only: ramps are highway=motorway_link and are handled
    separately, because on OSM they usually do NOT carry the route's ref
    (I-205 has 99 ramp edges touching its mainline and zero of them are
    ref-tagged 'I 205', so ramps must be found by topology, not by tag)."""
    return [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True)
            if _edge_on_route(d, ref) and _edge_is_class(d, ("motorway",))]


def _ramp_edges_at(G, nodes):
    """Every motorway_link edge touching any node in `nodes`, in either
    direction. These are the on- and off-ramps of an interchange."""
    ramps = []
    for u, v, k, d in G.edges(keys=True, data=True):
        if _edge_is_class(d, ("motorway_link",)) and (u in nodes or v in nodes):
            ramps.append((u, v, k))
    return ramps


# Compass direction of travel -> (node coordinate axis, sign of displacement).
_DIRECTION_AXES = {"N": ("y", 1.0), "S": ("y", -1.0),
                   "E": ("x", 1.0), "W": ("x", -1.0)}


def _directional_subset(G, edges, direction):
    """The subset of `edges` whose net endpoint displacement points along
    compass `direction` ('N', 'S', 'E', 'W'). Dual carriageways are separate
    directed ways in OSM, so on a straight stretch the net displacement of an
    edge identifies its carriageway. An edge with ZERO displacement on the
    chosen axis is ambiguous, and a wrong guess would close the opposite
    carriageway, so that is a hard error rather than a silent pick."""
    axis, sign = _DIRECTION_AXES[direction]
    keep = []
    for u, v, k in edges:
        d = sign * (float(G.nodes[v][axis]) - float(G.nodes[u][axis]))
        if d > 0:
            keep.append((u, v, k))
        elif d == 0:
            raise ValueError(
                f"edge ({u}, {v}, {k}) has zero {axis}-displacement, so its "
                f"direction is ambiguous; refusing to guess for {direction!r}")
    return keep


def closed_freeway_edges(G, spec=None):
    """List the (u, v, k) edge keys a freeway closure removes, without changing G.

    Like closed_edges_in_zone, this is shared by the simulation and the figures so
    the two can never disagree about what was closed.

    `spec` is config.FREEWAY_CLOSURE, a dict:
        ref         route as OSM tags it, e.g. 'I 205'          (required)
        name        close a named structure, e.g. 'Abernethy Bridge'
        center      (lat, lon) with radius_m, to close a stretch instead
        radius_m    stretch half-length in meters, used with center
        close_ramps close the on/off ramps stranded inside the closed stretch
        direction   optional: close ONE direction of travel only, 'N', 'S',
                    'E' or 'W' (the compass heading of the traffic). Needed
                    for real closures like the Sept 2026 Rose Quarter work,
                    which shuts I-5 southbound while northbound stays open.
                    Direction is judged by net endpoint displacement, which is
                    unambiguous on a straight stretch; an edge with zero
                    displacement on the chosen axis raises instead of guessing.

    Give either `name` or `center` + `radius_m`, not both. Selecting a named
    structure is the honest way to model 'they closed the bridge', since OSM
    already carries the structure name and no coordinate guessing is involved.
    """
    spec = config.FREEWAY_CLOSURE if spec is None else spec
    ref = spec["ref"]
    name = spec.get("name")
    center = spec.get("center")
    radius_m = spec.get("radius_m")
    if (name is None) == (center is None):
        raise ValueError("freeway closure needs exactly one of name / center")

    mainline = freeway_mainline_edges(G, ref)
    if not mainline:
        raise ValueError(f"no highway=motorway edges found on route {ref!r}")

    closed = []
    for u, v, k in mainline:
        d = G.edges[u, v, k]
        if name is not None:
            if any(str(n) == name for n in _as_tag_list(d.get("name"))):
                closed.append((u, v, k))
        else:
            mid_lat = 0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"]))
            mid_lon = 0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"]))
            if _haversine_m(center[0], center[1], mid_lat, mid_lon) <= radius_m:
                closed.append((u, v, k))
    if not closed:
        raise ValueError(f"freeway closure on {ref!r} selected no edges; "
                         f"check the name/center against the graph")

    direction = spec.get("direction")
    if direction is not None:
        if direction not in _DIRECTION_AXES:
            raise ValueError(f"direction must be one of "
                             f"{sorted(_DIRECTION_AXES)}, got {direction!r}")
        closed = _directional_subset(G, closed, direction)
        if not closed:
            raise ValueError(f"freeway closure on {ref!r} selected no "
                             f"{direction}-bound edges in the zone")

    if not spec.get("close_ramps", True):
        return closed

    # Ramps: a driver cannot enter a stretch of freeway that is shut, so the
    # ramps INSIDE the closure go too. A node counts as inside only if every
    # mainline edge touching it is closed. Nodes at the two ends still carry an
    # open mainline edge, so they stay open and become the diversion points
    # where traffic leaves the freeway. Without this rule the model would let
    # cars ramp onto a closed freeway and sit on an unreachable segment.
    closed_set = set(closed)
    touched, still_open = set(), set()
    for u, v, k in mainline:
        touched.add(u)
        touched.add(v)
        if (u, v, k) not in closed_set:
            still_open.add(u)
            still_open.add(v)
    interior = touched - still_open
    return closed + _ramp_edges_at(G, interior)


def apply_freeway_closure(G, spec=None):
    """Remove a freeway stretch (and its stranded ramps) from G. Mutates G in
    place and returns the removed (u, v, k) keys. Pass a copy of G if you need
    the open network afterward."""
    removed = closed_freeway_edges(G, spec)
    G.remove_edges_from(removed)
    return removed


def prepare_network(G):
    """Give every edge a desired speed in m/s ('v0_mps'), a free-flow travel time
    ('travel_time_s'), and ensure a length. Each car uses its current segment's
    v0_mps as its target speed in the IDM, and routes on travel_time_s."""
    # Lane counts come from lanes_real when config.LANES_REAL is on. Its
    # imputation for untagged edges is the median of the same road class in THIS
    # graph, so it is computed once here, from the network being prepared, rather
    # than per edge. With LANES_REAL off this stays None and _parse_lanes runs.
    medians = None
    if getattr(config, "LANES_REAL", False) and (config.LANES_ENABLED
                                                 or config.MOBIL_ENABLED):
        import lanes_real
        medians = lanes_real.class_medians(G)
    for _u, _v, _k, data in G.edges(keys=True, data=True):
        if "length" not in data or data["length"] is None:
            data["length"] = 10.0
        kph = _parse_maxspeed_kph(data.get("maxspeed"))
        if kph is None:
            kph = _default_kph(data.get("highway"))
        data["v0_mps"] = max(kph, 8.0) / 3.6   # floor at 8 km/h so nothing is stuck
        # free-flow seconds to traverse this segment. Routing on time (not length)
        # makes drivers prefer faster arterials over short slow side streets, which
        # is how real trips concentrate on the main roads the city counts as busy.
        data["travel_time_s"] = data["length"] / data["v0_mps"]
        # per-direction lane count (1 unless the lanes experiment is on)
        if medians is None:
            data["n_lanes"] = _parse_lanes(data)
        else:
            import lanes_real
            data["n_lanes"] = lanes_real.directional_lanes(data, medians)
    return G


# --- traffic signals -------------------------------------------------------
# A signalized intersection runs two phases. Each incoming edge is assigned to a
# phase by its compass bearing: roughly east-west approaches share one phase,
# north-south approaches the other, so cross streets alternate green. The current
# green phase at a node is a function of the clock plus a per-node offset (so the
# whole grid is not synchronized). This is a deliberately simple, transparent
# model; real per-signal timing plans are not public (see DATASETS.md).
#
# By default every signal runs the SAME uniform cycle (config.SIGNAL_CYCLE_S) and
# an even split (config.SIGNAL_GREEN_SPLIT), regardless of how lopsided its actual
# approach volumes are. With config.WEBSTER_ENABLED (traffic-realism Phase 4,
# increment 2) each intersection instead gets its OWN cycle length and green split,
# derived by Webster's formula (src/webster.py) from the modeled approach flows, so
# a heavy approach earns more green than a light one; and each phase change shows a
# yellow + all-red clearance interval during which neither phase is green. The flag
# is off by default and provably inert when off: with no per-node plan the signal
# takes the byte-for-byte original uniform code path below (proven by the pinned
# kernel_regression trajectories and the webster_network_scenarios inertness gate).


def _approach_phase(G, u, v):
    """Phase (0 = east-west, 1 = north-south) for travel from node u to node v,
    from the bearing of the segment. Used to decide which approaches share green."""
    x1, y1 = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
    x2, y2 = float(G.nodes[v]["x"]), float(G.nodes[v]["y"])
    ang = math.degrees(math.atan2(x2 - x1, y2 - y1)) % 180   # 0 = N/S, 90 = E/W
    return 0 if 45 <= ang < 135 else 1


def build_webster_plans(G, signal_nodes, edge_phase, flows):
    """Per-node Webster timing from measured approach flows. Returns
    (node_cycle, node_split) dicts keyed by signalized node.

    For each signalized node, its incoming edges are grouped by phase (0 = EW,
    1 = NS via `edge_phase`). Webster times each phase from its CRITICAL (heaviest)
    approach, so per phase we take the maximum approach flow (veh/h from `flows`,
    default 0 for an approach that never carried a car in the warmup) and the lane
    count of that critical approach (edge data `n_lanes`, which is 1 in the base
    single-lane model and the real per-direction count when a lane flag is on).
    `webster.cycle_and_split` then returns this node's cycle and EW green split;
    config.WEBSTER_* supplies the saturation flow, lost time, and clamps.
    """
    node_cycle, node_split = {}, {}
    for n in signal_nodes:
        # per-phase (critical flow, lane count of that critical approach)
        crit = {0: (0.0, 1), 1: (0.0, 1)}
        for u, v, k in G.in_edges(n, keys=True):
            ph = edge_phase[(u, v, k)]
            q = flows.get((u, v, k), 0.0)
            if q >= crit[ph][0]:            # >= so a lane count is set even at q==0
                lanes = G.edges[u, v, k].get("n_lanes", 1)
                crit[ph] = (q, lanes)
        cycle, split_ew = webster.cycle_and_split(
            crit[0][0], crit[1][0], n_lanes_ew=crit[0][1], n_lanes_ns=crit[1][1],
            sat_flow=config.WEBSTER_SAT_FLOW, lost_time_s=config.WEBSTER_LOST_TIME_S,
            cycle_min_s=config.WEBSTER_CYCLE_MIN_S, cycle_max_s=config.WEBSTER_CYCLE_MAX_S,
            min_green_s=config.WEBSTER_MIN_GREEN_S)
        node_cycle[n] = cycle
        node_split[n] = split_ew
    return node_cycle, node_split


# --- green-wave coordination (Phase 4, increment 2b) ------------------------
# 2a gives every signal its OWN Webster cycle. A progression band needs the
# OPPOSITE -- one shared cycle across a chain of signals -- so the functions
# below identify an ordered chain of signalized nodes on one named street and
# recompute a common cycle + travel-time offsets for just those nodes. Every
# other signal (and, within the chain, every member's own green SPLIT) is left
# exactly as 2a computed it. See config.WEBSTER_GREENWAVE_* for the flags.

def _matched_edges(G, street_name):
    """Edge keys (u, v, k) whose OSM 'name' tag contains `street_name` as a
    case-insensitive substring. OSM 'name' is a plain string, but OSMnx can merge
    parallel ways into one edge with a LIST of names -- checked element-wise, so
    either shape works. Returns [] if nothing matches (e.g. the real 1.5 km
    corridor graph and 'Powell' -- verified Jul 19 that none of its 21 OSM-tagged
    signals touch a Powell edge; this function returning [] there is correct,
    not a bug)."""
    needle = street_name.lower()
    matched = []
    for u, v, k, d in G.edges(keys=True, data=True):
        name = d.get("name")
        if name is None:
            continue
        names = name if isinstance(name, list) else [name]
        if any(needle in str(nm).lower() for nm in names):
            matched.append((u, v, k))
    return matched


def find_signal_chain(G, signal_nodes, street_name):
    """Order the signalized nodes on a named street into a coordination chain.

    A node qualifies as a member iff it is signalized AND touches at least one
    edge matched by `_matched_edges`. Members are then ordered by projecting
    each node's (x, y) onto the DOMINANT AXIS of the matched edges -- the mean
    unit bearing vector over all of them -- rather than assuming the corridor
    runs due east-west or north-south, or walking a specific edge sequence: a
    real corridor can jog, and OSM can tag it as several non-contiguous edges
    sharing a name, so a single geometric projection is more robust than a walk.
    Returns [] if fewer than 2 signalized nodes match (nothing to coordinate --
    the caller treats this as "no chain found", not an error) or if the matched
    edges' bearings cancel to a zero vector (no usable axis, e.g. a name shared
    equally by a north and a south leg)."""
    matched = _matched_edges(G, street_name)
    if not matched:
        return []
    members = {n for u, v, k in matched for n in (u, v) if n in signal_nodes}
    if len(members) < 2:
        return []

    dx_sum, dy_sum = 0.0, 0.0
    for u, v, k in matched:
        x1, y1 = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
        x2, y2 = float(G.nodes[v]["x"]), float(G.nodes[v]["y"])
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1.0
        dx_sum += dx / norm      # unit vectors, so one long edge cannot dominate
        dy_sum += dy / norm      # the axis over several short ones
    axis_norm = math.hypot(dx_sum, dy_sum)
    if axis_norm == 0.0:
        return []
    ax, ay = dx_sum / axis_norm, dy_sum / axis_norm
    return sorted(members, key=lambda n: float(G.nodes[n]["x"]) * ax
                                        + float(G.nodes[n]["y"]) * ay)


def _chain_phase_at_node(node, edge_phase, matched_edges):
    """Which phase (0 = EW / 1 = NS) the chain street serves AT this node,
    read directly from the bearing of the MATCHED edges touching it -- never
    assumed to be the same phase index as any other member. A corridor can jog,
    and its local bearing can cross the EW/NS 45-degree boundary at one
    particular intersection even while the rest of the chain does not (that is
    the whole reason this is computed per node instead of once for the chain).
    A node touching matched edges of both phases (a jog's own corner) breaks
    the tie toward phase 0 -- arbitrary, but deterministic and documented."""
    phases = [edge_phase[e] for e in matched_edges if node in e[:2]]
    return 0 if phases.count(0) >= phases.count(1) else 1


def _chain_travel_time_s(G, n_from, n_to, progression_speed_mps):
    """Free-flow travel time (s) from n_from to n_to at the FIXED progression
    design speed (config.WEBSTER_PROGRESSION_SPEED_KPH -- NOT each edge's own
    posted limit, which the base IDM still uses for actual car-following; a
    green-wave band is designed around one assumed platoon speed, the standard
    textbook construction). Uses the shortest path BY LENGTH over the whole
    graph rather than requiring a direct edge between the two nodes: a named
    street's signalized nodes are often not directly joined, because OSM splits
    a way at ordinary (unsignalized) nodes in between too. Falls back to the
    straight-line haversine distance if no path exists at all (should not arise
    between two members of one connected chain; keeps this function total
    rather than raising)."""
    try:
        dist_m = nx.shortest_path_length(G, n_from, n_to, weight="length")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        y1, x1 = float(G.nodes[n_from]["y"]), float(G.nodes[n_from]["x"])
        y2, x2 = float(G.nodes[n_to]["y"]), float(G.nodes[n_to]["x"])
        dist_m = _haversine_m(y1, x1, y2, x2)
    return dist_m / progression_speed_mps


def apply_greenwave(G, signal_nodes, edge_phase, node_cycle, node_split, offset):
    """Green-wave coordination along config.WEBSTER_GREENWAVE_STREET. MUTATES
    `node_cycle` and `offset` IN PLACE for the chain's member nodes only --
    `node_split` and every non-member node are left exactly as 2a computed them.
    Returns the ordered list of member nodes (empty if nothing to coordinate).

    Common cycle: 2a gives every signal its own Webster cycle; a progression
    needs one SHARED cycle, so members adopt a common coordination cycle = the
    MAX of their own (already-computed) Webster cycles. The max is the smallest
    common cycle that still fits every member's own critical approach -- a
    smaller shared cycle would undercut whichever member's own Webster plan
    needed the longest cycle, re-saturating it.

    Green split: each member's split is a FRACTION of the cycle (by
    construction, see webster.py), so keeping node_split[n] unchanged and only
    replacing node_cycle[n] with the common cycle already gives that member the
    same proportional green on the new, generally longer, cycle -- is_green
    recomputes the window boundary (split * cycle) at call time, so nothing
    else needs to change for this half of the design.

    Offsets: a platoon leaving member 0's own chain-phase green start should
    arrive at every downstream member during ITS chain-phase green too. Member
    i's own green-window-start TIME (mod C) is (g_i - offset_i) mod C, where g_i
    is the window's own start position on the cycle -- 0 if the chain phase at
    i is EW (phase 0's window always starts at 0, see is_green), or
    node_split[i] * C if NS (phase 1's window starts where phase 0's ends).
    Requiring member i's window-start time to lag member 0's by exactly the
    cumulative free-flow travel time at the progression speed gives:

        offset_i = (offset_0 + (g_i - g_0) - cum_travel_i) mod C

    with member 0's OWN offset (already drawn by prepare_signals on the uniform
    per-node cycle) kept as the arbitrary anchor, and cum_travel_0 = 0."""
    chain = find_signal_chain(G, signal_nodes, config.WEBSTER_GREENWAVE_STREET)
    if len(chain) < 2:
        print(f"  green-wave: no chain found for street "
              f"'{config.WEBSTER_GREENWAVE_STREET}' (need >=2 signalized nodes "
              f"on a matching street) -- coordination skipped, per-node Webster "
              f"timing (2a) stands unchanged.")
        return []

    matched = _matched_edges(G, config.WEBSTER_GREENWAVE_STREET)
    chain_phase = {n: _chain_phase_at_node(n, edge_phase, matched) for n in chain}
    common_cycle = max(node_cycle[n] for n in chain)
    progression_mps = config.WEBSTER_PROGRESSION_SPEED_KPH / 3.6

    n0 = chain[0]
    offset0 = offset[n0]
    g0 = 0.0 if chain_phase[n0] == 0 else node_split[n0] * common_cycle
    for n in chain:
        node_cycle[n] = common_cycle    # common cycle; node_split[n] untouched
    for n in chain[1:]:
        g_i = 0.0 if chain_phase[n] == 0 else node_split[n] * common_cycle
        cum_travel = _chain_travel_time_s(G, n0, n, progression_mps)
        offset[n] = (offset0 + (g_i - g0) - cum_travel) % common_cycle

    print(f"  green-wave ON: '{config.WEBSTER_GREENWAVE_STREET}' chain of "
          f"{len(chain)} signals {chain}, common cycle {common_cycle:.1f}s, "
          f"progression speed {config.WEBSTER_PROGRESSION_SPEED_KPH:.0f} km/h")
    return chain


def prepare_signals(G, flows=None):
    """Find signalized nodes and precompute each edge's phase and each node's
    cycle offset. Prefers real OSM 'traffic_signals' node tags; if the graph has
    none, falls back to treating every 4-way+ intersection as signalized.

    With config.WEBSTER_ENABLED and a `flows` dict (per-approach veh/h, from the
    measurement pre-pass or injected by a gate), each signalized node additionally
    gets its own Webster cycle length and green split (node_cycle / node_split), a
    yellow+all-red clearance interval, and a per-node offset drawn on its OWN cycle.
    Off by default: node_cycle stays None and is_green takes the uniform base path,
    byte-for-byte unchanged.

    With config.WEBSTER_GREENWAVE_ENABLED on top (increment 2b), the members of
    one named street's signal chain (config.WEBSTER_GREENWAVE_STREET) additionally
    get a shared coordination cycle and travel-time offsets on top of their 2a
    plans -- see `apply_greenwave`. Meaningless without Webster (there is no
    per-node cycle to coordinate), so it is refused loudly, same style as
    build_mobil_context refusing LANES_ENABLED+MOBIL_ENABLED together."""
    if config.WEBSTER_GREENWAVE_ENABLED and not config.WEBSTER_ENABLED:
        raise ValueError(
            "WEBSTER_GREENWAVE_ENABLED requires WEBSTER_ENABLED: green-wave "
            "coordination builds a shared cycle from each member's own Webster "
            "plan, and there is no Webster plan to coordinate with it off. Turn "
            "WEBSTER_ENABLED on too, or turn WEBSTER_GREENWAVE_ENABLED off.")

    signal_nodes = {n for n, d in G.nodes(data=True)
                    if "traffic_signals" in str(d.get("highway", ""))}
    tagged = len(signal_nodes)
    if not signal_nodes:
        signal_nodes = {n for n in G.nodes if G.degree(n) >= 4}

    sig_rng = random.Random(config.RANDOM_SEED + 1)   # own stream, reproducible
    offset = {n: sig_rng.uniform(0.0, config.SIGNAL_CYCLE_S) for n in signal_nodes}
    edge_phase = {(u, v, k): _approach_phase(G, u, v)
                  for u, v, k in G.edges(keys=True)}
    sig = {
        "nodes": signal_nodes, "offset": offset, "edge_phase": edge_phase,
        "cycle": config.SIGNAL_CYCLE_S, "green_split": config.SIGNAL_GREEN_SPLIT,
        "tagged": tagged,
        # Webster (increment 2): None unless the flag is on AND flows are supplied,
        # so the default dict drives the uniform base path in is_green unchanged.
        "node_cycle": None, "node_split": None, "clearance": 0.0,
        # Green-wave (increment 2b): the coordinated chain's member nodes, empty
        # unless WEBSTER_GREENWAVE_ENABLED found one (see apply_greenwave).
        "greenwave_chain": [],
    }
    if config.WEBSTER_ENABLED and flows is not None:
        node_cycle, node_split = build_webster_plans(G, signal_nodes, edge_phase, flows)
        # Redraw each offset on the node's OWN cycle length (the base draw used the
        # uniform cycle). This is still the 2a offset for every node; green-wave
        # coordination (below) then overwrites cycle+offset for chain members only.
        off_rng = random.Random(config.RANDOM_SEED + 1)
        offset = {n: off_rng.uniform(0.0, node_cycle[n]) for n in signal_nodes}
        sig["offset"] = offset
        sig["node_cycle"] = node_cycle
        sig["node_split"] = node_split
        sig["clearance"] = config.WEBSTER_YELLOW_S + config.WEBSTER_ALL_RED_S
        if config.WEBSTER_GREENWAVE_ENABLED:
            # Mutates node_cycle/offset in place for chain members only; both
            # dicts are the same objects already stored in `sig` above, so no
            # further reassignment is needed here.
            sig["greenwave_chain"] = apply_greenwave(
                G, signal_nodes, edge_phase, node_cycle, node_split, offset)
    return sig


def is_green(signals, node, phase, t):
    """Is `phase` showing green at this signalized node at time t (seconds)?"""
    node_cycle = signals.get("node_cycle")
    if node_cycle is None:
        # Uniform base model -- byte-for-byte the original single-cycle signal.
        frac = ((t + signals["offset"][node]) % signals["cycle"]) / signals["cycle"]
        green_phase = 0 if frac < signals["green_split"] else 1
        return phase == green_phase
    # Webster: this node's own cycle and split, plus a clearance interval at the end
    # of each phase (yellow + all-red) during which NEITHER phase is green. The EW
    # phase owns [0, split*cycle); NS owns the rest. A car reaching the line inside
    # its phase's clearance stops, as at a real yellow-then-red.
    cycle = node_cycle[node]
    split = signals["node_split"][node]
    clr = signals["clearance"]
    local = (t + signals["offset"][node]) % cycle
    ew_window = split * cycle
    if local < ew_window:
        active, phase_end = 0, ew_window
    else:
        active, phase_end = 1, cycle
    if phase != active:
        return False
    return (phase_end - local) > clr


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


def build_od_demand(G, nodes):
    """Build a real origin-destination demand context from LODES commute flows.

    Where build_demand_weights approximates trips as population x jobs x decay (a
    gravity guess at the joint home->work distribution), this uses the REAL joint
    distribution: LODES counts of commuters from each home block group to each work
    block group (src/lodes_od.py). A trip draws a home-BG -> work-BG pair in
    proportion to that flow, then lands on a random network node inside each end's
    block group.

    Each node is assigned to its nearest study-area block-group centroid (the same
    Voronoi split build_demand_weights uses), giving each block group the set of nodes
    that represent it. Only OD pairs whose home AND work block groups both caught at
    least one node survive (a pair with no node to place an end cannot be realized).

    Returns a `demand` dict tagged mode="od" (pair block-group lists, flow weights, and
    each block group's node list), or None if OD demand is off or the flow table is
    empty, so the caller falls back to gravity or uniform-random trips.
    """
    if not config.DEMAND_LODES_OD:
        return None
    try:
        od = lodes_od.od_table()
        lu = landuse_data.landuse_table()
    except Exception as e:
        print(f"  LODES OD demand unavailable ({e}); falling back")
        return None
    if len(od) == 0 or len(lu) == 0:
        print("  no LODES OD flows in the study area; falling back")
        return None

    # assign each node to its nearest block-group centroid (same projection and
    # nearest-centroid rule as build_demand_weights, so the two demand models place
    # trips on the same node-to-block-group map)
    lat0, lon0 = config.STUDY_CENTER
    mx = 111_320.0 * math.cos(math.radians(lat0))
    node_x = (np.array([float(G.nodes[n]["x"]) for n in nodes]) - lon0) * mx
    node_y = (np.array([float(G.nodes[n]["y"]) for n in nodes]) - lat0) * 110_540.0
    bg_x = (lu["lon"].to_numpy() - lon0) * mx
    bg_y = (lu["lat"].to_numpy() - lat0) * 110_540.0
    d2 = (node_x[:, None] - bg_x[None, :]) ** 2 + (node_y[:, None] - bg_y[None, :]) ** 2
    nearest = d2.argmin(axis=1)

    # each block group -> the list of node IDs assigned to it
    bg_geoids = lu["bg_geoid"].tolist()
    bg_nodes = {g: [] for g in bg_geoids}
    for ni, bi in enumerate(nearest):
        bg_nodes[bg_geoids[bi]].append(nodes[ni])

    # keep only flows whose home and work block groups both own at least one node
    pairs_h, pairs_w, weights = [], [], []
    for r in od.itertuples():
        if bg_nodes.get(r.h_bg) and bg_nodes.get(r.w_bg):
            pairs_h.append(r.h_bg)
            pairs_w.append(r.w_bg)
            weights.append(float(r.flow))
    if not weights:
        print("  LODES OD flows have no placeable node; falling back")
        return None

    kept_flow = sum(weights)
    print(f"  LODES OD demand: {len(weights)} placeable home->work BG pairs, "
          f"{int(kept_flow):,} commuters ({100*kept_flow/od['flow'].sum():.0f}% of "
          f"study-area flow placeable)")
    return {
        "mode": "od",
        "pairs_h": pairs_h,     # home block group per flow pair
        "pairs_w": pairs_w,     # work block group per flow pair
        "weights": weights,     # commuter counts (draw pairs in proportion to these)
        "bg_nodes": bg_nodes,   # block group -> list of node IDs inside it
    }


def build_demand_weights(G, nodes):
    """Turn the real population/jobs masses into per-node origin and destination
    weights, aligned with `nodes`. Trips then start where people live (origins
    weighted by resident population) and end where the jobs are (destinations
    weighted by employment), instead of uniformly at random.

    Each network node is assigned to the nearest block-group centroid, and that
    block group's population and jobs are spread evenly over all the nodes assigned
    to it (a Voronoi split). Spreading the mass over many nodes, rather than dumping
    each block group's whole population on the single node nearest its centroid,
    avoids a handful of artificial point sources and gives a smooth density that
    every street corner in a populated area shares.

    Destinations also get a distance-decay term (config.GRAVITY_DECAY_SCALE_M):
    given a chosen origin, each candidate destination's job weight is multiplied by
    exp(-distance / scale), so nearer jobs are likelier. That is the gravity-model
    deterrence that keeps trips mostly local instead of funneling everyone across
    the area to the single largest job center. The decay needs the origin, so it is
    applied per-trip in make_vehicle; this function returns the pieces it needs.

    Returns a `demand` dict (origin weights, job weights, node coordinates in local
    meters, a node->index map, and the decay scale), or None if gravity demand is
    off or the land-use data is missing, so the caller falls back to uniform random.

    If config.DEMAND_LODES_OD is on, real LODES origin-destination flows replace the
    gravity guess; this delegates to build_od_demand and only falls through to gravity
    if the OD table is empty or unplaceable.
    """
    if config.DEMAND_LODES_OD:
        od = build_od_demand(G, nodes)
        if od is not None:
            # the non-work layer rides inside the demand dict so every caller
            # (spawn, respawn, warmup) threads it without a signature change
            od["nonwork"] = build_nonwork_demand(G, nodes)
            return od
        # OD requested but unavailable: fall through to the gravity model below
    if not config.DEMAND_GRAVITY:
        return None
    try:
        lu = landuse_data.landuse_table()
    except Exception as e:
        print(f"  gravity demand unavailable ({e}); using uniform-random trips")
        return None
    if len(lu) == 0:
        print("  no land-use block groups in the study area; using uniform-random trips")
        return None

    # project node and block-group coordinates to local meters around the study
    # center (flat approximation; the area is small enough to be accurate to ~1 m)
    lat0, lon0 = config.STUDY_CENTER
    mx = 111_320.0 * math.cos(math.radians(lat0))
    nx_ = np.array([float(G.nodes[n]["x"]) for n in nodes]) - lon0
    ny_ = np.array([float(G.nodes[n]["y"]) for n in nodes]) - lat0
    node_x, node_y = nx_ * mx, ny_ * 110_540.0
    bg_x = (lu["lon"].to_numpy() - lon0) * mx
    bg_y = (lu["lat"].to_numpy() - lat0) * 110_540.0

    # nearest block group for each node (nodes x block groups is tiny: ~978 x ~19)
    d2 = (node_x[:, None] - bg_x[None, :]) ** 2 + (node_y[:, None] - bg_y[None, :]) ** 2
    nearest = d2.argmin(axis=1)
    pop = lu["population"].to_numpy(dtype=float)
    jobs = lu["jobs"].to_numpy(dtype=float)
    # split each block group's mass evenly among the nodes assigned to it, so the
    # block-group totals stay proportional regardless of how many nodes it caught
    counts = np.bincount(nearest, minlength=len(lu)).astype(float)
    counts[counts == 0] = 1.0
    origin_w = pop[nearest] / counts[nearest]
    dest_w = jobs[nearest] / counts[nearest]

    if origin_w.sum() <= 0 or dest_w.sum() <= 0:   # degenerate data: fall back safely
        return None
    scale = config.GRAVITY_DECAY_SCALE_M
    print(f"  gravity demand: {len(lu)} block groups, "
          f"{int(pop.sum()):,} residents, {int(jobs.sum()):,} jobs"
          + (f", decay scale {scale:.0f} m" if scale else ", no distance decay"))
    return {
        "origin_w": origin_w.tolist(),    # list for random.choices (origins)
        "dest_w": dest_w,                 # numpy array for the per-trip decay math
        "dest_w_list": dest_w.tolist(),   # list for the no-decay path
        "node_x": node_x, "node_y": node_y,
        "index": {n: i for i, n in enumerate(nodes)},
        "scale": scale,
        "nonwork": build_nonwork_demand(G, nodes),   # None unless the B3 flag is on
    }


def build_nonwork_demand(G, nodes):
    """The non-work (shopping/errand) trip context (config.DEMAND_NONWORK_ENABLED,
    REAL_DEMAND_UPGRADE_PLAN.md B3). Both commute demand models send every internal
    trip home -> job; this supplies the second layer real travel is mostly made of:
    origins by resident population (same home end as commuting), destinations by
    RETAIL/SERVICE employment (config.NONWORK_SECTORS from the same LODES WAC file),
    with a shorter gravity decay, both shares and decay set a priori from the 2022
    NHTS (see config.py). Same Voronoi node-assignment as build_demand_weights so
    the layers place mass on the same map.

    Returns a dict make_vehicle reads from demand["nonwork"] (share, origin/dest
    weights, node coords, decay scale), or None when the flag is off or the data is
    missing, in which case internal trips stay all-commute and, critically, the
    trip RNG stream is consumed exactly as before the layer existed."""
    if not config.DEMAND_NONWORK_ENABLED:
        return None
    try:
        lu = landuse_data.nonwork_table()
    except Exception as e:
        print(f"  non-work demand unavailable ({e}); internal trips stay all-commute")
        return None
    if len(lu) == 0 or lu["nonwork_attr"].sum() <= 0 or lu["population"].sum() <= 0:
        print("  no non-work attraction mass in the study area; staying all-commute")
        return None

    # identical projection and nearest-centroid rule as build_demand_weights, so
    # the commute and non-work layers share one node-to-block-group map
    lat0, lon0 = config.STUDY_CENTER
    mx = 111_320.0 * math.cos(math.radians(lat0))
    nx_ = np.array([float(G.nodes[n]["x"]) for n in nodes]) - lon0
    ny_ = np.array([float(G.nodes[n]["y"]) for n in nodes]) - lat0
    node_x, node_y = nx_ * mx, ny_ * 110_540.0
    bg_x = (lu["lon"].to_numpy() - lon0) * mx
    bg_y = (lu["lat"].to_numpy() - lat0) * 110_540.0
    d2 = (node_x[:, None] - bg_x[None, :]) ** 2 + (node_y[:, None] - bg_y[None, :]) ** 2
    nearest = d2.argmin(axis=1)
    pop = lu["population"].to_numpy(dtype=float)
    attr = lu["nonwork_attr"].to_numpy(dtype=float)
    counts = np.bincount(nearest, minlength=len(lu)).astype(float)
    counts[counts == 0] = 1.0
    origin_w = pop[nearest] / counts[nearest]
    dest_w = attr[nearest] / counts[nearest]
    if origin_w.sum() <= 0 or dest_w.sum() <= 0:
        return None

    print(f"  non-work demand ON: share {config.NONWORK_SHARE:.3f} of internal trips, "
          f"{len(lu)} block groups, {int(attr.sum()):,} retail/service jobs, "
          f"decay {config.NONWORK_DECAY_SCALE_M:.0f} m")
    return {
        "share": float(config.NONWORK_SHARE),
        "origin_w": origin_w.tolist(),
        "dest_w": dest_w,
        "node_x": node_x, "node_y": node_y,
        "index": {n: i for i, n in enumerate(nodes)},
        "scale": float(config.NONWORK_DECAY_SCALE_M),
    }


def build_through_context(G, nodes):
    """Precompute the boundary (cordon) entry/exit points for through-traffic.

    Through trips model regional traffic passing through the study area: they start
    and end on the PERIMETER of the network instead of inside it. A node is on the
    perimeter if it lies beyond THROUGH_BOUNDARY_FRAC of the study radius from the
    center. Each perimeter node is weighted by the fastest road that meets it (its
    max incident v0_mps), so through-traffic enters mainly on the arterials (Powell,
    Division) the way real regional traffic does, not on residential dead-ends. The
    weights come from geometry and road class only, never from the PBOT counts, so
    the validation stays an honest test.

    Returns a context dict (boundary nodes, entry weights, per-node local-meter
    coords, and the through-trip fraction), or None if the fraction is 0 or there are
    too few boundary nodes to make a crossing trip.
    """
    frac = config.THROUGH_TRAFFIC_FRACTION
    if not frac or frac <= 0:
        return None
    lat0, lon0 = config.STUDY_CENTER
    mx = 111_320.0 * math.cos(math.radians(lat0))
    r_bound = config.THROUGH_BOUNDARY_FRAC * config.STUDY_RADIUS_M
    boundary, weight, bx, by = [], [], [], []
    for n in nodes:
        x = (float(G.nodes[n]["x"]) - lon0) * mx
        y = (float(G.nodes[n]["y"]) - lat0) * 110_540.0
        if math.hypot(x, y) < r_bound:
            continue
        # fastest incident road (in- and out-edges), so arterial crossings dominate
        speeds = [d.get("v0_mps", 8.0) for _a, _b, d in G.edges(n, data=True)]
        speeds += [d.get("v0_mps", 8.0) for _a, _b, d in G.in_edges(n, data=True)]
        boundary.append(n)
        weight.append(max(speeds) if speeds else 8.0)
        bx.append(x)
        by.append(y)
    if len(boundary) < 2:
        print("  through-traffic: too few boundary nodes; disabling")
        return None
    print(f"  through-traffic: {frac:.0%} of trips cross the area, "
          f"{len(boundary)} boundary entry/exit nodes (arterial-weighted)")
    return {"nodes": boundary, "weight": weight,
            "bx": np.array(bx), "by": np.array(by), "fraction": frac}


def build_fleet_context():
    """Precompute the mixed-fleet pieces (config.FLEET_MIXED): the sourced Multnomah
    mix, a class -> coefficient lookup, and a DEDICATED seeded RNG stream for the
    class draws. The separate stream (RANDOM_SEED + 2, alongside the +1 signal
    stream) matters: drawing classes from the trip RNG would shift every later
    origin/destination draw, changing traffic itself. With its own stream the
    routes, activity, and throughput stay bit-identical to the same-seed
    single-class run, so a fleet-vs-diesel comparison isolates emissions only.
    Returns None when the flag is off (single-class path, unchanged behavior)."""
    if not config.FLEET_MIXED:
        return None
    mix = fleet.PORTLAND_FLEET
    fleet.validate(mix)
    print(f"  mixed fleet ON: {len(mix)} HBEFA3 classes (PORTLAND_FLEET), "
          "per-vehicle class drawn at spawn")
    return {
        "mix": mix,
        "coeffs": fleet.HBEFA3_NOX,                    # class name -> (f0..f5)
        "rng": random.Random(config.RANDOM_SEED + 2),  # own stream, reproducible
    }


def build_driver_context():
    """Precompute the driver-heterogeneity pieces (config.DRIVER_HETEROGENEITY):
    the per-parameter sigmas and a DEDICATED seeded RNG stream (RANDOM_SEED + 3,
    alongside the +1 signal and +2 fleet streams) for the per-vehicle IDM draws.
    The separate stream means enabling heterogeneity consumes no trip/route/fleet
    draw, so the same seed spawns the same INITIAL population and only the
    car-following dynamics are changed by hand. The realized traffic does still
    diverge from the homogeneous run -- different dynamics finish trips at
    different times, and respawns then take different trip draws -- which is the
    effect under study, not a seeding leak. Returns None when the flag is off
    (base model: every vehicle uses the config IDM defaults, unchanged
    behavior)."""
    if not config.DRIVER_HETEROGENEITY:
        return None
    sig = drivers.sigmas()
    drivers.validate(sig)
    active = ", ".join(f"{p}~{s}" for p, s in sig.items() if s > 0) or "nothing (all sigma 0)"
    print(f"  driver heterogeneity ON: per-vehicle IDM drawn at spawn (varying {active})")
    return {"rng": random.Random(config.RANDOM_SEED + 3), "sig": sig}


def build_mobil_context(G):
    """Precompute the MOBIL pieces (config.MOBIL_ENABLED): the parameter bundle and
    the per-segment lane counts, keyed like by_edge. Returns None when the flag is
    off (base model, or Phase 1's virtual lanes, both untouched by MOBIL).

    MOBIL and the virtual-lane experiment are two different models of the same
    thing and are mutually exclusive: Phase 1 makes lane identity implicit and
    frictionless (an upper bound on capacity), Phase 3 makes it explicit and pays
    the real cost of finding a gap. Running both at once would double-count lanes,
    so it is refused here rather than silently producing a hybrid."""
    if not config.MOBIL_ENABLED:
        return None
    if config.LANES_ENABLED:
        raise ValueError(
            "LANES_ENABLED and MOBIL_ENABLED are mutually exclusive lane models: "
            "virtual follow-N-ahead lanes (Phase 1) vs explicit per-car lanes with "
            "MOBIL (Phase 3). Turn one off in config.py.")
    lanes = {(u, v, k): d.get("n_lanes", 1)
             for u, v, k, d in G.edges(keys=True, data=True)}
    multi = sum(1 for n in lanes.values() if n > 1)
    print(f"  MOBIL lane changing ON: explicit lane identity, {multi} of "
          f"{len(lanes)} segments have >1 lane (politeness "
          f"{config.MOBIL_POLITENESS}, threshold {config.MOBIL_A_THRESHOLD} m/s^2, "
          f"b_safe {config.MOBIL_B_SAFE} m/s^2)")
    return {"params": mobil.params_from_config(config), "lanes": lanes}


def _veh_idm_accel(veh, leader, edge, L):
    """One IDM acceleration for `veh` with `leader` (a vehicle dict, or None for a
    clear road) ahead of it on the SAME segment. Mirrors the accel pass's
    conventions exactly -- no leader means a huge gap at the car's own speed, and a
    heterogeneous car uses its own drawn parameters -- so MOBIL's six accelerations
    come from the one verified kernel and never a second physics."""
    idm = veh.get("idm")
    v0 = edge[4] * idm["v0_factor"] if idm else edge[4]
    if leader is None:
        gap, lead_v = 1e6, veh["v"]
    else:
        gap, lead_v = leader["pos"] - L - veh["pos"], leader["v"]
    if idm is None:
        return idm_acceleration(veh["v"], gap, lead_v, v0)
    return idm_acceleration(veh["v"], gap, lead_v, v0, a_max=idm["a_max"],
                            b_comf=idm["b_comf"], T=idm["T"], s0=idm["s0"])


def _lane_queues(group, n_lanes, explicit):
    """Split one segment's cars (already sorted back-to-front by pos) into per-lane
    queues, each still sorted back-to-front, so a car's leader is simply the next
    entry in its own queue.

    explicit=False is Phase 1's VIRTUAL lanes: lane identity is queue rank mod N,
    so lane r is group[r::N] and the successor of group[i] in its queue is exactly
    group[i + N] -- the follow-N-ahead rule, unchanged.
    explicit=True is Phase 3: each car carries its own veh["lane"], clamped
    defensively here in case a segment narrowed or a checkpoint predates the flag.
    With N = 1 both produce the single queue [group], i.e. the base model."""
    if n_lanes == 1:
        # the overwhelmingly common case, and the base model's only case: the whole
        # group is one queue. Returned as-is rather than sliced, because group[::1]
        # would copy every segment's car list on every step.
        return [group]
    if not explicit:
        return [group[r::n_lanes] for r in range(n_lanes)]
    queues = [[] for _ in range(n_lanes)]
    for veh in group:
        queues[min(veh.get("lane", 0), n_lanes - 1)].append(veh)
    return queues


def _next_segment_rear(next_group, n_next, veh_lane, explicit):
    """The car whose back a crossing vehicle will meet in the next segment, or None
    if the lane it is entering is clear.

    Virtual lanes: the n_next'th car from the rear, i.e. the rearmost car of the
    emptiest lane (fewer cars there than lanes means a lane is free).
    Explicit lanes: the rearmost car of the lane this vehicle will ACTUALLY enter,
    which is its own index clamped to the new segment's width (the same rule the
    crossing itself applies).
    With n_next = 1 both reduce to next_group[0], the base model's rearmost car."""
    if explicit:
        target = min(veh_lane, n_next - 1)
        for other in next_group:                # ascending by pos: first = rearmost
            if min(other.get("lane", 0), n_next - 1) == target:
                return other
        return None
    return next_group[n_next - 1] if len(next_group) >= n_next else None


def _entry_choice(next_group, n_next, veh_lane, explicit, claims=None):
    """config.MERGE_ENTRY_IMPROVED's counterpart of _next_segment_rear: the lane
    an entering car will ACTUALLY take -- the one with the most room at the
    entrance -- and the effective rearmost car in it (None = that lane is clear).

    Returns (target_lane, rear). Used by BOTH the accel pass's spillback-leader
    lookup and the crossing itself, so the car brakes for exactly the car it
    will end up behind. Ties prefer the lane nearest the car's current index,
    so on a plain edge-to-edge continuation with equal room the car keeps its
    lane and the improved rule reduces to the legacy clamp.

    `claims` (crossing pass only) maps target lane -> the rearmost car that
    already crossed into this segment THIS step. Those cars are invisible in
    the frozen snapshot, so without claims two competing feeders read the same
    gap and land on top of each other; with them, same-step entries serialize:
    the second car sees the first as its effective rear, holds one step, and
    each feeder's queue then follows its own leader across as a wave. Claims
    apply in explicit and single-lane modes; virtual multi-lane keeps lane
    identity implicit, so per-lane claims do not map onto it and it stays on
    the frozen-snapshot rule.

    In virtual-lane and single-lane modes lane identity is implicit, so only
    the rear lookup matters and it already picks the emptiest lane; the legacy
    helper is reused unchanged."""
    def rearmost(a, b):
        if a is None or (b is not None and b["pos"] < a["pos"]):
            return b
        return a

    if not explicit or n_next == 1:
        lane_t = min(veh_lane, n_next - 1) if explicit else veh_lane
        rear = _next_segment_rear(next_group, n_next, veh_lane, explicit) \
            if next_group else None
        if claims and (explicit or n_next == 1):
            rear = rearmost(rear, claims.get(lane_t if explicit else 0))
        return lane_t, rear
    rears = {}
    for other in next_group:                    # ascending by pos: first = rearmost
        ln = min(other.get("lane", 0), n_next - 1)
        if ln not in rears:
            rears[ln] = other
            if len(rears) == n_next:
                break
    best_lane, best_rear, best_room = None, None, -1.0
    for ln in range(n_next):
        rear = rearmost(rears.get(ln), claims.get(ln) if claims else None)
        room = float("inf") if rear is None else rear["pos"]
        if room > best_room or (room == best_room and
                                abs(ln - veh_lane) < abs(best_lane - veh_lane)):
            best_lane, best_rear, best_room = ln, rear, room
    return best_lane, best_rear


def _mobil_lane_pass(by_edge, mobil_ctx, L):
    """Decide every car's lane for this step, from the frozen snapshot.

    Runs BEFORE the acceleration pass and reads only pre-move positions, so the
    decision is simultaneous in the same sense the IDM already is: no car reacts to
    a change another car made this step. Returns a list of (vehicle, new lane) for
    the cars that move, which the caller applies all at once.

    For each car and each ADJACENT lane that exists, the six MOBIL accelerations
    are evaluated from real in-lane neighbours and handed to mobil.wants_change;
    the safe candidate with the largest margin wins, and a car changes at most one
    lane per step.

    Two documented simplifications. (1) The accelerations use in-lane neighbours
    only -- no red-light or spillback term. Those boundary conditions are shared by
    every lane of a segment, so they largely cancel in a lane COMPARISON; where
    they do not (an empty adjacent lane at a red) the effect is cars filling the
    shorter queue, which is what real drivers do, and the accel pass still stops
    everyone at the line. (2) Two cars may pick the same gap in one step; the next
    step's IDM brakes the overlap. A fuller model would add a gap-acceptance
    tie-break."""
    params = mobil_ctx["params"]
    lane_counts = mobil_ctx["lanes"]
    decisions = []
    for key, group in by_edge.items():
        n_lanes = lane_counts.get(key, 1)
        if n_lanes < 2:
            continue                            # nowhere to go: single-file segment
        edge = group[0]["route"][group[0]["idx"]]     # one segment, one geometry
        queues = _lane_queues(group, n_lanes, explicit=True)
        for lane_idx, queue in enumerate(queues):
            for i, veh in enumerate(queue):
                own_leader = queue[i + 1] if i + 1 < len(queue) else None
                own_follower = queue[i - 1] if i > 0 else None
                self_before = _veh_idm_accel(veh, own_leader, edge, L)
                if own_follower is None:
                    old_pair = None             # nobody behind: this change costs no one
                else:
                    old_pair = (_veh_idm_accel(own_follower, veh, edge, L),
                                _veh_idm_accel(own_follower, own_leader, edge, L))
                best_lane, best_margin = None, float("-inf")
                for cand in (lane_idx - 1, lane_idx + 1):
                    if not 0 <= cand < n_lanes:
                        continue
                    # nearest car ahead of and behind this car IN THE TARGET LANE
                    new_leader, new_follower = None, None
                    for other in queues[cand]:
                        if other["pos"] > veh["pos"]:
                            new_leader = other
                            break
                        new_follower = other
                    self_after = _veh_idm_accel(veh, new_leader, edge, L)
                    if new_follower is None:
                        new_pair = None         # empty gap behind: trivially safe
                    else:
                        new_pair = (_veh_idm_accel(new_follower, new_leader, edge, L),
                                    _veh_idm_accel(new_follower, veh, edge, L))
                    change, margin = mobil.wants_change(self_before, self_after,
                                                        old_pair, new_pair, params)
                    if change and margin > best_margin:
                        best_lane, best_margin = cand, margin
                if best_lane is not None:
                    decisions.append((veh, best_lane))
    return decisions


def make_vehicle(G, nodes, rng, vid, demand=None, through=None, fleet_ctx=None,
                 driver_ctx=None):
    """Create one vehicle with an origin, destination, and shortest-time route.
    With a `demand` context, the origin is drawn in proportion to population and the
    destination in proportion to jobs, with a distance-decay pull toward nearer jobs;
    without one, both are uniform random. With a `through` context, a fraction of
    trips instead enter and leave on the network perimeter, modeling regional
    through-traffic. With a `fleet_ctx` (config.FLEET_MIXED), the vehicle also gets
    an HBEFA3 emission class drawn from the fleet mix at spawn, and carries that
    class's coefficients for the whole trip (a respawn draws a fresh class, so the
    steady-state population tracks the mix shares). With a `driver_ctx`
    (config.DRIVER_HETEROGENEITY), the vehicle also gets its own IDM parameter set
    drawn from the driver mix at spawn, carried on veh["idm"] for the whole trip.
    Returns None if no route is found after a few tries.

    With a non-work layer (demand["nonwork"], config.DEMAND_NONWORK_ENABLED), that
    share of internal trips draws its origin from population and its destination
    from retail/service attraction with the shorter non-work decay, modeling
    shopping/errand travel; the rest keep the commute pattern. When the layer is
    absent this branch draws nothing from the RNG, so runs without the flag are
    bit-identical to the pre-layer model."""
    nonwork = demand.get("nonwork") if demand is not None else None
    for _ in range(25):
        if through is not None and rng.random() < through["fraction"]:
            # THROUGH trip: enter on a perimeter node and leave on another, so the
            # trip crosses the study area like regional traffic passing through.
            bnodes, bw = through["nodes"], through["weight"]
            oi = rng.choices(range(len(bnodes)), weights=bw)[0]
            o = bnodes[oi]
            # destination: another boundary node, weighted by its own entry weight
            # AND by distance from the origin, so the trip crosses the area (favoring
            # the far side) instead of hopping between two adjacent perimeter nodes.
            dx = through["bx"] - through["bx"][oi]
            dy = through["by"] - through["by"][oi]
            dist = np.sqrt(dx * dx + dy * dy)
            w = np.asarray(bw) * dist
            d = bnodes[rng.choices(range(len(bnodes)), weights=w.tolist())[0]]
        elif nonwork is not None and rng.random() < nonwork["share"]:
            # NON-WORK trip (shopping/errand): home end drawn from population like
            # any internal trip, but the destination is pulled by retail/service
            # employment under the shorter NHTS-derived decay, not by total jobs.
            o = rng.choices(nodes, weights=nonwork["origin_w"])[0]
            oi = nonwork["index"][o]
            dx = nonwork["node_x"] - nonwork["node_x"][oi]
            dy = nonwork["node_y"] - nonwork["node_y"][oi]
            dist = np.sqrt(dx * dx + dy * dy)
            w = nonwork["dest_w"] * np.exp(-dist / nonwork["scale"])
            d = rng.choices(nodes, weights=w.tolist())[0]
        elif demand is None:
            o, d = rng.choice(nodes), rng.choice(nodes)
        elif demand.get("mode") == "od":
            # REAL OD trip: draw a home-BG -> work-BG pair in proportion to the LODES
            # commuter flow, then place each end on a random node inside that block
            # group (the gravity guess is replaced by the measured joint distribution).
            pi = rng.choices(range(len(demand["weights"])),
                             weights=demand["weights"])[0]
            o = rng.choice(demand["bg_nodes"][demand["pairs_h"][pi]])
            d = rng.choice(demand["bg_nodes"][demand["pairs_w"][pi]])
        else:
            o = rng.choices(nodes, weights=demand["origin_w"])[0]
            if demand["scale"]:
                # destination weights conditional on this origin: jobs damped by
                # distance from the origin (gravity deterrence). exp keeps every
                # weight positive, so there is always something to draw.
                oi = demand["index"][o]
                dx = demand["node_x"] - demand["node_x"][oi]
                dy = demand["node_y"] - demand["node_y"][oi]
                dist = np.sqrt(dx * dx + dy * dy)
                w = demand["dest_w"] * np.exp(-dist / demand["scale"])
                d = rng.choices(nodes, weights=w.tolist())[0]
            else:
                d = rng.choices(nodes, weights=demand["dest_w_list"])[0]
        if o == d:
            continue
        try:
            # route by travel time, not distance: real drivers minimize time, which
            # favors faster arterials and matches where real counts concentrate.
            path = nx.shortest_path(G, o, d, weight="travel_time_s")
        except nx.NetworkXNoPath:
            continue
        if len(path) < 2:
            continue
        route = [_edge_between(G, path[i], path[i + 1]) for i in range(len(path) - 1)]
        veh = {"id": vid, "route": route, "idx": 0, "pos": 0.0, "v": 0.0}
        if fleet_ctx is not None:
            # class drawn AFTER the route succeeds, from the fleet's own RNG stream,
            # so the draw sequence lines up with spawned vehicles (route retries do
            # not consume fleet draws) and the trip RNG stream is untouched.
            cls = fleet.sample_class(fleet_ctx["mix"], fleet_ctx["rng"])
            veh["eclass"] = cls                        # class name, kept for analysis
            veh["coeffs"] = fleet_ctx["coeffs"][cls]   # this vehicle's (f0..f5) row
        if driver_ctx is not None:
            # per-vehicle IDM params drawn AFTER the route succeeds, from the
            # driver's own RNG stream, so route retries do not consume driver draws
            # and the trip stream stays untouched (same discipline as the fleet
            # class draw above). Carried for the whole trip; a respawn draws afresh.
            veh["idm"] = drivers.sample(driver_ctx["rng"], driver_ctx["sig"])
        return veh
    return None


def step_vehicles(vehicles, dt, t, segment_totals, segment_nox, segment_throughput,
                  nox_coeffs, G, nodes, rng, signals, demand=None, through=None,
                  fleet_ctx=None, driver_ctx=None, lanes=None, mobil_ctx=None,
                  speed_stats=None, stuck_stats=None):
    """Advance every vehicle by one time step.

    Order matters: we read all positions first, compute each car's acceleration
    from that frozen snapshot, and only then move everyone. That simultaneous
    update is what keeps the car-following honest (no car reacts to a neighbour
    that has already moved this step).

    Three things slow a car: the car ahead on its own segment, a red light at the
    segment's far end, and a queue spilling back from the next segment on its
    route. A red light acts as a stationary 'virtual leader' at the stop line, so
    the IDM brakes for it smoothly; the car physically waits at the line until the
    light turns green. Queues then build behind the line by ordinary car-following,
    and congestion emerges.

    Cross-edge spillback: when a car has no leader on its own segment, it looks
    across the downstream intersection to the next segment on its route. If cars
    are backed up there, the rearmost one acts as a leader sitting past the end of
    this segment, so the IDM brakes for it. A car is also held at the stop line
    rather than crossing into a segment with no room at its entrance. Together these
    let a jam longer than one block back up through the upstream intersection
    instead of vanishing at the segment boundary.

    Virtual lanes (`lanes`, the multi-lane capacity experiment): with N lanes on a
    segment, a car follows the car N positions ahead in the segment's queue; the
    N-1 cars in between are conceptually beside it in other lanes. The front N
    cars all brake for the stop line independently, so N cars queue abreast and
    signal discharge scales with N. The spillback rules generalize the same way:
    the entrance of an N'-lane segment only blocks when its N'th-rearmost car is
    at the entrance (fewer than N' cars there means a free lane), and the leader
    seen across the intersection is that N'th-rearmost car (the rearmost car of
    the emptiest lane). With lanes=None or every count 1, all three rules reduce
    exactly to the single-lane behavior above. Lane identity is implicit (queue
    rank mod N) and reshuffles freely between steps, i.e. lane changes are free
    and perfect, so this measures the capacity ceiling's effect as an UPPER BOUND.

    Driver heterogeneity (`driver_ctx`, config.DRIVER_HETEROGENEITY): when a
    vehicle carries its own IDM parameter set (veh["idm"], drawn at spawn in
    make_vehicle), its desired speed is that segment's limit scaled by the car's
    v0_factor, and its a_max/b_comf/T/s0 are the car's own values, so drivers on
    the same segment accelerate, follow, and top out differently. A vehicle with
    no "idm" key (the flag off, or every sigma 0) uses the config defaults and the
    accel call is byte-for-byte the base model.

    Explicit lanes (`mobil_ctx`, config.MOBIL_ENABLED): each car carries a real
    lane index veh["lane"] on its current segment (0 = rightmost), kept when it
    crosses into the next segment and clamped if that road is narrower. Its leader
    is the nearest car ahead IN ITS OWN LANE, so a fast car behind a slow one is
    genuinely blocked until it changes lanes -- and a lane-change pass runs first,
    from the same frozen snapshot, deciding changes with MOBIL. Overtaking is
    therefore emergent, not coded. Mutually exclusive with `lanes` above: virtual
    lanes are the frictionless upper bound, MOBIL pays the real cost of a gap.
    """
    if lanes is not None and mobil_ctx is not None:
        raise ValueError("virtual lanes (lanes=) and explicit MOBIL lanes "
                         "(mobil_ctx=) are mutually exclusive lane models")
    explicit = mobil_ctx is not None
    lane_counts = mobil_ctx["lanes"] if explicit else lanes

    # group cars by the segment they are on, and sort each group front-to-back
    by_edge = defaultdict(list)
    for veh in vehicles:
        by_edge[veh["route"][veh["idx"]][:3]].append(veh)
    for group in by_edge.values():
        group.sort(key=lambda x: x["pos"])

    L = config.VEHICLE_LENGTH_M

    # 0) MOBIL only: decide lane changes from the frozen snapshot, then apply them
    # all at once, so the accel pass below sees each car in the lane it chose.
    if explicit:
        for veh, new_lane in _mobil_lane_pass(by_edge, mobil_ctx, L):
            veh["lane"] = new_lane

    # 1) compute accelerations from the frozen snapshot
    accel = {}
    for key, group in by_edge.items():
        # lanes on this segment. Virtual lanes (Phase 1) make identity implicit --
        # queue rank mod N -- so a car's leader is the car N positions ahead;
        # explicit lanes (Phase 3) put each car in its own queue. Either way the
        # per-lane queues below turn the leader into "the next car in my queue",
        # and with N = 1 both are the single-file base model.
        n_here = lane_counts.get(key, 1) if lane_counts else 1
        for queue in _lane_queues(group, n_here, explicit):
            for i, veh in enumerate(queue):
                edge = veh["route"][veh["idx"]]
                # per-vehicle IDM params if this car is heterogeneous, else the base
                # model's single config set. idm is None => the config defaults and the
                # accel call below is byte-for-byte the base kernel.
                idm = veh.get("idm")
                v0 = edge[4] * idm["v0_factor"] if idm else edge[4]
                if i + 1 < len(queue):             # there is a car ahead in this lane
                    lead = queue[i + 1]
                    gap = lead["pos"] - L - veh["pos"]
                    lead_v = lead["v"]
                else:                              # no car ahead in this lane
                    # look across the downstream intersection to the next segment on
                    # this car's route. If cars are backed up there, the rearmost one
                    # in the lane this car will enter is our leader, sitting
                    # (edge_remaining + its pos) ahead of us; a free lane there means
                    # nothing blocks. This is cross-edge spillback: a jam now backs up
                    # through the intersection instead of disappearing at the segment
                    # boundary.
                    gap = 1e6
                    lead_v = veh["v"]
                    if veh["idx"] + 1 < len(veh["route"]):
                        next_key = veh["route"][veh["idx"] + 1][:3]
                        next_group = by_edge.get(next_key)
                        n_next = lane_counts.get(next_key, 1) if lane_counts else 1
                        if next_group is None:
                            rear = None
                        elif config.MERGE_ENTRY_IMPROVED:
                            # brake for the rear car of the lane the crossing
                            # will actually target (the one with the most room)
                            _, rear = _entry_choice(next_group, n_next,
                                                    veh.get("lane", 0), explicit)
                        else:
                            rear = _next_segment_rear(next_group, n_next,
                                                      veh.get("lane", 0), explicit)
                        if rear is not None:
                            gap = (edge[3] - veh["pos"]) + rear["pos"] - L
                            lead_v = rear["v"]

                # a red light at the downstream node is a stopped leader at the line
                node_v = edge[1]
                if node_v in signals["nodes"] and not is_green(
                        signals, node_v, signals["edge_phase"][edge[:3]], t):
                    stop_gap = edge[3] - veh["pos"]
                    if stop_gap < gap:             # the light binds before any car
                        gap, lead_v = stop_gap, 0.0

                if idm is None:
                    accel[veh["id"]] = idm_acceleration(veh["v"], gap, lead_v, v0)
                else:
                    accel[veh["id"]] = idm_acceleration(
                        veh["v"], gap, lead_v, v0, a_max=idm["a_max"],
                        b_comf=idm["b_comf"], T=idm["T"], s0=idm["s0"])

    # 2) move everyone, credit the segment they travelled on, advance routes
    # stuck threshold in m/s, converted once per step, not once per vehicle
    stuck_v = config.STUCK_SPEED_KMH / 3.6 if stuck_stats is not None else 0.0
    # improved entry only: (segment key, lane) -> rearmost car that crossed into
    # that lane THIS step, so later crossings in the same step see it (claims in
    # _entry_choice) instead of reading the frozen snapshot and overlapping it
    entered_rear = {}
    for veh in vehicles:
        v_old = veh["v"]
        a = accel[veh["id"]]
        v_new = max(0.0, v_old + a * dt)
        v_avg = 0.5 * (v_old + v_new)
        veh["pos"] += v_avg * dt                       # trapezoidal step
        veh["v"] = v_new

        edge_key = veh["route"][veh["idx"]][:3]
        # credit this segment with one vehicle-second of activity (a raw exposure
        # measure, kept alongside the emission total)
        segment_totals[edge_key] += dt
        # opt-in speed moments (realism readout): time-weighted sums so that at
        # analysis time v_sum/value is the segment's mean speed over the run and
        # v2_sum/value - mean^2 its variance. CNOSSOS noise is nonlinear in
        # speed, so the VARIANCE (not just the mean) moves the noise surface --
        # the Phase 2 heterogeneity payoff. Pure measurement: nothing here feeds
        # back into the dynamics, so passing speed_stats cannot change any
        # trajectory (the kernel-regression gate still proves it bit-identical).
        if speed_stats is not None:
            speed_stats["v_sum"][edge_key] += v_avg * dt
            speed_stats["v2_sum"][edge_key] += v_avg * v_avg * dt
        # opt-in stuck time (calibrated-demand Phase 3): a vehicle-second below
        # config.STUCK_SPEED_KMH counts as stuck, so "vehicle-hours stuck" is
        # MEASURED per car per step, not inferred from the segment's mean speed
        # at analysis time. Same pure-measurement contract as speed_stats above:
        # nothing feeds back into the dynamics.
        if stuck_stats is not None and v_avg < stuck_v:
            stuck_stats["stuck_sum"][edge_key] += dt
        # and with this vehicle's NOx for the step: the HBEFA3 rate at the step's
        # average speed and its realized acceleration, integrated over dt. NOx is
        # turned into NO2 downstream (NO2 = F_NO2 * NOx), so the fraction stays a
        # tunable knob that does not require rerunning the sim.
        a_real = (v_new - v_old) / dt
        # mixed fleet: a vehicle carries its own class coefficients from spawn;
        # otherwise every vehicle emits as the single configured class.
        segment_nox[edge_key] += emissions.nox_g_per_s(
            v_avg, a_real, veh.get("coeffs", nox_coeffs)) * dt

        # cross into the next segment(s) if we ran past the end of this one
        while veh["pos"] > veh["route"][veh["idx"]][3]:
            edge = veh["route"][veh["idx"]]
            node_v = edge[1]
            # do not cross a red light: wait exactly at the stop line
            if node_v in signals["nodes"] and not is_green(
                    signals, node_v, signals["edge_phase"][edge[:3]], t):
                veh["pos"], veh["v"] = edge[3], 0.0
                break
            # do not cross into a full downstream segment: if every lane's rearmost
            # car sits within a minimum gap of the entrance, hold at the stop line
            # (with n_next lanes, that is the n_next'th-rearmost car; fewer cars
            # than lanes means a free lane, so entry is never blocked). This is
            # the spillback counterpart to the red-light hold above.
            entry_lane = None      # improved-entry target lane, decided below
            if veh["idx"] + 1 < len(veh["route"]):
                next_key = veh["route"][veh["idx"] + 1][:3]
                next_group = by_edge.get(next_key)
                n_next = lane_counts.get(next_key, 1) if lane_counts else 1
                if config.MERGE_ENTRY_IMPROVED:
                    # improved rule: cross as soon as there is physical room for
                    # the car BODY past the entrance in the roomiest lane. The
                    # car keeps whatever approach speed the IDM left it (it was
                    # already braking for this same rear car via the spillback
                    # leader above), so a queue drains across the junction as a
                    # wave instead of stop-restart cycles at full jam spacing.
                    claims = ({ln: c for (k2, ln), c in entered_rear.items()
                               if k2 == next_key}
                              if entered_rear else None)
                    if next_group or claims:
                        entry_lane, rear = _entry_choice(
                            next_group or [], n_next, veh.get("lane", 0),
                            explicit, claims)
                        overhang = veh["pos"] - edge[3]
                        if (rear is not None and rear["pos"] - overhang
                                < L + config.MERGE_ENTRY_EPS_M):
                            # no room even for the body: bumper-to-bumper stop
                            veh["pos"], veh["v"] = edge[3], 0.0
                            break
                else:
                    # legacy rule: hold at the line, speed zeroed, until the
                    # rearmost car has cleared a full jam distance. The minimum
                    # gap is this driver's OWN jam distance when the car is
                    # heterogeneous (config.IDM_S0 otherwise), matching the s0
                    # the accel pass above used for the same car. A driver who
                    # keeps a shorter jam distance should also squeeze into a
                    # tighter entrance.
                    veh_idm = veh.get("idm")
                    s0_here = veh_idm["s0"] if veh_idm else config.IDM_S0
                    rear = (_next_segment_rear(next_group, n_next,
                                               veh.get("lane", 0), explicit)
                            if next_group else None)
                    if rear is not None and rear["pos"] < L + s0_here:
                        veh["pos"], veh["v"] = edge[3], 0.0
                        break
            # the car has fully traversed this segment: count one vehicle through it.
            # This is the model analog of a real traffic count (vehicles per period),
            # the apples-to-apples match for ADT, distinct from vehicle-seconds.
            segment_throughput[edge[:3]] += 1
            veh["pos"] -= edge[3]
            if veh["idx"] + 1 < len(veh["route"]):
                veh["idx"] += 1
                if explicit:
                    # legacy: keep the lane index across the intersection,
                    # dropping to the highest lane that exists if the new road
                    # is narrower (a car leaving a 3-lane arterial for a 1-lane
                    # street ends up in lane 0). Improved: take the lane the
                    # room check above targeted, so a feeder can use ALL of a
                    # wider downstream road's lanes at the junction itself.
                    n_new = lane_counts.get(veh["route"][veh["idx"]][:3], 1)
                    if entry_lane is not None:
                        veh["lane"] = entry_lane
                    else:
                        veh["lane"] = min(veh.get("lane", 0), n_new - 1)
                if config.MERGE_ENTRY_IMPROVED:
                    # register this crossing so later same-step entries into the
                    # same lane serialize behind it (the claims read above)
                    nk = veh["route"][veh["idx"]][:3]
                    ln = veh.get("lane", 0) if explicit else 0
                    prev = entered_rear.get((nk, ln))
                    if prev is None or veh["pos"] < prev["pos"]:
                        entered_rear[(nk, ln)] = veh
            else:
                # reached the destination: respawn with a fresh trip so the
                # number of vehicles on the network stays steady
                fresh = make_vehicle(G, nodes, rng, veh["id"], demand, through,
                                     fleet_ctx, driver_ctx)
                if fresh is not None:
                    veh.update(fresh)
                    if explicit:
                        # fresh carries no lane key, so without this the car would
                        # keep a stale index from the route it just finished
                        veh["lane"] = 0
                else:
                    veh["pos"], veh["v"] = edge[3], 0.0
                break


def _measure_approach_flows(G, n_vehicles, warmup_steps, verbose=True):
    """Estimate each signalized approach's volume (veh/h) for Webster timing.

    A short SEEDED warmup with the uniform BASE signals, on its OWN RNG stream
    (config.RANDOM_SEED + 11) and its own vehicle population and context objects,
    so it consumes nothing the authoritative run draws: with WEBSTER_ENABLED the
    authoritative simulation that follows is the byte-for-byte same population it
    would have with the flag off, and only the signal timing differs. An edge's
    flow = the vehicles that fully crossed it (the existing segment_throughput
    measure -- one count per traversal into the downstream node) over the LAST HALF
    of the warmup, after the network has filled from empty, converted to veh/h.
    Returns {edge_key: veh_per_hour} (edges that never carried a car are absent,
    and build_webster_plans then reads them as zero flow)."""
    nodes = list(G.nodes)
    wrng = random.Random(config.RANDOM_SEED + 11)   # isolated from the authoritative run
    signals = prepare_signals(G)                    # uniform base signals (never Webster)
    lanes = {(u, v, k): d.get("n_lanes", 1)
             for u, v, k, d in G.edges(keys=True, data=True)}
    mobil_ctx = build_mobil_context(G)              # mirror run_simulation's lane setup
    if mobil_ctx is not None:
        lanes = None
    nox_coeffs = emissions.active_coeffs()
    fleet_ctx = build_fleet_context()
    driver_ctx = build_driver_context()
    demand = build_demand_weights(G, nodes)
    through = build_through_context(G, nodes)

    vehicles = []
    for vid in range(n_vehicles):
        veh = make_vehicle(G, nodes, wrng, vid, demand, through, fleet_ctx, driver_ctx)
        if veh is not None:
            vehicles.append(veh)

    seg_tot, seg_nox = defaultdict(float), defaultdict(float)
    thru = defaultdict(float)          # cumulative crossings over the warmup
    half = warmup_steps // 2
    thru_at_half = {}                  # snapshot at the half mark (start of the window)
    for step in range(warmup_steps):
        if step == half:
            thru_at_half = dict(thru)
        step_vehicles(vehicles, config.DT, step * config.DT, seg_tot, seg_nox, thru,
                      nox_coeffs, G, nodes, wrng, signals, demand, through,
                      fleet_ctx=fleet_ctx, driver_ctx=driver_ctx, lanes=lanes,
                      mobil_ctx=mobil_ctx)

    window_s = max(warmup_steps - half, 1) * config.DT
    flows = {}
    for edge, total in thru.items():
        crossed = total - thru_at_half.get(edge, 0.0)
        if crossed > 0.0:
            flows[edge] = crossed / (window_s / 3600.0)
    if verbose:
        peak = max(flows.values(), default=0.0)
        print(f"Webster warmup: {len(vehicles)} vehicles x {warmup_steps} steps "
              f"-> {len(flows)} approaches with flow over the last {window_s:.0f}s "
              f"(peak {peak:,.0f} veh/h)")
    return flows


def run_simulation(G, n_vehicles=None, n_steps=None, use_checkpoint=True, verbose=True,
                   speed_stats=None, stuck_stats=None):
    """Drive n_vehicles for n_steps. Return (segment_totals, segment_nox):
    per-segment vehicle-seconds of activity, and per-segment NOx grams.

    speed_stats (opt-in, realism readout): pass an empty dict and it is filled
    in place with per-segment time-weighted speed sums, keys "v_sum" and
    "v2_sum" (see step_vehicles). Existing callers pass nothing and see the
    exact prior behavior and the same 3-tuple return.

    stuck_stats (opt-in, calibrated-demand Phase 3): pass an empty dict and it
    is filled in place with per-segment stuck vehicle-seconds under key
    "stuck_sum" -- time spent below config.STUCK_SPEED_KMH (see step_vehicles).
    Same contract as speed_stats: pure measurement, off by default."""
    n_vehicles = config.N_VEHICLES if n_vehicles is None else n_vehicles
    n_steps = config.N_STEPS if n_steps is None else n_steps

    prepare_network(G)
    # Webster signal timing (Phase 4, increment 2): a measurement pre-pass first,
    # so each intersection can be timed to the volume it actually carries. Off by
    # default -- prepare_signals(G) with no flows is the uniform base signal, and
    # the warmup uses its own RNG stream so the authoritative run below is the same
    # population it would be with the flag off (only the timing changes).
    webster_flows = None
    if config.WEBSTER_ENABLED:
        webster_flows = _measure_approach_flows(
            G, config.N_VEHICLES if n_vehicles is None else n_vehicles,
            config.WEBSTER_WARMUP_STEPS, verbose=verbose)
    signals = prepare_signals(G, flows=webster_flows)
    # per-segment virtual-lane counts (all 1 unless config.LANES_ENABLED); dict
    # keyed like by_edge so step_vehicles can look lanes up per segment
    lanes = {(u, v, k): d.get("n_lanes", 1)
             for u, v, k, d in G.edges(keys=True, data=True)}
    mobil_ctx = build_mobil_context(G)         # explicit per-car lanes (or None)
    if mobil_ctx is not None:
        lanes = None       # mutually exclusive: MOBIL owns the lane counts instead
    if verbose:
        src = "OSM-tagged" if signals["tagged"] else "degree>=4 fallback"
        print(f"{len(signals['nodes'])} signalized intersections ({src})")
        if signals["node_cycle"] is not None:
            cyc = signals["node_cycle"].values()
            print(f"Webster timing ON: per-node cycle {min(cyc):.0f}-{max(cyc):.0f}s "
                  f"(clearance {signals['clearance']:.1f}s/phase)")
        if config.LANES_ENABLED:
            multi = sum(1 for n in lanes.values() if n > 1)
            print(f"lanes experiment ON: {multi} of {len(lanes)} segments get >1 "
                  f"virtual lane (max {max(lanes.values())})")
    nodes = list(G.nodes)
    rng = random.Random(config.RANDOM_SEED)   # own stream, so routes are reproducible
    nox_coeffs = emissions.active_coeffs()    # HBEFA3 row for the configured class, fetched once
    fleet_ctx = build_fleet_context()         # mixed-fleet per-vehicle classes (or None)
    driver_ctx = build_driver_context()       # per-vehicle IDM heterogeneity (or None)
    demand = build_demand_weights(G, nodes)   # population/jobs gravity trip weights
    through = build_through_context(G, nodes)  # regional through-traffic (cordon) trips

    state = load_checkpoint(config.RAW_DIR, config.RUN_NAME) if use_checkpoint else None
    if state is None:
        segment_totals = {edge: 0.0 for edge in G.edges(keys=True)}
        segment_nox = {edge: 0.0 for edge in G.edges(keys=True)}
        segment_throughput = {edge: 0.0 for edge in G.edges(keys=True)}
        vehicles = []
        for vid in range(n_vehicles):
            veh = make_vehicle(G, nodes, rng, vid, demand, through, fleet_ctx,
                               driver_ctx)
            if veh is not None:
                vehicles.append(veh)
        state = {"step": 0, "segment_totals": segment_totals,
                 "segment_nox": segment_nox,
                 "segment_throughput": segment_throughput, "vehicles": vehicles}
        if speed_stats is not None:
            # the caller's dict gets the per-edge accumulators; stored in state
            # so a checkpoint resume keeps the partial sums
            speed_stats["v_sum"] = {edge: 0.0 for edge in G.edges(keys=True)}
            speed_stats["v2_sum"] = {edge: 0.0 for edge in G.edges(keys=True)}
            state["speed_stats"] = speed_stats
        if stuck_stats is not None:
            # same discipline as speed_stats: caller's dict, checkpointed in state
            stuck_stats["stuck_sum"] = {edge: 0.0 for edge in G.edges(keys=True)}
            state["stuck_stats"] = stuck_stats
    else:
        print(f"Resuming from step {state['step']}")
        segment_totals = state["segment_totals"]
        # older checkpoints predate these accumulators; start them fresh if absent
        segment_nox = state.get("segment_nox") or {edge: 0.0 for edge in G.edges(keys=True)}
        state["segment_nox"] = segment_nox
        segment_throughput = (state.get("segment_throughput")
                              or {edge: 0.0 for edge in G.edges(keys=True)})
        state["segment_throughput"] = segment_throughput
        vehicles = state["vehicles"]
        if speed_stats is not None:
            saved = state.get("speed_stats")
            if saved:
                # resume: adopt the checkpointed partial sums into the caller's dict
                speed_stats.update(saved)
            else:
                # the checkpoint predates the request for speed stats: the sums
                # would cover only the remaining steps, i.e. be WRONG for the whole
                # run. Refuse rather than silently produce a partial readout.
                raise SystemExit(
                    "checkpoint for this run has no speed_stats; delete the "
                    "checkpoint (or run without speed_stats) to proceed")
            state["speed_stats"] = speed_stats
        if stuck_stats is not None:
            saved = state.get("stuck_stats")
            if saved:
                # resume: adopt the checkpointed partial sums into the caller's dict
                stuck_stats.update(saved)
            else:
                # checkpoint predates the request: the sum would cover only the
                # remaining steps, i.e. be WRONG for the whole run. Refuse rather
                # than silently produce a partial readout (speed_stats discipline).
                raise SystemExit(
                    "checkpoint for this run has no stuck_stats; delete the "
                    "checkpoint (or run without stuck_stats) to proceed")
            state["stuck_stats"] = stuck_stats

    t0 = time.perf_counter()
    for step in range(state["step"], n_steps):
        # the optional context/lane arguments go by KEYWORD at every call site:
        # they are appended over time (fleet_ctx, then driver_ctx, then lanes), so
        # positional passing would silently mis-bind the next time one is inserted.
        step_vehicles(vehicles, config.DT, step * config.DT, segment_totals,
                      segment_nox, segment_throughput, nox_coeffs, G, nodes, rng,
                      signals, demand, through, fleet_ctx=fleet_ctx,
                      driver_ctx=driver_ctx, lanes=lanes, mobil_ctx=mobil_ctx,
                      speed_stats=speed_stats, stuck_stats=stuck_stats)
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
    return segment_totals, segment_nox, segment_throughput


def benchmark(G):
    """Early computational-complexity read (mentor request, Jun 22): hold the network
    fixed and watch wall time grow with vehicle count. Small steps so it is fast."""
    print(f"Runtime read on the Powell network ({G.number_of_nodes()} nodes, "
          f"{G.number_of_edges()} edges):")
    for n_vehicles in (50, 100, 250, 500, 1000):
        run_simulation(G, n_vehicles=n_vehicles, n_steps=200,
                       use_checkpoint=False, verbose=True)


def save_results(segment_totals, segment_nox, segment_throughput, speed_stats=None,
                 stuck_stats=None):
    """Write final per-segment results as one tidy table.
    parquet keeps data types and stays compact. Switch to .to_csv if you ever
    want a file you can open and read by eye.

    Columns: value = vehicle-seconds of activity (raw exposure); nox_g = NOx grams
    from HBEFA3; throughput = number of vehicles that fully traversed the segment
    (the model analog of a real traffic count, for validation against PBOT ADT).
    The NO2 surface is NO2 = config.F_NO2 * nox_g, applied at analysis time so the
    fraction can be retuned without rerunning the simulation.

    speed_stats (opt-in, from run_simulation): adds v_sum and v2_sum columns, the
    time-weighted speed sums whose analysis-time quotients give each segment's
    mean speed (v_sum/value) and speed variance (v2_sum/value - mean^2).

    stuck_stats (opt-in, from run_simulation): adds a stuck_sum column, the
    vehicle-seconds the segment carried below config.STUCK_SPEED_KMH; divide by
    3600 for the stuck vehicle-hours of the calibrated-demand Phase 3 readout."""
    keys = list(segment_totals.keys())
    rows = [{"u": u, "v": v, "key": k, "value": segment_totals[(u, v, k)],
             "nox_g": segment_nox[(u, v, k)],
             "throughput": segment_throughput[(u, v, k)]}
            for (u, v, k) in keys]
    df = pd.DataFrame(rows)
    if speed_stats is not None:
        # aligned to `keys`, the same iteration order the rows were built from
        df["v_sum"] = [speed_stats["v_sum"][e] for e in keys]
        df["v2_sum"] = [speed_stats["v2_sum"][e] for e in keys]
    if stuck_stats is not None:
        df["stuck_sum"] = [stuck_stats["stuck_sum"][e] for e in keys]
    out = os.path.join(config.PROCESSED_DIR, f"{config.RUN_NAME}_segments.parquet")
    df.to_parquet(out)
    print(f"Saved {len(df)} segment results to {out} "
          f"(total NOx {df['nox_g'].sum():.1f} g)")


def run_closure_experiment(G):
    """Before/after closure experiment (mentor request, Jun 23).

    Runs the SAME demand on the network twice: once open, once with config.CLOSURE
    applied, and saves both result files (RUN_NAME + '_open' and '_closed'). The
    same random seed drives both, so the origin/destination draws match and any
    difference in the surfaces comes from the closure forcing reroutes, not noise.
    visualize.py then differences the two to show where NO2 moved.

    Checkpointing is off here: each run is short (~10 s) and the two phases would
    otherwise share a checkpoint name. We restore config.RUN_NAME at the end.
    """
    if config.CLOSURE is None:
        raise SystemExit("Set config.CLOSURE to a (lat, lon, radius_m) zone first.")
    base = config.RUN_NAME
    try:
        # open network: the baseline
        config.RUN_NAME = f"{base}_open"
        print(f"[open] {base} on the full network")
        totals, nox, thru = run_simulation(G, use_checkpoint=False)
        save_results(totals, nox, thru)
        open_no2 = config.F_NO2 * sum(nox.values())

        # closed network: same demand, segments in the zone removed
        Gc = G.copy()
        removed = apply_closure(Gc)
        lat, lon, r = config.CLOSURE
        print(f"[closed] removed {len(removed)} segments within {r:.0f} m "
              f"of ({lat}, {lon})")
        config.RUN_NAME = f"{base}_closed"
        totals, nox, thru = run_simulation(Gc, use_checkpoint=False)
        save_results(totals, nox, thru)
        closed_no2 = config.F_NO2 * sum(nox.values())
    finally:
        config.RUN_NAME = base

    delta = closed_no2 - open_no2
    pct = 100 * delta / open_no2 if open_no2 else 0.0
    print(f"\nClosure effect on total NO2: open {open_no2:.1f} g -> "
          f"closed {closed_no2:.1f} g  ({pct:+.1f}%)")
    print("Total can move only a little; the point is the spatial shift. "
          "Draw it with: python src/visualize.py closure")


def run_day_experiment(G):
    """24-hour time-of-day experiment: the temporal dimension a static surface
    cannot produce (the mentor's brainstorm direction, Jun 26).

    Rao et al. produce a single long-term-average NO2 surface. The ABM runs second
    by second, so it can produce one surface PER HOUR of the day. We drive that with
    a real time-of-day demand shape: the number of vehicles on the network each hour
    is scaled by the PORTAL hourly profile (src/demand_data.py), so traffic is light
    overnight, climbs to a morning peak, holds through midday, and peaks again in the
    afternoon.

    Two results emerge together. The obvious one: NO2 rises and falls with the clock.
    The interesting one: because a queued car emits far more NOx than a cruising one
    (the HBEFA3 idle term), peak-hour NO2 rises MORE than the volume alone would
    predict. That congestion nonlinearity is exactly the interaction effect the ABM
    exists to show, and it is what a flow-times-a-factor static estimate misses.

    Method (deliberately simple, reusing the validated kernel): each hour is an
    independent steady-state run whose vehicle count is N_VEHICLES * profile[h] * 24.
    The * 24 keeps config.N_VEHICLES meaning the DAILY-AVERAGE population, so peak
    hours sit above it and night hours below (the 24 hourly fractions average 1/24,
    so the mean hourly count is exactly N_VEHICLES). Spatial demand (the population/
    jobs gravity model) rides along automatically through run_simulation.

    Known simplification, stated honestly: each hour starts from an empty network and
    fills over the first few minutes, so there is a short warmup per hour. At one
    simulated hour per run that warmup is a small fraction, like the uniform signal
    timing. All 24 results go to one file with an 'hour' column so visualize.py can
    draw the daily profile and the hourly maps without rerunning anything.
    """
    profile = demand_data.hourly_demand_profile()
    src = "real PORTAL data" if demand_data.is_using_real_data() else "SYNTHETIC fallback"
    print(f"Time-of-day demand shape: {src}. "
          f"Daily-average population {config.N_VEHICLES} vehicles.\n")

    frames = []
    for h in range(24):
        n_h = max(1, round(config.N_VEHICLES * profile[h] * 24))
        totals, nox, thru = run_simulation(
            G, n_vehicles=n_h, use_checkpoint=False, verbose=False)
        no2_total = config.F_NO2 * sum(nox.values())
        print(f"[hour {h:02d}:00]  {n_h:>4} vehicles   network NO2 {no2_total:8.1f} g")
        for (u, v, k), val in totals.items():
            frames.append({"u": u, "v": v, "key": k, "value": val,
                           "nox_g": nox[(u, v, k)], "throughput": thru[(u, v, k)],
                           "n_vehicles": n_h, "hour": h})

    df = pd.DataFrame(frames)
    out = os.path.join(config.PROCESSED_DIR, f"{config.RUN_NAME}_day_segments.parquet")
    df.to_parquet(out)
    by_hour = df.groupby("hour")["nox_g"].sum() * config.F_NO2
    peak = int(by_hour.idxmax())
    print(f"\nSaved {len(df)} rows (24 hours) to {out}.")
    print(f"Peak NO2 hour = {peak:02d}:00 ({by_hour[peak]:.1f} g), "
          f"quietest = {int(by_hour.idxmin()):02d}:00 ({by_hour.min():.1f} g). "
          f"Draw it with: python src/visualize.py day")


if __name__ == "__main__":
    set_seeds(config.RANDOM_SEED)
    G = get_network()
    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode == "benchmark":
        benchmark(G)
    elif mode == "closure":
        run_closure_experiment(G)
    elif mode == "day":
        run_day_experiment(G)
    else:
        totals, nox, thru = run_simulation(G)
        save_results(totals, nox, thru)
