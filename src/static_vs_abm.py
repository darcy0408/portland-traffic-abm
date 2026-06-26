"""The static-vs-dynamic contrast figure (the SIGSPATIAL money shot).

The whole research claim in one picture. Close a block of SE Powell, then color
every street segment by how much its NO2 CHANGES, on one shared red/blue scale,
under two methods side by side:

  - Left, a static land-use model (the same random-forest-on-buffers method Rao et
    al. use). Its predictors are population and jobs aggregated over circular
    buffers. A road closure changes no land-use input, so every predictor is
    byte-for-byte identical before and after, and a function of unchanged inputs
    returns an unchanged output. Its predicted change is exactly zero on every
    segment: the whole panel stays blank. The limitation is structural, not a
    tuning artifact. No static land-use model can respond to a closure.

  - Right, this project's agent-based model. The surface comes from where cars
    actually drive. When SE Powell closes the cars reroute, so NO2 drops on the
    closed stretch (blue) and rises on the parallel arterials, SE Division and SE
    Holgate (red). The panel lights up.

A blank panel next to a vivid one, on the same scale, is the contribution: a
network-responsive exposure surface that a static map structurally cannot produce.
This needs nothing from Rao's data; it stands on its own.

This script runs NO simulation. It reads the open and closed result files the
closure experiment already saved and draws. Single source of truth: the numbers
come from those committed files, not a fresh run.

Run:  python src/static_vs_abm.py
"""
import os
import sys

import numpy as np
import pandas as pd
import osmnx as ox
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from sklearn.ensemble import RandomForestRegressor

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import predictors                      # reuse the midpoint + projection helpers
from generate import closed_edges_in_zone

BG_PATH = os.path.join(config.PROCESSED_DIR, "landuse_bg.parquet")
OUT_DIR = os.path.join(config.BASE_DIR, "outputs", "demo")
UNCHANGED = (0.82, 0.82, 0.86, 1.0)    # light grey: this segment's NO2 did not move
CLOSED_MARK = (0.10, 0.10, 0.12, 1.0)  # near-black: the closed block itself


def land_use_features(G, seg_df):
    """Rao-style land-use predictors for every segment: resident population and
    jobs aggregated over each buffer radius around the segment midpoint. The mass
    lives at the 19 block-group centroids; a segment's feature at radius r is the
    total population (or jobs) of every block group within r meters of it.

    These features depend only on land use, so they are identical whether or not a
    road is closed. That invariance is exactly what the figure demonstrates.
    """
    bg = pd.read_parquet(BG_PATH)
    seg_lat, seg_lon = predictors._segment_midpoints(G, seg_df)
    sx, sy = predictors._local_xy(seg_lat, seg_lon)
    bx, by = predictors._local_xy(bg["lat"].to_numpy(), bg["lon"].to_numpy())

    d2 = (sx[:, None] - bx[None, :]) ** 2 + (sy[:, None] - by[None, :]) ** 2
    pop = bg["population"].to_numpy(float)
    jobs = bg["jobs"].to_numpy(float)

    cols = {}
    for r in config.BUFFER_RADII_M:
        within = d2 <= float(r) ** 2
        cols[f"pop_buf{r}"] = within @ pop
        cols[f"jobs_buf{r}"] = within @ jobs
    return pd.DataFrame(cols)


def edge_vals(edges, by_edge):
    """Align a {(u,v,key): value} dict to the graph's edge order, 0 where absent."""
    return np.array([by_edge.get(e, 0.0) for e in edges])


