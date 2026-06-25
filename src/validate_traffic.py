"""Validate the ABM's traffic pattern against real PBOT counts (Christof, Jun 25).

Pairs each real count point (from traffic_counts.py) with the nearest street
segment in the model, then asks the honest first question: does the ABM put heavy
traffic where the city actually counts heavy traffic?

The metric is SPEARMAN RANK correlation between the real ADT and the model's
per-segment activity. Rank correlation is the right tool here because the two
quantities are in different units (real vehicles per day vs simulated
vehicle-seconds) and the demand is still uniform random, so absolute levels are not
expected to match yet. Rank correlation ignores units and levels and asks only
whether the model ORDERS the streets the way reality does. A positive correlation
validates the network structure even before demand calibration; a weak one is the
signal to wire in the real PORTAL/ODOT demand (src/demand_data.py).

Run it with:  python src/validate_traffic.py [run_name]   (default config.RUN_NAME)
First run `python src/traffic_counts.py` to pull the counts.
"""
import os
import sys

import numpy as np
import pandas as pd
import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

SNAP_MAX_M = 40.0   # a count farther than this from any modeled segment is unmatched


def _local_xy(lat, lon):
    """Project lon/lat to local meters around the study center (small-area flat
    approximation, same as predictors.py), so nearest-segment search is fast."""
    lat0, lon0 = config.STUDY_CENTER
    x = (np.asarray(lon) - lon0) * 111_320.0 * np.cos(np.radians(lat0))
    y = (np.asarray(lat) - lat0) * 110_540.0
    return x, y


def _spearman(a, b):
    """Spearman rank correlation: Pearson correlation of the ranks."""
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def main(run_name):
    counts_path = os.path.join(config.PROCESSED_DIR, "pbot_traffic_counts.parquet")
    if not os.path.exists(counts_path):
        raise SystemExit("No counts yet; run `python src/traffic_counts.py` first.")
    counts = pd.read_parquet(counts_path).dropna(subset=["adt"])
    abm = pd.read_parquet(os.path.join(config.PROCESSED_DIR, f"{run_name}_segments.parquet"))
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))

    # segment midpoints, aligned row-for-row with the ABM table
    seg_lat = np.array([0.5 * (float(G.nodes[r.u]["y"]) + float(G.nodes[r.v]["y"]))
                        for r in abm.itertuples()])
    seg_lon = np.array([0.5 * (float(G.nodes[r.u]["x"]) + float(G.nodes[r.v]["x"]))
                        for r in abm.itertuples()])
    sx, sy = _local_xy(seg_lat, seg_lon)
    cx, cy = _local_xy(counts["lat"].to_numpy(), counts["lon"].to_numpy())

    # nearest segment for each count point (brute force; ~2k x ~3k is cheap)
    d2 = (cx[:, None] - sx[None, :]) ** 2 + (cy[:, None] - sy[None, :]) ** 2
    nearest = d2.argmin(axis=1)
    dist = np.sqrt(d2[np.arange(len(cx)), nearest])

    matched = counts.assign(seg=nearest, snap_m=dist)
    matched = matched[matched["snap_m"] <= SNAP_MAX_M]

    # one row per segment that got at least one count: mean real ADT vs the model's
    # measures on that segment
    per_seg = (matched.groupby("seg")
               .agg(adt=("adt", "mean"), n_counts=("adt", "size"))
               .reset_index())
    seg_idx = per_seg["seg"].to_numpy()
    per_seg["activity"] = abm["value"].to_numpy()[seg_idx]
    # throughput is the cleaner match to ADT (vehicle counts), but older runs lack it
    has_thru = "throughput" in abm.columns
    if has_thru:
        per_seg["throughput"] = abm["throughput"].to_numpy()[seg_idx]

    out = os.path.join(config.PROCESSED_DIR, f"{run_name}_count_validation.parquet")
    per_seg.to_parquet(out, index=False)

    rho_act = _spearman(per_seg["adt"], per_seg["activity"])
    print(f"Traffic validation for run '{run_name}'")
    print(f"  {len(counts)} count points, {len(matched)} matched to a segment "
          f"within {SNAP_MAX_M:.0f} m, on {len(per_seg)} distinct segments")
    print(f"  Spearman rank correlation (real ADT vs ...)")
    print(f"    model activity (vehicle-seconds): {rho_act:+.3f}")
    rho = rho_act
    if has_thru:
        rho_thru = _spearman(per_seg["adt"], per_seg["throughput"])
        print(f"    model throughput (vehicles)     : {rho_thru:+.3f}  "
              f"<- the apples-to-apples measure")
        rho = rho_thru
    nonzero = (per_seg["activity"] > 0).sum()
    print(f"  {nonzero}/{len(per_seg)} matched segments carry model traffic "
          f"({len(per_seg) - nonzero} real-count streets the model leaves empty)")
    print(f"  saved matched table to {out}")
    if rho >= 0.5:
        print("  Read: strong positive rank match; the model orders streets much "
              "like the real counts, even with uniform demand.")
    elif rho >= 0.25:
        print("  Read: moderate positive match; structure is partly right. Wiring in "
              "the real PORTAL/ODOT demand should sharpen it.")
    else:
        print("  Read: weak match; uniform-random demand is not enough. This motivates "
              "calibrating demand from the real time-of-day profile (demand_data.py).")


if __name__ == "__main__":
    run = sys.argv[1] if len(sys.argv) > 1 else config.RUN_NAME
    main(run)
