"""Arterial travel-time predictions for the Rose Quarter closure (pre-registered).

Read-only instrument, no simulation (single-source-of-truth rule): recovers
realized per-edge travel times from a finished campaign's saved per-segment
results and computes, for the 12 frozen OD pairs of the public travel-time
logger (github.com/darcy0408/portland-traveltime-log), the fastest-path
travel time on the open network and on the closed network, per seed. The
paired per-seed differences are the model's registered predictions for what
the TomTom logger should record when I-5 SB closes on Sept 11 2026.

Design registered in PREREG_I5_ROSEQUARTER.md (Appendix M) BEFORE this
script first ran on campaign data; results appended there, dated.

    python src/rosequarter_traveltime.py --arm base        # fwrq campaign
    python src/rosequarter_traveltime.py --arm improved    # fwrqi campaign

The router here is the model analog of the logger's router: it picks the
fastest route under CURRENT (realized, congestion-aware) edge times, exactly
what a live routing API does. This is deliberately not the sim's own spawn
router (which uses free-flow times and never replans): the instrument asks
what a navigator would experience on the network the campaign produced.
"""
import argparse
import json
import os
import sys

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import generate        # noqa: E402
from freeway_rosequarter import (SEEDS, _verify_span)  # noqa: E402

# The 12 OD pairs, copied VERBATIM from the logger repo's frozen pairs.json
# (portland-traveltime-log commit history is the public timestamp). (lat, lon).
PAIRS = [
    {"id": "i5sb_span",     "from": (45.6060, -122.6871), "to": (45.5081, -122.6608), "name": "Delta Park -> OMSI"},
    {"id": "vanc_pdx",      "from": (45.6262, -122.6751), "to": (45.5189, -122.6794), "name": "Vancouver WA -> Pioneer Courthouse Sq"},
    {"id": "i5sb_detour",   "from": (45.5768, -122.6820), "to": (45.5119, -122.6843), "name": "Rosa Parks/I-5 -> PSU"},
    {"id": "interstate_sb", "from": (45.5830, -122.6819), "to": (45.5346, -122.6740), "name": "Kenton -> Broadway Bridge east"},
    {"id": "williams_nb",   "from": (45.5346, -122.6740), "to": (45.5830, -122.6819), "name": "Broadway Bridge east -> Kenton"},
    {"id": "mlk_sb",        "from": (45.5830, -122.6620), "to": (45.5190, -122.6608), "name": "NE Columbia/MLK -> SE Stark/Grand"},
    {"id": "grand_nb",      "from": (45.5190, -122.6608), "to": (45.5830, -122.6620), "name": "SE Stark/Grand -> NE Columbia/MLK"},
    {"id": "i205_sb",       "from": (45.5749, -122.5655), "to": (45.4890, -122.5665), "name": "Airport Way -> Foster via I-205"},
    {"id": "i84wb_feeder",  "from": (45.5310, -122.5780), "to": (45.5316, -122.6668), "name": "NE 82nd/I-84 -> Moda Center"},
    {"id": "powell_wb",     "from": (45.4977, -122.5789), "to": (45.5015, -122.6685), "name": "SE 82nd/Powell -> Ross Island Bridge"},
    {"id": "ctrl_west",     "from": (45.4515, -122.7817), "to": (45.5229, -122.9898), "name": "Washington Square -> Hillsboro"},
    {"id": "ctrl_se",       "from": (45.5023, -122.4416), "to": (45.4790, -122.5670), "name": "Gresham -> Lents"},
]

# Rules pinned before the first real run (Appendix M):
# - a pair is model-gradeable only if BOTH endpoints snap within SNAP_MAX_M of
#   a graph node; otherwise the model route would start or end at a fictitious
#   boundary point. Excluded pairs are reported, and stay logger-side controls.
#   (Known at registration: ctrl_west's Hillsboro endpoint sits ~7 km outside
#   the 20 km graph and is expected to be excluded on both arms.)
SNAP_MAX_M = 500.0
# - realized edge time = value / throughput (vehicle-seconds per traversing
#   vehicle), floored at free-flow time: a segment cannot honestly be faster
#   than free flow, and the floor absorbs the known short-segment attribution
#   artifact. An edge that carried vehicles but discharged NONE inside the
#   simulated hour gets T_CAP_S, the horizon itself; a router avoids it, which
#   is what a live router does with a standing queue.
T_CAP_S = 3600.0
# - the standing campaign verdict bar: unanimous sign across the 8 paired
#   seeds AND |t| > 3 on the paired relative differences.
# - a route SWITCH is flagged when the closed-arm path length differs from the
#   open-arm path length by more than LEN_SWITCH_FRAC (the logger's length_m
#   jump signal).
LEN_SWITCH_FRAC = 0.10

ARM_SPECS = {
    "base":     {"prefix": "fwrq",  "graph": "graph.graphml",               "stack": "base"},
    "improved": {"prefix": "fwrqi", "graph": "graph_metro20k_lanes.graphml", "stack": "improved"},
}


def _load_graph(spec):
    path = os.path.join(config.NETWORK_DIR, spec["graph"])
    if not os.path.exists(path):
        raise SystemExit(f"no cached graph at {path}; run where the campaign's "
                         f"graph lives (Orca for the base arm)")
    G = ox.load_graphml(path)
    if G.number_of_edges() < 100_000:
        raise SystemExit(f"graph has {G.number_of_edges():,} edges; this is a "
                         f"metro instrument and refuses a corridor-sized graph")
    generate.prepare_network(G)   # the same free-flow times the sim used
    return G


