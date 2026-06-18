"""STAGE 2: VISUALIZE.

Reads the processed data file and produces figures. This script runs no
simulation. You can rerun it as often as you like, changing colors, axes, or
basemaps, without ever touching the expensive run that produced the data.

Run it with:  python src/visualize.py
"""
import os
import sys

import pandas as pd
import osmnx as ox
import matplotlib.pyplot as plt

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def load_segments():
    path = os.path.join(config.PROCESSED_DIR, f"{config.RUN_NAME}_segments.parquet")
    return pd.read_parquet(path)


def load_network():
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    return ox.load_graphml(graph_file)


def plot_segment_map(G, df):
    """Color each street segment by its simulated value."""
    value_by_edge = {(r.u, r.v, r.key): r.value for r in df.itertuples()}
    edge_colors = [value_by_edge.get((u, v, k), 0.0) for u, v, k in G.edges(keys=True)]

    fig, ax = ox.plot_graph(
        G,
        edge_color=edge_colors,
        edge_linewidth=2,
        node_size=0,
        show=False,
        close=False,
    )
    out = os.path.join(config.FIGURES_DIR, f"{config.RUN_NAME}_segment_map.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved figure to {out}")


if __name__ == "__main__":
    G = load_network()
    df = load_segments()
    plot_segment_map(G, df)
