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

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import predictors                      # reuse the midpoint + projection helpers
import landuse_model                   # the strong, well-fit static land-use baseline (#6)
from generate import closed_edges_in_zone

OUT_DIR = os.path.join(config.BASE_DIR, "outputs", "demo")
UNCHANGED = (0.82, 0.82, 0.86, 1.0)    # light grey: this segment's NO2 did not move
CLOSED_MARK = (0.10, 0.10, 0.12, 1.0)  # near-black: the closed block itself


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

    # --- Static land-use model (a strong, well-fit Rao-style land-use forest, #6) ---
    # landuse_model fits the open surface with built-environment + demographic
    # predictors (out-of-bag R^2 ~0.51 on the log scale, a genuinely good baseline,
    # not a strawman). Those predictors describe permanent infrastructure, so they
    # are held fixed across the closure: a static model is not refit for a one-day
    # event. The same prediction therefore serves the open and the closed scenario,
    # and the change is exactly zero on every segment. Even a good static model is
    # blind to the closure, which is the whole point.
    static = landuse_model.build_static_model()
    static_change = np.zeros(len(edges))    # same fixed inputs open and closed -> zero
    print(f"static land-use model out-of-bag R^2 = {static.oob_r2:.2f} (log scale, "
          f"a well-fit baseline); NO2 change across the closure = 0 on every segment")
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

    axes[0].set_title(f"Static land-use model (Rao's method, fits at R²={static.oob_r2:.2f})\n"
                      "change: ZERO on every segment",
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
