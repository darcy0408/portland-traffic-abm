"""
Reconstruct ODOT sound-wall LINES from the TransGIS point inventory.

The ODOT Sound Barrier layer (TransGIS catalog MapServer layer 135) stores each
wall as a single POINT with a recorded length (len_meter) and height (ht_meter).
The noise physics needs a wall LINE so a source-to-receiver path can be tested
for crossing it. This script rebuilds each line with one assumption, stated
plainly: the wall runs parallel to the road at its snapped location, centered on
the ODOT point. The point's own offset from the road centerline puts the wall on
the correct side of the road automatically.

The snap supplies only the local road BEARING. Which edge the wall snaps to does
not matter for the physics (shielding is a pure geometry test against the wall
line), so a wall snapping to a frontage road parallel to its freeway is
harmless. What is NOT harmless is snapping to a perpendicular street: the first
any-class version of this snap drew several I-5 walls crossing the freeway at
right angles, because residential cross-streets dead-end AT the wall and their
tips sit closer than the freeway centerline. So the bearing comes from the road
class that plausibly generated the noise: state-highway walls (numeric HWYNUMB)
snap against motorway/trunk/primary edges only, county and city walls against
secondary-and-above, and the full graph is only a flagged fallback. Snapping
reuses the Jul 4 audit idiom: nearest edge GEOMETRY in a projected CRS, never
midpoints.

Reads the metro20k graph the Rose Quarter runs are pinned to (prereg Appendix R
md5, checked here with a warning, not a hard stop, since this is exploratory).
Runs no simulation. Outputs:
  data/processed/odot_walls_lines.parquet   one row per reconstructed wall
  outputs/figures/barrier_lines_map.png     verification map for eyeballing

Usage: python src/barriers.py [path/to/graph.graphml]
"""

import hashlib
import json
import os
import sys

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from matplotlib.collections import LineCollection
from pyproj import Transformer
from shapely.geometry import LineString

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WALLS_JSON = os.path.join(BASE, "data", "odot_sound_barriers_metro.json")
# The metro20k graph lives in the freeway-closure worktree; it is the exact
# graph (md5-pinned) the saved open/closed Rose Quarter runs were made on.
DEFAULT_GRAPH = os.path.normpath(os.path.join(
    BASE, "..", "freeway-closure", "data", "network", "graph.graphml"))
PREREG_GRAPH_MD5 = "6707ddf25d63f2b5b4d2948b37cdb783"
OUT_PARQUET = os.path.join(BASE, "data", "processed", "odot_walls_lines.parquet")
OUT_FIG = os.path.join(BASE, "outputs", "figures", "barrier_lines_map.png")

SNAP_WARN_M = 100.0   # a wall this far from any modeled edge gets flagged, not
                      # dropped: its bearing came from a road that may not be
                      # the one it shields, so eyeball it on the map
FALLBACK_M = 150.0    # if no class-appropriate edge is this close, fall back to
                      # the nearest edge of any class (and flag the row)
BEARING_STEP_M = 5.0  # half-window along the edge polyline for the local tangent

# Road classes a sound wall plausibly shields. State-highway walls sit on
# freeways and ODOT-maintained arterials (motorway/trunk/primary in OSM);
# county and city walls can also front secondary and tertiary arterials.
FREEWAY_CLASSES = {"motorway", "motorway_link", "trunk", "trunk_link",
                   "primary", "primary_link"}
ARTERIAL_CLASSES = FREEWAY_CLASSES | {"secondary", "secondary_link",
                                      "tertiary", "tertiary_link"}


def load_walls():
    """ODOT feature JSON to a clean DataFrame, one row per wall."""
    with open(WALLS_JSON) as f:
        raw = json.load(f)
    rows = []
    for feat in raw["features"]:
        a = feat["attributes"]
        rows.append({
            "objectid": a["OBJECTID"],
            "lon": feat["geometry"]["x"],
            "lat": feat["geometry"]["y"],
            "len_m": a.get("len_meter"),
            "ht_m": a.get("ht_meter"),
            "wall_type": a.get("ntg_typ"),
            "hwy": a.get("HWYNUMB"),
            "proj_nm": a.get("proj_nm"),
            "built": a.get("cnstrc_dt"),
            "county": a.get("COUNTYNAME"),
            "atnatn_pre": a.get("atnatn_pre"),
            "atnatn_msr": a.get("atnatn_msr"),
            "begmp": a.get("BEGMP"),
            "endmp": a.get("ENDMP"),
        })
    walls = pd.DataFrame(rows)

    # A wall with no recorded length cannot be drawn as a line: drop it and say so.
    n_nolen = int((walls["len_m"].isna() | (walls["len_m"] <= 0)).sum())
    walls = walls[walls["len_m"].notna() & (walls["len_m"] > 0)].copy()

    # A wall with no recorded height still has real geometry; impute the median
    # height of the rest and flag it so the physics step can exclude it if wanted.
    ht_median = float(walls.loc[walls["ht_m"] > 0, "ht_m"].median())
    walls["ht_imputed"] = walls["ht_m"].isna() | (walls["ht_m"] <= 0)
    walls.loc[walls["ht_imputed"], "ht_m"] = ht_median
    print(f"{len(walls)} walls kept ({n_nolen} dropped for missing length, "
          f"{int(walls['ht_imputed'].sum())} heights imputed to the {ht_median} m median)")
    return walls


