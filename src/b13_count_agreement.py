"""B3's pre-registered payoff measure: count agreement, paired vs control.

Analysis-only (CLAUDE.md single-source-of-truth): reads the saved b13_* and
metrocal_realism_* segments parquets plus the held-out PBOT counts. Never runs
a sim. The B1xB3 harness docstring says B3's headline is NOT busiest-Powell --
it changes WHERE cars go -- so the payoff is rank agreement with the held-out
counts. This script is that step.

Why not just call validate_traffic.main: that script hardcodes graph.graphml,
which in this worktree is the 1.5 km CORRIDOR graph, while every b13 run used
the 20 km metro graph -- snapping counts against the corridor graph and then
indexing a metro parquet would silently mismatch. This script snaps against
graph_metro20k_orca.graphml (the exact graph the runs used), reusing
validate_traffic's audited constants and Spearman so the logic cannot drift:
geometry snap, not midpoint snap (Jul 4 audit), same SNAP_MAX_M, and
throughput as the apples-to-apples measure against ADT. The snap is computed
ONCE and joined onto all 32 runs, which is also what makes 32 runs cheap.

Honesty notes:
  - No metro-scale count rho has ever been ledgered; the control's value here
    is itself new, so arms are read as PAIRED deltas against it, not against
    any corridor number (corridor rho 0.51/0.59 is a different graph and a
    different matched-count set -- do not compare across).
  - The PBOT counts stay held out: nothing here feeds back into a parameter.

Run: python src/b13_count_agreement.py
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd

import config
from validate_traffic import SNAP_MAX_M, _spearman  # the audited pieces, reused

METRO_GRAPH = os.path.join(config.NETWORK_DIR, "graph_metro20k_orca.graphml")
ARMS = ("pockets", "nonwork", "both")
SEEDS = (42, 7, 13, 99, 2024, 314, 777, 8)   # metrocal's pinned set


def control_name(seed):
    return f"metrocal_realism_n16500_s{seed}"


def arm_name(arm, seed):
    return f"b13_{arm}_n16500_s{seed}"


def snap_counts():
    """Snap each count point to the metro graph ONCE; returns (u,v,key), adt."""
    counts = pd.read_parquet(os.path.join(
        config.PROCESSED_DIR, "pbot_traffic_counts.parquet")).dropna(subset=["adt"])
    G = ox.load_graphml(METRO_GRAPH)
    if G.number_of_edges() < 100_000:
        raise SystemExit(f"{METRO_GRAPH} is not the metro graph; refusing")
    Gp = ox.project_graph(G)
    pts = gpd.GeoSeries(gpd.points_from_xy(counts["lon"], counts["lat"]),
                        crs="EPSG:4326").to_crs(Gp.graph["crs"])
    ne, nd = ox.distance.nearest_edges(Gp, pts.x.to_numpy(), pts.y.to_numpy(),
                                       return_dist=True)
    matched = counts.assign(edge=[tuple(e) for e in ne],
                            snap_m=np.asarray(nd, dtype=float))
    matched = matched[matched["snap_m"] <= SNAP_MAX_M]
    per_edge = matched.groupby("edge").agg(adt=("adt", "mean"),
                                           n=("adt", "size")).reset_index()
    print(f"{len(counts)} count points, {len(matched)} matched within "
          f"{SNAP_MAX_M:.0f} m, {len(per_edge)} distinct metro segments")
    return per_edge


def rho_for(run, per_edge):
    """Spearman(real ADT, model throughput) on the matched segments."""
    p = os.path.join(config.PROCESSED_DIR, f"{run}_segments.parquet")
    abm = pd.read_parquet(p)
    thru = {(r.u, r.v, r.key): r.throughput for r in abm.itertuples()}
    # a matched edge absent from the table would silently zero; make it loud
    missing = [e for e in per_edge["edge"] if e not in thru]
    if missing:
        raise SystemExit(f"{run}: {len(missing)} matched edges not in parquet")
    model = np.array([thru[e] for e in per_edge["edge"]])
    return _spearman(per_edge["adt"].to_numpy(), model)


def main():
    per_edge = snap_counts()
    rows = {}
    for seed in SEEDS:
        rows[("control", seed)] = rho_for(control_name(seed), per_edge)
        for arm in ARMS:
            rows[(arm, seed)] = rho_for(arm_name(arm, seed), per_edge)

    print("\nSpearman(real ADT, model throughput), metro graph, "
          "mean +/- SD over 8 seeds")
    ctrl = np.array([rows[("control", s)] for s in SEEDS])
    print(f"  {'control (realism)':20s} {ctrl.mean():+.3f} +/- {ctrl.std(ddof=1):.3f}")
    for arm in ARMS:
        a = np.array([rows[(arm, s)] for s in SEEDS])
        d = a - ctrl                       # paired: same seed, same snap
        pos = int((d > 0).sum())
        print(f"  {arm:20s} {a.mean():+.3f} +/- {a.std(ddof=1):.3f}   "
              f"paired delta {d.mean():+.3f} +/- {d.std(ddof=1):.3f}  "
              f"({pos}/8 seeds up)")


if __name__ == "__main__":
    main()
