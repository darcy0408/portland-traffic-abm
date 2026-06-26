"""Draw the CNOSSOS road-traffic noise surface, the project's second output map.

Standalone companion to src/visualize.py: it reads the noise parquet that
src/noise.py wrote (data/processed/<run>_noise.parquet) plus the cached graph, and
renders one per-segment dB(A) map to config.FIGURES_DIR. It runs no simulation and
builds no surface itself; like visualize.py it only reads files and draws. Kept as
its own file (not a new mode in the shared visualize.py) so the concurrent demo
work is not disturbed.

The segment drawing mirrors visualize.py's _segment_heatmap (color and thicken
each edge by its value, dim grey for unused streets), with two deliberate changes
for noise:
  - decibels are already a logarithmic (compressed) scale, so we use a LINEAR
    color norm over the populated dB range, not the square-root PowerNorm the NO2
    grams map needs for its heavy skew, and
  - segments with no modeled flow have noise_db = NaN (silent) and are drawn dim
    grey, the same convention as an unused street on the NO2 map.

Run with:
    python src/visualize_noise.py            # uses config.RUN_NAME
    python src/visualize_noise.py <run_name> # any run that has a *_noise.parquet
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
import noise as noise_model   # for RECEIVER_DIST_M in the labels


def load_noise_surface(run_name):
    """Load the per-segment noise parquet src/noise.py produced for this run."""
    path = os.path.join(config.PROCESSED_DIR, f"{run_name}_noise.parquet")
    if not os.path.exists(path):
        raise SystemExit(f"No noise surface at {path}; build it first with "
                         f"python src/noise.py {run_name if run_name != config.RUN_NAME else ''}".rstrip())
    return pd.read_parquet(path)


def load_network():
    return ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))


def plot_noise_map(G, df, run_name):
    """Heat map of the modeled dB(A) road-traffic noise surface per segment.

    Loud arterials light up, quiet and unused streets stay dim grey. The color
    scale is linear in dB(A) (decibels are already logarithmic), spanning from the
    quiet end of the populated levels up to the loudest, so the busy corridors are
    clearly separated from the side streets.
    """
    noise_by_edge = {(r.u, r.v, r.key): r.noise_db for r in df.itertuples()}
    edges = list(G.edges(keys=True))
    vals = np.array([noise_by_edge.get(e, np.nan) for e in edges])

    lit = vals[np.isfinite(vals)]
    if lit.size == 0:
        raise SystemExit("No segment carries modeled noise; nothing to draw.")
    # linear dB scale; start a little below the quiet end so the lowest-noise
    # streets are still visible rather than pinned to black, and clip the very top
    # (98th percentile) so one or two segments do not stretch the whole ramp
    vmin = float(np.percentile(lit, 5))
    vmax = float(np.percentile(lit, 98))
    if vmax <= vmin:
        vmax = vmin + 1.0
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap = mpl.colormaps["magma"]

    colors, widths = [], []
    for v in vals:
        if not np.isfinite(v):
            colors.append((0.16, 0.16, 0.20, 1.0))   # dim grey: no modeled flow
            widths.append(0.4)
        else:
            t = norm(np.clip(v, vmin, vmax))
            colors.append(cmap(t))
            widths.append(0.6 + 3.0 * t)             # louder segment -> thicker line

    bg = "#0e0e12"
    fig, ax = ox.plot_graph(
        G, edge_color=colors, edge_linewidth=widths, node_size=0,
        bgcolor=bg, show=False, close=False,
    )

    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.01)
    cbar.set_label(f"road-traffic noise, dB(A) at {noise_model.RECEIVER_DIST_M:.0f} m receiver",
                   color="white")
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")
    ax.set_title("Powell ABM: modeled road-traffic noise surface (CNOSSOS-EU)\n"
                 "cars only, geometric divergence only, Leq-style for the simulated hour",
                 color="white")

    out = os.path.join(config.FIGURES_DIR, f"{run_name}_noise_map.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    print(f"Saved figure to {out}")


if __name__ == "__main__":
    run = sys.argv[1] if len(sys.argv) > 1 else config.RUN_NAME
    G = load_network()
    plot_noise_map(G, load_noise_surface(run), run)