def edge_line(Gp, u, v, k):
    """The projected geometry of one edge; straight node-to-node if untagged."""
    data = Gp.edges[u, v, k]
    if "geometry" in data:
        return data["geometry"]
    return LineString([(Gp.nodes[u]["x"], Gp.nodes[u]["y"]),
                       (Gp.nodes[v]["x"], Gp.nodes[v]["y"])])


def local_tangent(line, pt):
    """Unit direction of the polyline at the point nearest to pt."""
    s = line.project(pt)
    p0 = line.interpolate(max(s - BEARING_STEP_M, 0.0))
    p1 = line.interpolate(min(s + BEARING_STEP_M, line.length))
    dx, dy = p1.x - p0.x, p1.y - p0.y
    norm = float(np.hypot(dx, dy))
    if norm < 1e-9:
        # degenerate (zero-length edge): fall back to the whole-line direction
        (x0, y0), (x1, y1) = line.coords[0], line.coords[-1]
        dx, dy = x1 - x0, y1 - y0
        norm = float(np.hypot(dx, dy)) or 1.0
    return dx / norm, dy / norm


def _edge_label(data, key):
    """Edge attributes can be lists on merged OSM ways; flatten to one string."""
    v = data.get(key, "")
    if isinstance(v, (list, tuple)):
        v = ";".join(str(x) for x in v)
    return str(v)


def class_subgraph(Gp, classes):
    """A copy of Gp holding only edges of the given highway classes.

    Edge keys are preserved, so a (u, v, k) found here indexes Gp directly.
    """
    H = nx.MultiDiGraph(**Gp.graph)
    for u, v, k, data in Gp.edges(keys=True, data=True):
        hw = data.get("highway", "")
        hw = hw[0] if isinstance(hw, list) else hw
        if hw in classes:
            H.add_edge(u, v, key=k, **data)
    for n in H.nodes:
        H.nodes[n].update(Gp.nodes[n])
    return H


def snap_group(Gp, Gclass, pts, pass_name):
    """Snap points to the class-filtered graph, full graph as flagged fallback.

    Returns one dict per point: edge, snap distance, and which pass supplied it.
    """
    xs, ys = pts.x.to_numpy(), pts.y.to_numpy()
    ne, nd = ox.distance.nearest_edges(Gclass, xs, ys, return_dist=True)
    results = []
    far = [i for i, d in enumerate(nd) if d > FALLBACK_M]
    fb = {}
    if far:
        fne, fnd = ox.distance.nearest_edges(Gp, xs[far], ys[far], return_dist=True)
        fb = {i: (tuple(e), float(d)) for i, e, d in zip(far, fne, fnd)}
    for i, (e, d) in enumerate(zip(ne, nd)):
        if i in fb:
            results.append({"edge": fb[i][0], "snap_m": fb[i][1],
                            "snap_pass": "any-fallback"})
        else:
            results.append({"edge": tuple(e), "snap_m": float(d),
                            "snap_pass": pass_name})
    return results