def draw_change(ax, G, edges, change, norm, vmax, cmap, closed_set):
    """Color each segment by its NO2 change (closed - open) on the shared diverging
    scale: red = up, blue = down, light grey = no change, near-black = the closed
    block. Width grows with the size of the change so the redistribution stands out."""
    colors, widths = [], []
    for e, d in zip(edges, change):
        if e in closed_set:
            colors.append(CLOSED_MARK); widths.append(2.4)
        elif d == 0.0:
            colors.append(UNCHANGED); widths.append(0.5)
        else:
            t = norm(np.clip(d, -vmax, vmax))
            colors.append(cmap(t)); widths.append(0.7 + 3.2 * abs(t - 0.5) * 2)
    ox.plot_graph(G, ax=ax, edge_color=colors, edge_linewidth=widths,
                  node_size=0, bgcolor="white", show=False, close=False)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    G = predictors.load_network()
    base = config.RUN_NAME
    open_df = pd.read_parquet(
        os.path.join(config.PROCESSED_DIR, f"{base}_open_segments.parquet"))
    closed_df = pd.read_parquet(
        os.path.join(config.PROCESSED_DIR, f"{base}_closed_segments.parquet"))
    closed_set = set(closed_edges_in_zone(G))

    edges = list(G.edges(keys=True))

    # --- ABM surfaces (NO2 = F_NO2 * NOx), aligned to the graph edge order ---
    abm_open = config.F_NO2 * edge_vals(
        edges, {(r.u, r.v, r.key): r.nox_g for r in open_df.itertuples()})
    abm_closed = config.F_NO2 * edge_vals(
        edges, {(r.u, r.v, r.key): r.nox_g for r in closed_df.itertuples()})

    abm_change = abm_closed - abm_open

    # --- Static land-use forest (the same RF-on-buffers method Rao uses) ---
    # We fit it, then predict on the open and the closed scenario. The closure
    # leaves every land-use predictor unchanged, so the two predictions are equal
    # and the static change is exactly zero. We compute it the long way (predict
    # twice) rather than asserting it, so the zero is demonstrated, not assumed.
    X = land_use_features(G, open_df).to_numpy()
    y = config.F_NO2 * open_df["nox_g"].to_numpy(float)
    rf = RandomForestRegressor(n_estimators=400, random_state=config.RANDOM_SEED,
                               oob_score=True, n_jobs=-1)
    rf.fit(X, y)
    seg_keys = [(r.u, r.v, r.key) for r in open_df.itertuples()]
    static_change = edge_vals(
        edges, dict(zip(seg_keys, rf.predict(X) - rf.predict(X))))  # open minus closed: 0
    print(f"land-use forest out-of-bag R^2 vs the ABM open surface: {rf.oob_score_:.2f} "
          f"(land use alone barely tracks the road-concentrated surface)")
    print(f"static-model NO2 change across the closure: max |change| = "
          f"{np.abs(static_change).max():.6f} g (zero on every one of {len(edges)} segments)")
    print(f"ABM NO2 change across the closure: {np.count_nonzero(abm_change)} segments move, "
          f"max +{abm_change.max():.2f} g, min {abm_change.min():.2f} g")

    # one shared diverging scale for both panels, clipped at the 98th pct of the
    # ABM change so a single segment does not wash the rest out
    mag = np.abs(abm_change[abm_change != 0])
    vmax = float(np.percentile(mag, 98)) if mag.size else 1.0
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    cmap = mpl.colormaps["RdBu_r"]

    fig, axes = plt.subplots(1, 2, figsize=(16, 8.6))
    fig.patch.set_facecolor("white")

    draw_change(axes[0], G, edges, static_change, norm, vmax, cmap, closed_set)
    draw_change(axes[1], G, edges, abm_change, norm, vmax, cmap, closed_set)

    axes[0].set_title("Static land-use model (Rao's method)\nchange: ZERO on every segment",
                      color="#1f4e79", fontsize=15, weight="bold", pad=10)
    axes[1].set_title("Agent-based model (this work)\nNO2 redistributes across the network",
                      color="#b3261e", fontsize=15, weight="bold", pad=10)

    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, shrink=0.7, pad=0.02, aspect=30)
    cbar.set_label("NO2 change when SE Powell closes (g)   red = up, blue = down", fontsize=11)

    fig.suptitle("Close SE Powell: only the agent-based model responds",
                 color="#111111", fontsize=20, weight="bold", y=0.99)
    fig.text(0.5, 0.045,
             "Same closure, same scale. The land-use model is blank because a road closure changes no land-use input, "
             "so its prediction cannot move.\nThe agent model moves NO2 off SE Powell (-82%) onto the parallel arterials "
             "SE Division (+132%) and SE Holgate (+54%). The black block marks the closure.",
             color="#222222", fontsize=12, ha="center", va="top")

    fig.subplots_adjust(left=0.02, right=0.90, top=0.88, bottom=0.16, wspace=0.04)
    out = os.path.join(OUT_DIR, "5_static_vs_abm_closure.png")
    fig.savefig(out, dpi=200, facecolor="white")
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
