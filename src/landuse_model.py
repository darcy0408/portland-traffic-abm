"""A strong Rao-style static land-use regression baseline for the NO2 contrast.

WHAT THIS IS
This builds a genuinely good static land-use regression (LUR) that predicts the
agent model's per-segment NO2 surface, so the static-vs-ABM contrast figure rests
on a fair baseline instead of a strawman. An earlier quick version used only
population and jobs as predictors and fit the ABM surface poorly (out-of-bag
R^2 = -0.16). The fix here is richer, classic LUR predictors, all derived from data
ALREADY in the repo, with NO external downloads: built-environment road geometry by
class, intersection density, distance to the nearest major road, plus the
population and jobs masses, each aggregated over Rao's buffer radii.

CRITICAL FRAMING (the whole point of using these predictors)
Every predictor here describes the PERMANENT built environment and demographics:
the road network's geometry and class, how dense the intersections are, how far a
spot sits from a major arterial, and how many people live and jobs sit nearby. A
static land-use regression is fit ONCE on those fixed features. It is NOT refit for
a temporary road closure (a marathon, a bridge-maintenance closure, an I-5 lane
closure). The land use does not change when a street is barricaded for a day, so the
predictors are held FIXED across a closure scenario. A function of unchanged inputs
returns an unchanged output, so this model's predicted surface is byte-for-byte
identical open vs closed, and its predicted CHANGE under a closure is exactly zero on
every segment. That invariance is the contribution we are illustrating: even a
well-fit static model is structurally blind to a closure. We therefore never
"reclose" the network when predicting. We predict on the same fixed feature matrix
for both the open and the closed scenario, by construction.

This module runs NO simulation and draws nothing. It only READS:
  - data/processed/powell_no2_open_segments.parquet  (the target: F_NO2 * nox_g)
  - data/processed/landuse_bg.parquet                (block-group population, jobs)
  - data/network/graph.graphml                       (road geometry and classes)
and fits a random forest with the same algorithm the ABM-side forest uses, so the
only difference between the two forests is the predictor source.

API
  build_static_model() -> StaticModel namedtuple with:
    .model        the fitted RandomForestRegressor (oob_score=True). It is fit on
                  log1p(NO2): traffic NO2 is heavy-tailed, and log fitting is the
                  standard land-use-regression convention for pollution concentrations.
                  .model.oob_prediction_ is therefore on the log scale.
    .features     the feature DataFrame, one row per open-surface segment, in the
                  open-surface parquet's u,v,key order
    .predicted    numpy array of predicted NO2 in raw grams (the log fit is exp-back-
                  transformed), aligned to those same rows
    .seg_keys     list of (u, v, key) tuples in that same order
    .oob_r2       float, the out-of-bag R^2 on the log1p(NO2) scale the model was fit
                  on (the meaningful, clearly positive metric). The raw-grams-scale OOB
                  R^2 is near zero by construction (a static model cannot reproduce the
                  extreme arterial peaks); __main__ prints both.

  To get the closure-invariant predicted surface for the contrast figure:
    sm = build_static_model()
    predicted_no2, seg_keys, oob_r2 = sm.predicted, sm.seg_keys, sm.oob_r2
  Use `predicted_no2` for BOTH the open and the closed panel: it does not change,
  which is exactly what the figure demonstrates.
"""
import os
import sys
from collections import namedtuple

import numpy as np
import pandas as pd
import osmnx as ox
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import predictors   # reuse the midpoint + local-projection helpers (do not edit it)

# Paths to the read-only inputs.
OPEN_SURFACE_PATH = os.path.join(config.PROCESSED_DIR, "powell_no2_open_segments.parquet")
BG_PATH = os.path.join(config.PROCESSED_DIR, "landuse_bg.parquet")

# Road-class grouping. "Major" is the arterial/through-traffic spine that carries
# the bulk of vehicle flow (and so the bulk of traffic NO2); "minor" is the local
# access network. Each OSM highway tag is mapped to one of these two groups, and the
# link ramps follow their parent class. Tags not listed (e.g. busway) fall through to
# minor, which is the conservative default since they carry little car traffic.
MAJOR_CLASSES = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
}
MINOR_CLASSES = {
    "tertiary", "tertiary_link",
    "residential", "unclassified", "living_street", "service", "road",
}

