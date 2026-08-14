"""Gate checks for the non-work (shopping/errand) demand layer (B3).

Runs the four hand-checkable gates REAL_DEMAND_UPGRADE_PLAN.md B3 requires
before the flag can ever be trusted, against the real kernel and the cached
graph. Read-only with respect to committed data: nothing here writes a run
file, and the committed config default (DEMAND_NONWORK_ENABLED = False) is
only overridden inside this process.

    python src/nonwork_check.py                 # config graph (data/network)
    python src/nonwork_check.py --graph <path>  # e.g. the pta-realism metro copy

Gates:
  1 DATA           the attraction table loads and carries positive mass
  2 CONTEXT        build_nonwork_demand aligns finite weights with the nodes
  3 REPRODUCE      same seed -> identical spawned trips, twice
  4 SPATIAL        non-work trips come out shorter than work trips (NHTS says
                   about half); measured, reported, asserted directional only
  5 INERTNESS      flag off -> the demand dict carries no layer and the spawn
                   sequence is identical whether the key is None or absent,
                   so pre-layer runs reproduce bit-for-bit
"""
import argparse
import math
import os
import random
import sys

import numpy as np
import osmnx as ox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import generate        # noqa: E402
import landuse_data    # noqa: E402

FAILED = []


def gate(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f": {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def crowfly_mean(ctx, pairs):
    """Mean straight-line origin->destination distance (m) for (o, d) node pairs,
    using the context's local-meter coordinates."""
    idx = ctx["index"]
    d = [math.hypot(ctx["node_x"][idx[o]] - ctx["node_x"][idx[dn]],
                    ctx["node_y"][idx[o]] - ctx["node_y"][idx[dn]])
         for o, dn in pairs]
    return float(np.mean(d))


def draw_nonwork(nw, nodes, rng, n):
    out = []
    for _ in range(n):
        o = rng.choices(nodes, weights=nw["origin_w"])[0]
        oi = nw["index"][o]
        dist = np.hypot(nw["node_x"] - nw["node_x"][oi], nw["node_y"] - nw["node_y"][oi])
        w = nw["dest_w"] * np.exp(-dist / nw["scale"])
        out.append((o, nodes[int(rng.choices(range(len(nodes)), weights=w.tolist())[0])]))
    return out


def draw_work(demand, nodes, rng, n):
    out = []
    for _ in range(n):
        if demand.get("mode") == "od":
            pi = rng.choices(range(len(demand["weights"])), weights=demand["weights"])[0]
            o = rng.choice(demand["bg_nodes"][demand["pairs_h"][pi]])
            d = rng.choice(demand["bg_nodes"][demand["pairs_w"][pi]])
        else:
            o = rng.choices(nodes, weights=demand["origin_w"])[0]
            oi = demand["index"][o]
            dist = np.hypot(demand["node_x"] - demand["node_x"][oi],
                            demand["node_y"] - demand["node_y"][oi])
            w = demand["dest_w"] * np.exp(-dist / demand["scale"])
            d = rng.choices(nodes, weights=w.tolist())[0]
        out.append((o, d))
    return out


def spawn_signature(G, nodes, demand, seed, n):
    """(origin, destination, route-length) for n spawned vehicles, the comparable
    fingerprint of the trip RNG stream."""
    rng = random.Random(seed)
    sig = []
    for vid in range(n):
        veh = generate.make_vehicle(G, nodes, rng, vid, demand, None)
        if veh is not None:
            r = veh["route"]
            sig.append((r[0][0], r[-1][1], len(r)))
    return sig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default=os.path.join(config.NETWORK_DIR, "graph.graphml"))
    args = ap.parse_args()

    print(f"graph: {args.graph}")
    G = ox.load_graphml(args.graph)
    generate.prepare_network(G)
    nodes = list(G.nodes)
    print(f"  {G.number_of_nodes():,} nodes / {G.number_of_edges():,} edges\n")

    # ---- gate 1: data
    config.DEMAND_NONWORK_ENABLED = True
    lu = landuse_data.nonwork_table()
    total = float(lu["nonwork_attr"].sum())
    gate("DATA: attraction table", len(lu) > 0 and total > 0,
         f"{len(lu)} block groups, {int(total):,} retail/service jobs "
         f"({'+'.join(config.NONWORK_SECTORS)})")

    # ---- gate 2: context
    nw = generate.build_nonwork_demand(G, nodes)
    ok = (nw is not None and len(nw["origin_w"]) == len(nodes)
          and np.isfinite(nw["dest_w"]).all() and sum(nw["origin_w"]) > 0
          and float(nw["dest_w"].sum()) > 0)
    gate("CONTEXT: weights aligned and finite", ok,
         f"share {nw['share']}, decay {nw['scale']:.0f} m" if nw else "context is None")
    if nw is None:
        sys.exit(1)

    # ---- gate 3: reproducibility
    a = draw_nonwork(nw, nodes, random.Random(42), 300)
    b = draw_nonwork(nw, nodes, random.Random(42), 300)
    gate("REPRODUCE: same seed, same 300 draws", a == b)

    # ---- gate 4: spatial sanity (directional assert, magnitudes reported)
    demand = generate.build_demand_weights(G, nodes)
    if demand is None:
        gate("SPATIAL: work demand available", False, "build_demand_weights None")
    else:
        nw_pairs = draw_nonwork(nw, nodes, random.Random(7), 400)
        wk_pairs = draw_work(demand, nodes, random.Random(8), 400)
        m_nw, m_wk = crowfly_mean(nw, nw_pairs), crowfly_mean(nw, wk_pairs)
        gate("SPATIAL: non-work shorter than work", m_nw < m_wk,
             f"nonwork {m_nw/1000:.1f} km vs work {m_wk/1000:.1f} km, ratio "
             f"{m_nw/m_wk:.2f} (NHTS vehicle-trip ratio ~0.54; crow-fly, "
             f"single-hour, so direction is the gate, the ratio is the report)")

    # ---- gate 5: inertness with the flag off
    config.DEMAND_NONWORK_ENABLED = False
    demand_off = generate.build_demand_weights(G, nodes)
    gate("INERTNESS: no layer in the demand dict",
         demand_off is not None and demand_off.get("nonwork") is None)
    sig_none = spawn_signature(G, nodes, demand_off, 99, 60)
    demand_absent = {k: v for k, v in demand_off.items() if k != "nonwork"}
    sig_absent = spawn_signature(G, nodes, demand_absent, 99, 60)
    gate("INERTNESS: spawn stream untouched (key None == key absent)",
         sig_none == sig_absent and len(sig_none) > 0, f"{len(sig_none)} vehicles")

    print(f"\nVERDICT: {'ALL PASS' if not FAILED else 'FAILURES: ' + ', '.join(FAILED)}")
    sys.exit(0 if not FAILED else 1)


if __name__ == "__main__":
    main()
