"""Predictor engineering for the Rao-style NO2 comparison (week 6).

The comparison runs two random forests with the SAME algorithm and predicts the
SAME target; only the predictor source differs:
  - the baseline forest gets Rao-style land-use predictors,
  - the ABM forest gets traffic predictors the simulation produces.

Rao's signature move is that every predictor is aggregated over circular buffers
of several radii around the point (he used 12 buffers from 100 to 1200 m), so a
location is described by its neighborhood, not just the one segment it sits on.
This module:
  1. turns an ABM run's per-segment output into raw traffic predictors, and
  2. provides the multi-buffer aggregation (config.BUFFER_RADII_M) that both the
     ABM side here and the land-use side (once NLCD is pulled) will reuse.

It runs no simulation and draws nothing. Build features once, save them, reuse.

Note (honest, current limit): the sim presently stores only vehicle-seconds of
activity ('value') and emitted NOx per segment. So the only raw traffic predictor
available right now is the activity load. Richer ones (throughput count, mean
speed, stopped/queued fraction) need a few extra accumulators in generate.py and
are the planned next step. We deliberately do NOT use emitted NOx as a predictor:
it is the ABM's mechanistic answer for NO2, so feeding it in would leak the target.
"""
import os
import sys

import numpy as np
import pandas as pd
import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def load_run(run_name=None):
    """Load one ABM run's per-segment results (columns: u, v, key, value, nox_g)."""
    run_name = config.RUN_NAME if run_name is None else run_name
    path = os.path.join(config.PROCESSED_DIR, f"{run_name}_segments.parquet")
    if not os.path.exists(path):
        raise SystemExit(f"No results at {path}; run the simulation first "
                         f"(python src/generate.py).")
    return pd.read_parquet(path)


def load_network():
    """Load the cached OSMnx graph (segment geometry lives here, not in the parquet)."""
    return ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))


def _segment_midpoints(G, df):
    """Latitude and longitude of each segment's midpoint, aligned row-for-row with
    df. The midpoint is the average of the two endpoint nodes (x = lon, y = lat).
    This is the point each segment's buffer is centered on."""
    lat = np.empty(len(df))
    lon = np.empty(len(df))
    for i, r in enumerate(df.itertuples()):
        lat[i] = 0.5 * (float(G.nodes[r.u]["y"]) + float(G.nodes[r.v]["y"]))
        lon[i] = 0.5 * (float(G.nodes[r.u]["x"]) + float(G.nodes[r.v]["x"]))
    return lat, lon


def _local_xy(lat, lon):
    """Project lat/lon to local meters with an equirectangular approximation around
    the study center. Buffer radii are small (<= 1200 m) so this flat-earth
    approximation is well under a meter of error and lets us do fast vectorized
    distances instead of haversine in a double loop."""
    lat0, lon0 = config.STUDY_CENTER
    m_per_deg_lat = 110_540.0
    m_per_deg_lon = 111_320.0 * np.cos(np.radians(lat0))
    x = (lon - lon0) * m_per_deg_lon
    y = (lat - lat0) * m_per_deg_lat
    return x, y


def buffer_sums(values, lat, lon, radii=None):
    """For each point, sum `values` over every point (including itself) whose
    midpoint falls within each buffer radius. Returns a dict {radius: array}.

    This is the Rao-style neighborhood aggregation: a segment's predictor at
    radius r is the total activity on all segments within r meters of it. Larger
    buffers fold in more of the surrounding network, capturing how a busy arterial
    raises pollution on the quiet blocks around it.
    """
    radii = config.BUFFER_RADII_M if radii is None else radii
    values = np.asarray(values, dtype=float)
    x, y = _local_xy(np.asarray(lat), np.asarray(lon))

    # pairwise squared distances; n ~ 2,800 so the n-by-n matrix is a few tens of MB
    dx = x[:, None] - x[None, :]
    dy = y[:, None] - y[None, :]
    d2 = dx * dx + dy * dy

    out = {}
    for r in radii:
        within = d2 <= float(r) ** 2          # boolean neighbor mask for this radius
        out[r] = within @ values              # sum of values over each row's neighbors
    return out


