"""STAGE 2: VISUALIZE.

Reads the processed data file and produces figures. This script runs no
simulation. You can rerun it as often as you like, changing colors, axes, or
basemaps, without ever touching the expensive run that produced the data.

Run it with:  python src/visualize.py
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


def load_segments():
    path = os.path.join(config.PROCESSED_DIR, f"{config.RUN_NAME}_segments.parquet")
    return pd.read_parquet(path)


def load_network():
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    return ox.load_graphml(graph_file)


def plot_network(G):
    """Plain street-network map, no simulation data needed.
    Use this to confirm the study area looks right before running the sim."""
    fig, ax = ox.plot_graph(
        G,
        edge_color="#3a76c4",
        edge_linewidth=0.7,
        node_size=0,
        bgcolor="white",
        show=False,
        close=False,
    )
    out = os.path.join(config.FIGURES_DIR, "network_map.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved network map to {out}")


def plot_segment_map(G, df):
    """Heat map of simulated traffic activity per street segment.

    Each segment is colored and thickened by how much vehicle activity it carried.
    Busy corridors light up; unused streets stay a dim grey. The activity values
    are skewed (a few busy edges, many quiet ones), so we use a square-root color
    scale and clip the very top so one or two edges don't wash out the rest.
    """
    value_by_edge = {(r.u, r.v, r.key): r.value for r in df.itertuples()}
    edges = list(G.edges(keys=True))
    vals = np.array([value_by_edge.get(e, 0.0) for e in edges])

    positive = vals[vals > 0]
    vmax = float(np.percentile(positive, 98)) if positive.size else 1.0
    norm = mcolors.PowerNorm(gamma=0.5, vmin=0.0, vmax=vmax)   # sqrt-ish scale
    cmap = mpl.colormaps["inferno"]

    colors, widths = [], []
    for v in vals:
        if v <= 0:
            colors.append((0.16, 0.16, 0.20, 1.0))   # dim grey: street never used
            widths.append(0.4)
        else:
            t = norm(min(v, vmax))
            colors.append(cmap(t))
            widths.append(0.6 + 3.0 * t)             # busier segment -> thicker line

    bg = "#0e0e12"
    fig, ax = ox.plot_graph(
        G, edge_color=colors, edge_linewidth=widths, node_size=0,
        bgcolor=bg, show=False, close=False,
    )

    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.01)
    cbar.set_label("vehicle-seconds on segment", color="white")
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")
    ax.set_title(
        f"Powell ABM: traffic activity per segment\n"
        f"{config.N_VEHICLES} vehicles, {config.N_STEPS} steps",
        color="white",
    )

    out = os.path.join(config.FIGURES_DIR, f"{config.RUN_NAME}_segment_map.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    print(f"Saved figure to {out}")


if __name__ == "__main__":
    G = load_network()
    # `python src/visualize.py network` draws just the street network.
    # With no argument it draws the simulation segment map (needs sim output).
    if len(sys.argv) > 1 and sys.argv[1] == "network":
        plot_network(G)
    else:
        df = load_segments()
        plot_segment_map(G, df)