def main(graph_path):
    with open(graph_path, "rb") as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    if md5 != PREREG_GRAPH_MD5:
        print(f"WARNING: graph md5 {md5} is not the prereg-pinned metro20k graph; "
              f"wall lines will not align with the saved Rose Quarter runs")
    else:
        print("graph md5 matches the prereg Appendix R pin")

    print("loading graph (93 MB, takes a minute)...")
    G = ox.load_graphml(graph_path)
    Gp = ox.project_graph(G)
    crs = Gp.graph["crs"]

    walls = load_walls().reset_index(drop=True)
    pts = gpd.GeoSeries(gpd.points_from_xy(walls["lon"], walls["lat"]),
                        crs="EPSG:4326").to_crs(crs)

    # Bearing comes from the road class the wall plausibly shields (see the
    # module docstring for the perpendicular cross-street failure this avoids).
    is_state = walls["hwy"].astype(str).str.isdigit()
    G_fwy = class_subgraph(Gp, FREEWAY_CLASSES)
    G_art = class_subgraph(Gp, ARTERIAL_CLASSES)
    snaps = [None] * len(walls)
    for mask, Gclass, name in ((is_state, G_fwy, "freeway"),
                               (~is_state, G_art, "arterial")):
        idxs = walls.index[mask]
        if len(idxs) == 0:
            continue
        for i, s in zip(idxs, snap_group(Gp, Gclass, pts[idxs], name)):
            snaps[i] = s

    recs = []
    for (idx, w), snap, pt in zip(walls.iterrows(), snaps, pts):
        u, v, k = snap["edge"]
        line = edge_line(Gp, u, v, k)
        tx, ty = local_tangent(line, pt)
        half = w["len_m"] / 2.0
        x0, y0 = pt.x - tx * half, pt.y - ty * half
        x1, y1 = pt.x + tx * half, pt.y + ty * half
        ed = Gp.edges[u, v, k]
        recs.append({**w.to_dict(),
                     "snap_m": snap["snap_m"],
                     "snap_pass": snap["snap_pass"],
                     "snap_name": _edge_label(ed, "name"),
                     "snap_ref": _edge_label(ed, "ref"),
                     "snap_class": _edge_label(ed, "highway"),
                     "bearing_deg": float(np.degrees(np.arctan2(ty, tx))),
                     "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    out = pd.DataFrame(recs)
    out["far_snap"] = out["snap_m"] > SNAP_WARN_M

    # endpoints back to lat/lon so downstream scripts never need this CRS object
    inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    out["lon0"], out["lat0"] = inv.transform(out["x0"].to_numpy(), out["y0"].to_numpy())
    out["lon1"], out["lat1"] = inv.transform(out["x1"].to_numpy(), out["y1"].to_numpy())
    out["proj_crs"] = str(crs)

    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    out.to_parquet(OUT_PARQUET, index=False)
    print(f"wrote {len(out)} wall lines to {OUT_PARQUET}")
    print(f"snap distance m: median {out.snap_m.median():.1f}, "
          f"90th pct {out.snap_m.quantile(0.9):.1f}, max {out.snap_m.max():.1f}, "
          f"{int(out.far_snap.sum())} beyond {SNAP_WARN_M:.0f} m (flagged)")
    print("snap pass:", out.snap_pass.value_counts().to_dict())
    print("snapped road classes:", out.snap_class.value_counts().head(8).to_dict())

    make_figure(Gp, out)


def _base_edges(Gp, classes=None):
    """Edge polylines for the background map, optionally filtered by class."""
    segs = []
    for u, v, k, data in Gp.edges(keys=True, data=True):
        if classes is not None:
            hw = data.get("highway", "")
            hw = hw[0] if isinstance(hw, list) else hw
            if hw not in classes:
                continue
        if "geometry" in data:
            segs.append(np.asarray(data["geometry"].coords))
        else:
            segs.append(np.array([(Gp.nodes[u]["x"], Gp.nodes[u]["y"]),
                                  (Gp.nodes[v]["x"], Gp.nodes[v]["y"])]))
    return segs


def make_figure(Gp, out):
    """Two panels: full metro walls over major roads, and a Rose Quarter zoom."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 9))
    wall_segs = [((r.x0, r.y0), (r.x1, r.y1)) for r in out.itertuples()]
    heights = out["ht_m"].to_numpy()

    major = {"motorway", "motorway_link", "trunk", "trunk_link", "primary"}
    ax = axes[0]
    ax.add_collection(LineCollection(_base_edges(Gp, major), colors="0.8", lw=0.5))
    lc = LineCollection(wall_segs, array=heights, cmap="viridis", lw=2.5)
    ax.add_collection(lc)
    # flagged far snaps get a red underlay so a doubtful bearing source is visible
    far = out[out["far_snap"]]
    if len(far):
        ax.add_collection(LineCollection(
            [((r.x0, r.y0), (r.x1, r.y1)) for r in far.itertuples()],
            colors="red", lw=6, alpha=0.4, zorder=1))
    ax.autoscale()
    ax.set_aspect("equal")
    ax.set_title(f"ODOT sound walls reconstructed as lines (n={len(out)}), "
                 f"red = snapped >{SNAP_WARN_M:.0f} m from a road")
    fig.colorbar(lc, ax=ax, shrink=0.6, label="wall height (m)")

    # Rose Quarter zoom: the I-5 stretch the Sept 11 closure affects
    zoom = gpd.GeoSeries(gpd.points_from_xy([-122.70, -122.64], [45.50, 45.56]),
                         crs="EPSG:4326").to_crs(Gp.graph["crs"])
    zx0, zy0 = zoom[0].x, zoom[0].y
    zx1, zy1 = zoom[1].x, zoom[1].y
    ax = axes[1]
    ax.add_collection(LineCollection(_base_edges(Gp), colors="0.85", lw=0.3))
    ax.add_collection(LineCollection(_base_edges(Gp, major), colors="0.6", lw=0.8))
    lc2 = LineCollection(wall_segs, array=heights, cmap="viridis", lw=3.0)
    ax.add_collection(lc2)
    ax.set_xlim(zx0, zx1)
    ax.set_ylim(zy0, zy1)
    ax.set_aspect("equal")
    ax.set_title("Rose Quarter zoom (I-5 / I-84 / I-405)")

    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT_FIG), exist_ok=True)
    fig.savefig(OUT_FIG, dpi=150)
    print(f"wrote {OUT_FIG}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GRAPH)
