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

The sim stores vehicle-seconds of activity ('value'), throughput (vehicle
entries), and emitted NOx per segment. Activity and throughput feed the features
directly, and mean speed is recovered from them (length * throughput / activity).
We deliberately do NOT use emitted NOx as a predictor: it is the ABM's mechanistic
answer for NO2, so feeding it in would leak the target. forest_compare.py enforces
this with an explicit feature allowlist.
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
    """Load one ABM run's per-segment results (columns: u, v, key, value, throughput, nox_g)."""
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


def _edge_sample_points(G, edge_ids, step=20.0):
    """Sample points every `step` meters along each edge's TRUE geometry, for
    length-weighted buffer attribution.

    Returns (x, y, seg_idx, frac): local-meter coordinates of every sample point,
    the row index of the edge each point belongs to, and the fraction 1/n of that
    edge the point carries. Attributing an edge quantity as frac * quantity at
    each point makes a buffer sum a length-weighted overlap: a 300 m segment half
    inside a 100 m buffer contributes half its value, instead of all of it or
    none of it depending on where one midpoint lands (the all-or-nothing midpoint
    test was the same bug class as the Jul 4 count-snapping bug; at r=100 it gave
    a median 24% feature error and false zeros at 5 of 64 Rao sites). Curved
    edges (freeway ramps, river roads) use their OSM geometry, so mass sits on
    the actual road line, not on a chord midpoint up to 340 m off it.

    edge_ids is a sequence of (u, v, key) triples; seg_idx indexes into it.
    """
    xs, ys, seg, frac = [], [], [], []
    for i, (u, v, k) in enumerate(edge_ids):
        d = G[u][v][k]
        length = float(d.get("length", 10.0))
        n = max(2, int(np.ceil(length / step)) + 1)
        t = np.linspace(0.0, 1.0, n)
        geom = d.get("geometry")
        if geom is None:
            # straight edge: interpolate between the endpoint nodes
            la = float(G.nodes[u]["y"]) + t * (float(G.nodes[v]["y"]) - float(G.nodes[u]["y"]))
            lo = float(G.nodes[u]["x"]) + t * (float(G.nodes[v]["x"]) - float(G.nodes[u]["x"]))
        else:
            pts = [geom.interpolate(ti, normalized=True) for ti in t]
            la = np.array([p.y for p in pts])
            lo = np.array([p.x for p in pts])
        x, y = _local_xy(la, lo)
        xs.append(x)
        ys.append(y)
        seg.append(np.full(n, i))
        frac.append(np.full(n, 1.0 / n))
    return (np.concatenate(xs), np.concatenate(ys),
            np.concatenate(seg).astype(int), np.concatenate(frac))


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

    NOTE: this segment-to-segment path still uses all-or-nothing MIDPOINT
    inclusion (each segment is one point). It matches the committed
    powell_through-era behavior and is only used by the per-segment demo path,
    not the forest comparison; the site-centered path (build_site_predictors)
    uses length-weighted true-geometry attribution instead.
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
      - activity_buf{r}:   vehicle-seconds within r meters, length-weighted (a
                           segment contributes the fraction of its length that
                           lies inside the buffer, along its true OSM geometry)
      - throughput_buf{r}: vehicle traversals within r, same weighting
      - meanspeed_buf{r}:  activity-weighted mean realized speed (m/s) within r,
                           with v_mean = length * throughput / vehicle-seconds
    plus n_seg_buf{max r}: the length-weighted (fractional) count of segments
    inside the largest buffer. It is > 0 exactly when any road lies within reach,
    which is all the on-network filter needs.

    Only the segments present in the run are used, so a site outside the simulated
    network simply gets zeros (and n_seg = 0); filter those before training.
    """
    radii = config.BUFFER_RADII_M if radii is None else radii
    G = load_network()
    df = load_run(run_name)

    activity = df["value"].to_numpy(float)
    throughput = df["throughput"].to_numpy(float)
    length = _segment_lengths(G, df)
    with np.errstate(divide="ignore", invalid="ignore"):
        v_mean = np.where(activity > 0, length * throughput / activity, 0.0)

    # Sample points along every segment's true geometry; each point carries its
    # segment's per-point share of activity/throughput (length-weighted overlap).
    edge_ids = list(zip(df["u"].to_numpy(), df["v"].to_numpy(), df["key"].to_numpy()))
    ex, ey, seg_idx, frac = _edge_sample_points(G, edge_ids)
    pt_act = frac * activity[seg_idx]
    pt_thr = frac * throughput[seg_idx]
    pt_actw = frac * (v_mean * activity)[seg_idx]              # for weighted speed

    px, py = _local_xy(sites["lat"].to_numpy(float),
                       sites["lon"].to_numpy(float))           # sites

    r_max = float(max(radii))
    acc = {r: {"a": [], "t": [], "w": []} for r in radii}
    nseg = []
    # chunk over sites: the full site-by-point distance matrix would be large
    # (352 sites x ~174k points at metro scale), a chunk is a few tens of MB
    chunk = 64
    for s0 in range(0, len(px), chunk):
        s1 = min(s0 + chunk, len(px))
        d2 = (px[s0:s1, None] - ex[None, :]) ** 2 + (py[s0:s1, None] - ey[None, :]) ** 2
        for r in radii:
            within = d2 <= float(r) ** 2                       # chunk x points mask
            acc[r]["a"].append(within @ pt_act)
            acc[r]["t"].append(within @ pt_thr)
            acc[r]["w"].append(within @ pt_actw)
        nseg.append((d2 <= r_max ** 2) @ frac)                 # fractional segment count

    out = pd.DataFrame({
        "site_id": sites["site_id"].to_numpy(),
        "lat": sites["lat"].to_numpy(float),
        "lon": sites["lon"].to_numpy(float),
    })
    for r in radii:
        a = np.concatenate(acc[r]["a"])
        out[f"activity_buf{r}"] = a
        out[f"throughput_buf{r}"] = np.concatenate(acc[r]["t"])
        with np.errstate(divide="ignore", invalid="ignore"):
            out[f"meanspeed_buf{r}"] = np.where(a > 0, np.concatenate(acc[r]["w"]) / a, 0.0)
    out[f"n_seg_buf{max(radii)}"] = np.concatenate(nseg)
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