def build_abm_predictors(run_name=None, radii=None):
    """Assemble the ABM-side predictor table for one run: each segment, its
    midpoint, its raw activity load, and that load aggregated over every buffer
    radius. This is the feature matrix the ABM forest will train on.
    """
    radii = config.BUFFER_RADII_M if radii is None else radii
    G = load_network()
    df = load_run(run_name)
    lat, lon = _segment_midpoints(G, df)

    out = pd.DataFrame({
        "u": df["u"], "v": df["v"], "key": df["key"],
        "lat": lat, "lon": lon,
        "activity": df["value"].to_numpy(float),   # vehicle-seconds on the segment
    })

    # Rao-style buffered version of the traffic load, one column per radius.
    sums = buffer_sums(out["activity"].to_numpy(), lat, lon, radii)
    for r in radii:
        out[f"activity_buf{r}"] = sums[r]

    return out


def _segment_lengths(G, df):
    """Segment length in meters, aligned row-for-row with df (from the graph edge
    geometry, which the parquet does not carry)."""
    out = np.empty(len(df))
    for i, r in enumerate(df.itertuples()):
        out[i] = float(G[r.u][r.v][r.key].get("length", 10.0))
    return out


def build_site_predictors(sites, run_name=None, radii=None):
    """Build Rao-style multi-buffer ABM traffic predictors AT a set of points
    (the passive-sampler sites), the form the forest comparison needs.

    build_abm_predictors centers each buffer on a segment midpoint (segment ->
    segment). Here each buffer is centered on a sampler SITE, and we aggregate the
    surrounding segments' traffic into that site's feature row (site -> segments).
    Same neighborhood idea as Rao: a location is described by the traffic in the
    rings around it, not by the one segment it happens to sit on.

    `sites` is a DataFrame with columns site_id, lat, lon (e.g. from
    rao_data.rao_targets). For each site and each radius we compute:
      - activity_buf{r}:   total vehicle-seconds on segments within r meters
      - throughput_buf{r}: total vehicle traversals (the model's count) within r
      - meanspeed_buf{r}:  activity-weighted mean realized speed (m/s) within r,
                           with v_mean = length * throughput / vehicle-seconds
    plus n_seg_buf{max r} so a site with no nearby network is easy to drop.

    Only the segments present in the run are used, so a site outside the simulated
    network simply gets zeros (and n_seg ~ 0); filter those before training.
    """
    radii = config.BUFFER_RADII_M if radii is None else radii
    G = load_network()
    df = load_run(run_name)

    seg_lat, seg_lon = _segment_midpoints(G, df)
    activity = df["value"].to_numpy(float)
    throughput = df["throughput"].to_numpy(float)
    length = _segment_lengths(G, df)
    with np.errstate(divide="ignore", invalid="ignore"):
        v_mean = np.where(activity > 0, length * throughput / activity, 0.0)

    sx, sy = _local_xy(seg_lat, seg_lon)                       # segments
    px, py = _local_xy(sites["lat"].to_numpy(float),
                       sites["lon"].to_numpy(float))           # sites
    # site-by-segment squared distances (P sites x N segments)
    d2 = (px[:, None] - sx[None, :]) ** 2 + (py[:, None] - sy[None, :]) ** 2

    out = pd.DataFrame({
        "site_id": sites["site_id"].to_numpy(),
        "lat": sites["lat"].to_numpy(float),
        "lon": sites["lon"].to_numpy(float),
    })
    act_w = v_mean * activity                                  # for weighted speed
    for r in radii:
        within = d2 <= float(r) ** 2                           # P x N neighbor mask
        a = within @ activity
        out[f"activity_buf{r}"] = a
        out[f"throughput_buf{r}"] = within @ throughput
        with np.errstate(divide="ignore", invalid="ignore"):
            out[f"meanspeed_buf{r}"] = np.where(a > 0, (within @ act_w) / a, 0.0)
    out[f"n_seg_buf{max(radii)}"] = (d2 <= float(max(radii)) ** 2).sum(axis=1)
    return out


if __name__ == "__main__":
    run = sys.argv[1] if len(sys.argv) > 1 else config.RUN_NAME
    feats = build_abm_predictors(run)
    out_path = os.path.join(config.PROCESSED_DIR, f"{run}_abm_predictors.parquet")
    feats.to_parquet(out_path, index=False)
    pred_cols = [c for c in feats.columns if c.startswith("activity")]
    print(f"Built ABM predictors for '{run}': {len(feats)} segments, "
          f"{len(pred_cols)} predictor columns {pred_cols}")
    print(f"Saved to {out_path}")
    print(feats.head(4).to_string())