# Ordinal rank of a segment's OWN road class: higher = bigger arterial carrying more
# through traffic, so higher expected emissions. This is a permanent property of the
# infrastructure (the road's design class does not change in a closure), so it is a
# legitimate built-environment predictor and stays fixed open vs closed. Link ramps
# inherit their parent class's rank.
HIGHWAY_RANK = {
    "motorway": 6, "trunk": 5, "primary": 4, "secondary": 3,
    "tertiary": 2, "unclassified": 1, "residential": 1, "road": 1,
    "living_street": 0, "service": 0, "busway": 0,
}

# A namedtuple keeps the return values explicit and ordered for the caller.
StaticModel = namedtuple(
    "StaticModel", ["model", "features", "predicted", "seg_keys", "oob_r2"]
)


def _highway_class(tag):
    """Return 'major' or 'minor' for an OSM 'highway' tag. The tag can be a single
    string or, where OSM merged ways, a list of strings. For a list we treat the
    segment as major if ANY of its tags is a major class, since a road is only as
    minor as its busiest classification."""
    if isinstance(tag, (list, tuple)):
        tags = [str(t) for t in tag]
    else:
        tags = [str(tag)]
    if any(t in MAJOR_CLASSES for t in tags):
        return "major"
    return "minor"


def _highway_rank(tag):
    """Ordinal road-class rank for a segment's own 'highway' tag (see HIGHWAY_RANK).
    For a merged list of tags we take the highest rank, mirroring _highway_class:
    a road is described by its busiest classification. Link ramps inherit their
    parent class by stripping the '_link' suffix before lookup."""
    if isinstance(tag, (list, tuple)):
        tags = [str(t) for t in tag]
    else:
        tags = [str(tag)]
    return max(HIGHWAY_RANK.get(t.replace("_link", ""), 1) for t in tags)


def _own_segment_features(G, seg_df):
    """Each segment's OWN permanent road properties, aligned to seg_df rows: its
    length in meters, whether it is a major road (1/0), and its road-class rank. A
    segment's own emissions scale with how much road there is and how big a road it is,
    so these are the strongest per-segment built-environment signals. All three are
    fixed infrastructure and so are closure-invariant."""
    edge_data = {(u, v, k): d for u, v, k, d in G.edges(keys=True, data=True)}
    own_len, own_major, own_rank = [], [], []
    for r in seg_df.itertuples():
        d = edge_data.get((r.u, r.v, r.key), {})
        tag = d.get("highway")
        own_len.append(float(d.get("length", 0.0)))
        own_major.append(1.0 if _highway_class(tag) == "major" else 0.0)
        own_rank.append(float(_highway_rank(tag)))
    return (np.array(own_len), np.array(own_major), np.array(own_rank))


def _cross_buffer_sums(center_lat, center_lon, pt_lat, pt_lon, values, radii):
    """For each CENTER point, sum `values` over every POINT within each buffer radius.
    Returns a dict {radius: array of length len(centers)}.

    This is the Rao-style neighborhood aggregation generalized to two different point
    sets: the centers are the segment midpoints we are describing, and the points are
    whatever mass we are aggregating (block-group centroids, edge midpoints carrying
    road length, or graph nodes carrying a count of one). predictors.buffer_sums only
    does the self-join case (centers == points), so we write the cross case here and
    reuse predictors._local_xy for the identical flat-earth projection."""
    cx, cy = predictors._local_xy(np.asarray(center_lat), np.asarray(center_lon))
    px, py = predictors._local_xy(np.asarray(pt_lat), np.asarray(pt_lon))
    values = np.asarray(values, dtype=float)

    # pairwise squared distances, centers (rows) by points (cols)
    dx = cx[:, None] - px[None, :]
    dy = cy[:, None] - py[None, :]
    d2 = dx * dx + dy * dy

    out = {}
    for r in radii:
        within = d2 <= float(r) ** 2      # neighbor mask for this radius
        out[r] = within @ values          # sum of values over each center's neighbors
    return out