def _edge_times(G, df):
    """Set 't_real_s' on every edge: free-flow default, realized where the run
    recorded activity. Fails loudly if a saved row's edge is not in the graph
    (that would mean the parquet and the graph disagree)."""
    for _u, _v, _k, data in G.edges(keys=True, data=True):
        data["t_real_s"] = data["travel_time_s"]
    misses = 0
    for row in df.itertuples(index=False):
        try:
            data = G.edges[row.u, row.v, row.key]
        except KeyError:
            misses += 1
            continue
        if row.throughput >= 1:
            data["t_real_s"] = max(data["travel_time_s"],
                                   row.value / row.throughput)
        elif row.value > 0:
            data["t_real_s"] = T_CAP_S
        # value == 0: untraveled, keep free-flow
    if misses:
        raise SystemExit(f"{misses} saved segments not present in the graph; "
                         f"wrong graph for this campaign's parquets")


def _route(G, o, d):
    """Fastest path under t_real_s. Returns (seconds, meters) or (nan, nan)
    when the closed network disconnects the pair (reported, never silent)."""
    try:
        path = nx.shortest_path(G, o, d, weight="t_real_s")
    except nx.NetworkXNoPath:
        return float("nan"), float("nan")
    t = s = 0.0
    for a, b in zip(path[:-1], path[1:]):
        # parallel edges: take the one the router took (min realized time)
        best = min(G[a][b].values(), key=lambda e: e["t_real_s"])
        t += best["t_real_s"]
        s += best["length"]
    return t, s


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--arm", choices=ARM_SPECS, required=True)
    ap.add_argument("--processed", default=None,
                    help="override the processed dir the parquets live in")
    args = ap.parse_args()
    spec = ARM_SPECS[args.arm]
    processed = args.processed or config.PROCESSED_DIR

    G = _load_graph(spec)
    removed = _verify_span(G)           # the frozen-span guard, every run
    Gc = G.copy()
    Gc.remove_edges_from(removed)

    # snap the frozen endpoints once per graph, apply the exclusion rule
    lons = [p[e][1] for p in PAIRS for e in ("from", "to")]
    lats = [p[e][0] for p in PAIRS for e in ("from", "to")]
    nodes, dists = ox.distance.nearest_nodes(G, X=lons, Y=lats, return_dist=True)
    usable, snaps = [], {}
    for i, p in enumerate(PAIRS):
        o, d = nodes[2 * i], nodes[2 * i + 1]
        do, dd = dists[2 * i], dists[2 * i + 1]
        snaps[p["id"]] = {"o_node": int(o), "d_node": int(d),
                          "o_snap_m": round(do, 1), "d_snap_m": round(dd, 1)}
        if max(do, dd) > SNAP_MAX_M:
            print(f"EXCLUDED {p['id']}: endpoint snaps {max(do, dd):,.0f} m "
                  f"from the graph (rule: {SNAP_MAX_M:.0f} m)")
        else:
            usable.append((p["id"], o, d))

    results = {p_id: {} for p_id, _, _ in usable}
    for seed in SEEDS:
        frames = {}
        for arm in ("open", "rosequarter"):
            stem = os.path.join(processed, f"{spec['prefix']}_{arm}_s{seed}")
            summ = json.load(open(stem + "_summary.json"))
            if summ.get("stack", "base") != spec["stack"] or summ.get("nonwork"):
                raise SystemExit(f"{stem}_summary.json is not a "
                                 f"{spec['stack']} campaign file")
            frames[arm] = pd.read_parquet(stem + "_segments.parquet")
        _edge_times(G, frames["open"])
        _edge_times(Gc, frames["rosequarter"])
        for p_id, o, d in usable:
            to, lo = _route(G, o, d)
            tc, lc = _route(Gc, o, d)
            results[p_id][seed] = {"open_s": round(to, 1), "closed_s": round(tc, 1),
                                   "open_m": round(lo), "closed_m": round(lc)}
        print(f"seed {seed} done")

    out = os.path.join(processed, f"rqtt_{spec['prefix']}.json")
    with open(out, "w") as f:
        json.dump({"arm": args.arm, "prefix": spec["prefix"],
                   "snap_max_m": SNAP_MAX_M, "t_cap_s": T_CAP_S,
                   "snaps": snaps, "results": results}, f, indent=1)
    print(f"saved -> {out}\n")

    print(f"{'=' * 78}\nARTERIAL TRAVEL TIMES ({args.arm} arm): paired per-seed, "
          f"closed - open\n{'=' * 78}")
    print(f"{'pair':>14s} {'open min':>9s} {'closed':>7s} {'mean %':>8s} "
          f"{'sd %':>6s} {'signs':>6s} {'switch':>6s}  verdict")
    for p_id, _, _ in usable:
        r = results[p_id]
        to = np.array([r[s]["open_s"] for s in SEEDS])
        tc = np.array([r[s]["closed_s"] for s in SEEDS])
        rel = 100.0 * (tc - to) / to
        pos = int((tc - to > 0).sum())
        unanimous = pos in (0, len(SEEDS))
        t = (abs(rel.mean()) / (rel.std(ddof=1) / np.sqrt(len(rel)))
             if rel.std(ddof=1) > 0 else float("inf"))
        switches = sum(abs(r[s]["closed_m"] - r[s]["open_m"])
                       > LEN_SWITCH_FRAC * r[s]["open_m"] for s in SEEDS)
        verdict = ("SUPPORTED" if unanimous and t > 3
                   else "weak" if unanimous else "not supported")
        print(f"{p_id:>14s} {to.mean() / 60:9.1f} {tc.mean() / 60:7.1f} "
              f"{rel.mean():+8.2f} {rel.std(ddof=1):6.2f} {pos:3d}/{len(SEEDS):<2d} "
              f"{switches:4d}/{len(SEEDS):<2d}  {verdict} (t={t:.1f})")


if __name__ == "__main__":
    main()