def _nearest_distance(center_lat, center_lon, pt_lat, pt_lon):
    """Minimum distance in meters from each center to the nearest point in the point
    set. Used for distance-to-nearest-major-road. Same flat-earth projection as the
    buffers, so the units line up."""
    cx, cy = predictors._local_xy(np.asarray(center_lat), np.asarray(center_lon))
    px, py = predictors._local_xy(np.asarray(pt_lat), np.asarray(pt_lon))
    dx = cx[:, None] - px[None, :]
    dy = cy[:, None] - py[None, :]
    d2 = dx * dx + dy * dy
    return np.sqrt(d2.min(axis=1))


def _edge_geometry(G):
    """Per-edge midpoint, length, and major/minor class for every graph edge.
    Returns four aligned numpy arrays (lat, lon, length_m, is_major). These are the
    POINTS for the road-length and distance-to-major features. We read them straight
    from the graph so they cover the full network independent of any row ordering."""
    lat, lon, length, is_major = [], [], [], []
    for u, v, k, d in G.edges(keys=True, data=True):
        # midpoint of the edge = mean of its two endpoint node coordinates
        lat.append(0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"])))
        lon.append(0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"])))
        length.append(float(d.get("length", 0.0)))
        is_major.append(_highway_class(d.get("highway")) == "major")
    return (np.array(lat), np.array(lon), np.array(length), np.array(is_major, dtype=bool))


def _node_coords(G):
    """Latitude/longitude of every graph node. These are the POINTS for the
    intersection-density feature (count of nodes within each buffer)."""
    lat = np.array([float(G.nodes[n]["y"]) for n in G.nodes])
    lon = np.array([float(G.nodes[n]["x"]) for n in G.nodes])
    return lat, lon


def build_features(G, seg_df, radii=None):
    """Build the full Rao-style land-use feature matrix, one row per segment in
    seg_df's order. Every feature is a function of the permanent built environment and
    demographics only, so the matrix is identical open vs closed (see module docstring).

    Features, each aggregated over every buffer radius unless noted:
      pop_buf{r}        resident population within r meters (19 block-group masses)
      jobs_buf{r}       workplace jobs within r meters
      majrdlen_buf{r}   meters of major-road (arterial) length within r meters
      minrdlen_buf{r}   meters of minor-road (local) length within r meters
      nodes_buf{r}      intersection density: count of graph nodes within r meters
      dist_major        meters to the nearest major-road segment midpoint (single col)
      own_length        the segment's own length in meters (single col)
      own_is_major      1 if the segment is itself a major road, else 0 (single col)
      own_rank          the segment's own road-class rank, 0..6 (single col)
    """
    radii = config.BUFFER_RADII_M if radii is None else radii

    # Center points: the midpoint of each segment we are predicting, aligned to seg_df.
    seg_lat, seg_lon = predictors._segment_midpoints(G, seg_df)

    # Point set 1: block-group centroids carrying population and jobs.
    bg = pd.read_parquet(BG_PATH)
    bg_lat = bg["lat"].to_numpy(float)
    bg_lon = bg["lon"].to_numpy(float)
    pop = bg["population"].to_numpy(float)
    jobs = bg["jobs"].to_numpy(float)

    # Point set 2: every edge midpoint carrying its length, split by road class.
    e_lat, e_lon, e_len, e_major = _edge_geometry(G)
    maj_len = np.where(e_major, e_len, 0.0)   # length counted only on major edges
    min_len = np.where(e_major, 0.0, e_len)   # length counted only on minor edges

    # Point set 3: graph nodes, each a count of one, for intersection density.
    n_lat, n_lon = _node_coords(G)
    ones = np.ones_like(n_lat)

    cols = {}

    # Population and jobs within each buffer (the demographic LUR predictors).
    pop_sums = _cross_buffer_sums(seg_lat, seg_lon, bg_lat, bg_lon, pop, radii)
    job_sums = _cross_buffer_sums(seg_lat, seg_lon, bg_lat, bg_lon, jobs, radii)

    # Major and minor road length within each buffer (the road-geometry predictors,
    # the strongest classic LUR signal for traffic pollution).
    maj_sums = _cross_buffer_sums(seg_lat, seg_lon, e_lat, e_lon, maj_len, radii)
    min_sums = _cross_buffer_sums(seg_lat, seg_lon, e_lat, e_lon, min_len, radii)

    # Intersection density within each buffer (count of nodes; stop-and-go zones).
    node_sums = _cross_buffer_sums(seg_lat, seg_lon, n_lat, n_lon, ones, radii)

    for r in radii:
        cols[f"pop_buf{r}"] = pop_sums[r]
        cols[f"jobs_buf{r}"] = job_sums[r]
        cols[f"majrdlen_buf{r}"] = maj_sums[r]
        cols[f"minrdlen_buf{r}"] = min_sums[r]
        cols[f"nodes_buf{r}"] = node_sums[r]

    # Distance to the nearest major-road segment (single, non-buffered feature). A
    # segment that is itself major has its own midpoint in the major point set, so its
    # distance is ~0; quiet residential blocks far from any arterial score high.
    cols["dist_major"] = _nearest_distance(seg_lat, seg_lon, e_lat[e_major], e_lon[e_major])

    # The segment's OWN permanent road properties (length, major flag, class rank).
    # These carry the bulk of the per-segment signal: a long arterial emits far more
    # than a short residential block, regardless of its neighborhood.
    own_len, own_major_flag, own_rank = _own_segment_features(G, seg_df)
    cols["own_length"] = own_len
    cols["own_is_major"] = own_major_flag
    cols["own_rank"] = own_rank

    return pd.DataFrame(cols, index=seg_df.index)


def build_site_features(G, sites, radii=None):
    """Build the Rao-style land-use feature matrix at a set of POINTS (the
    passive-sampler sites), one row per site in `sites` order.

    This is the land-use counterpart to predictors.build_site_predictors: the same
    buffer aggregation, but centered on each sampler site instead of a segment
    midpoint, so the static (land-use) and agent (traffic) forests are fit on the
    SAME points with only the predictor SOURCE differing. It reuses every helper in
    this module unchanged; build_features (the per-segment demo path) is untouched.

    `sites` is a DataFrame with columns site_id, lat, lon. Features (each over every
    buffer radius): pop_buf, jobs_buf, majrdlen_buf, minrdlen_buf, nodes_buf, plus a
    single dist_major (meters to the nearest major-road midpoint). The per-segment
    "own road" features (own_length/own_is_major/own_rank) are dropped: a sampler
    point does not sit on one specific edge, and dist_major already encodes arterial
    proximity. Every feature is permanent built environment, so it is closure-
    invariant exactly as in the per-segment case.
    """
    radii = config.BUFFER_RADII_M if radii is None else radii

    c_lat = sites["lat"].to_numpy(float)        # center points: the sampler sites
    c_lon = sites["lon"].to_numpy(float)

    bg = pd.read_parquet(BG_PATH)               # population / jobs masses
    bg_lat, bg_lon = bg["lat"].to_numpy(float), bg["lon"].to_numpy(float)
    pop, jobs = bg["population"].to_numpy(float), bg["jobs"].to_numpy(float)

    e_lat, e_lon, e_len, e_major = _edge_geometry(G)
    maj_len = np.where(e_major, e_len, 0.0)
    min_len = np.where(e_major, 0.0, e_len)

    n_lat, n_lon = _node_coords(G)
    ones = np.ones_like(n_lat)

    pop_sums = _cross_buffer_sums(c_lat, c_lon, bg_lat, bg_lon, pop, radii)
    job_sums = _cross_buffer_sums(c_lat, c_lon, bg_lat, bg_lon, jobs, radii)
    maj_sums = _cross_buffer_sums(c_lat, c_lon, e_lat, e_lon, maj_len, radii)
    min_sums = _cross_buffer_sums(c_lat, c_lon, e_lat, e_lon, min_len, radii)
    node_sums = _cross_buffer_sums(c_lat, c_lon, n_lat, n_lon, ones, radii)

    cols = {}
    for r in radii:
        cols[f"pop_buf{r}"] = pop_sums[r]
        cols[f"jobs_buf{r}"] = job_sums[r]
        cols[f"majrdlen_buf{r}"] = maj_sums[r]
        cols[f"minrdlen_buf{r}"] = min_sums[r]
        cols[f"nodes_buf{r}"] = node_sums[r]
    cols["dist_major"] = _nearest_distance(c_lat, c_lon, e_lat[e_major], e_lon[e_major])

    return pd.DataFrame(cols, index=sites.index)


def build_static_model(radii=None):
    """Load everything, build the land-use features, fit the random forest, and return
    a StaticModel. The forest uses the SAME settings as the ABM-side forest so the two
    are directly comparable: only the predictor source differs.

    The returned .predicted surface is closure-invariant by construction. It is fit and
    predicted on the fixed land-use features, never re-derived from a reclosed network,
    so a caller should use it unchanged for both the open and the closed panel.
    """
    radii = config.BUFFER_RADII_M if radii is None else radii

    # Load the cached graph and the ABM open surface (the prediction target).
    G = predictors.load_network()
    seg_df = pd.read_parquet(OPEN_SURFACE_PATH)

    # Target: per-segment NO2 = F_NO2 * NOx, the ABM's own answer we are trying to
    # reproduce from static land use alone.
    y = (config.F_NO2 * seg_df["nox_g"].to_numpy(float))

    # Traffic NO2 is heavy-tailed: most segments sit near zero while a few arterials
    # spike (here mean 1.7 g, median 0.3 g, max ~156 g). We therefore fit on log1p(NO2),
    # the standard land-use-regression convention for skewed pollution concentrations.
    # On the raw scale a handful of extreme arterial peaks dominate the squared error
    # and drive R^2 negative even for a model that ranks segments well; the log scale
    # measures the structure the model actually captures. Predictions are exp-back-
    # transformed below so the returned surface is in raw NO2 grams, matching the ABM.
    y_log = np.log1p(y)

    # Build the feature matrix aligned row-for-row to seg_df (the open surface order).
    features = build_features(G, seg_df, radii)
    X = features.to_numpy()

    # Same RF configuration the ABM-side forest uses; oob_score gives an honest
    # generalization estimate without a separate holdout.
    rf = RandomForestRegressor(
        n_estimators=400, random_state=config.RANDOM_SEED,
        oob_score=True, n_jobs=-1,
    )
    rf.fit(X, y_log)

    # Predicted surface back on the raw NO2 grams scale (expm1 undoes the log1p fit).
    predicted = np.expm1(rf.predict(X))
    seg_keys = [(int(r.u), int(r.v), int(r.key)) for r in seg_df.itertuples()]

    # Headline OOB R^2 is on the log scale the model was fit on (the meaningful, clearly
    # positive metric). The raw-scale OOB R^2 is recoverable by the caller from
    # rf.oob_prediction_ (see __main__); it is near zero because even a strong static
    # model cannot reproduce the extreme arterial peaks, itself part of the contrast.
    return StaticModel(
        model=rf,
        features=features,
        predicted=predicted,
        seg_keys=seg_keys,
        oob_r2=float(rf.oob_score_),
    )


if __name__ == "__main__":
    sm = build_static_model()

    # Raw-scale OOB R^2 for honesty: back-transform the model's out-of-bag predictions
    # and score them against the raw NO2 target.
    seg_df = pd.read_parquet(OPEN_SURFACE_PATH)
    y_raw = config.F_NO2 * seg_df["nox_g"].to_numpy(float)
    oob_r2_raw = r2_score(y_raw, np.expm1(sm.model.oob_prediction_))

    print(f"Static land-use forest fit to the ABM NO2 surface "
          f"({len(sm.seg_keys)} segments):")
    print(f"  out-of-bag R^2 (log NO2, the fit scale) : {sm.oob_r2:.3f}")
    print(f"  out-of-bag R^2 (raw NO2 grams)          : {oob_r2_raw:.3f}")
    print(f"  features                                : {sm.features.shape[1]}")

    # Top feature importances tell us which built-environment signals carry the fit.
    importances = pd.Series(sm.model.feature_importances_, index=sm.features.columns)
    top = importances.sort_values(ascending=False).head(8)
    print("  top 8 feature importances:")
    for name, imp in top.items():
        print(f"    {name:18s} {imp:.3f}")
