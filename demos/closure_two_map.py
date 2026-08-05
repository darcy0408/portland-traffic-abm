"""RENDER-ONLY DEMO: matched pair of metro-scale closure maps for the progress
slide (Progress Update 2). Reproduces PU1's side-by-side device --
    "Static land-use model: zero change"   vs.   "Agent-based model: NO2 moves"
at full metro scale instead of the old 1.5 km Powell corridor.

Reads (never writes, never simulates):
  - segments: .claude/worktrees/metro5k-scaleup/data/processed/
              metro20k_open_segments.parquet, metro20k_closed_segments.parquet
              (columns u, v, key, value, nox_g, throughput; NO2 = config.F_NO2 * nox_g)
  - graph:    .claude/worktrees/metro5k-scaleup/data/network/graph.graphml
              (~85 MB, 159,410 edges; loaded once and shared by both panels)
  - config.CLOSURE / config.F_NO2 (already set to the metro20k closure zone/run
    in this repo's config.py) and generate.closed_edges_in_zone(), so the
    "what counts as closed" logic is identical to src/visualize.py's
    plot_closure_diff -- this script adapts that exact method to the metro
    graph + parquets rather than re-deriving it.

Writes exactly two files, both gitignored:
  outputs/figures/metro_closure_static.png  -- panel 1: uniform grey, no diff
                                               coloring at all (the static
                                               land-use surface cannot move)
  outputs/figures/metro_closure_diff.png    -- panel 2: red/blue NO2 diff,
                                               closed segments outlined bright

The two panels share the exact same map extent (bounds computed once from the
graph) and background (#07111f, the deck's dark background) so they read as a
matched pair when placed side by side.

Style note: 159k edges is too many to build per-edge as a Python list passed
to ox.plot_graph (slow); instead this follows demos/no2_reveal_anim.py's
precedent of building ONE matplotlib LineCollection from the edge geometries
and setting per-segment colors as a numpy array, which is fast enough to
render this graph interactively.
"""
import os
import sys
import time

import numpy as np
import pandas as pd
import osmnx as ox
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import config          # repo-root config: F_NO2, CLOSURE, FIGURES_DIR
import generate         # closed_edges_in_zone(), so we agree with visualize.py on what's closed

# --- Read-only inputs (metro5k-scaleup worktree; never write here) ---
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE = os.path.join(REPO_ROOT, ".claude", "worktrees", "metro5k-scaleup")
OPEN_PATH = os.path.join(WORKTREE, "data", "processed", "metro20k_open_segments.parquet")
CLOSED_PATH = os.path.join(WORKTREE, "data", "processed", "metro20k_closed_segments.parquet")
GRAPH_PATH = os.path.join(WORKTREE, "data", "network", "graph.graphml")

# --- Outputs ---
OUT_STATIC = os.path.join(config.FIGURES_DIR, "metro_closure_static.png")
OUT_DIFF = os.path.join(config.FIGURES_DIR, "metro_closure_diff.png")

# --- Shared style ---
BG_COLOR = "#07111f"          # matches the deck background
STATIC_GREY = "#d1d5db"       # panel 1: the ONE color, everywhere, low alpha
STATIC_ALPHA = 0.38
CLOSED_OUTLINE_GREY = "#9ca3af"   # panel 1's faint reference outline (not color-coded)
UNCHANGED_GREY = (0.16, 0.16, 0.20, 1.0)   # panel 2: dim grey for zero-diff segments
CLOSED_YELLOW = (1.0, 0.95, 0.3, 1.0)      # panel 2: bright outline for the closed set
FIGSIZE = (5.5, 5.5)
DPI = 180


def load_graph_geometry():
    """Load the metro graph once and build the LineCollection segment coordinates
    and the shared data-space bounds both panels will use."""
    t0 = time.time()
    G = ox.load_graphml(GRAPH_PATH)
    print(f"Loaded graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges "
          f"({time.time() - t0:.1f}s)")

    node_xy = {n: (d["x"], d["y"]) for n, d in G.nodes(data=True)}
    edges = list(G.edges(keys=True))

    segments = []
    xmin = ymin = np.inf
    xmax = ymax = -np.inf
    for u, v, k, data in G.edges(keys=True, data=True):
        geom = data.get("geometry")
        if geom is not None:
            coords = np.asarray(geom.coords)
        else:
            coords = np.array([node_xy[u], node_xy[v]])
        segments.append(coords)
        xmin = min(xmin, coords[:, 0].min()); xmax = max(xmax, coords[:, 0].max())
        ymin = min(ymin, coords[:, 1].min()); ymax = max(ymax, coords[:, 1].max())

    bounds = (xmin, ymin, xmax, ymax)
    return G, edges, segments, bounds


def load_diffs(G, edges):
    """NO2 change per segment (closed - open), config.F_NO2-scaled, aligned to
    `edges`. Same computation as src/visualize.py's plot_closure_diff, adapted
    to read the metro parquets instead of the corridor's."""
    open_df = pd.read_parquet(OPEN_PATH)
    closed_df = pd.read_parquet(CLOSED_PATH)
    open_nox = {(r.u, r.v, r.key): r.nox_g for r in open_df.itertuples()}
    closed_nox = {(r.u, r.v, r.key): r.nox_g for r in closed_df.itertuples()}
    diffs = np.array([config.F_NO2 * (closed_nox.get(e, 0.0) - open_nox.get(e, 0.0))
                      for e in edges])
    return diffs


def setup_axes(ax, bounds):
    """Apply the shared extent/aspect so both panels crop to the identical
    map area -- this is what lets a viewer's eye map one panel onto the other."""
    xmin, ymin, xmax, ymax = bounds
    pad_x = (xmax - xmin) * 0.02
    pad_y = (ymax - ymin) * 0.02
    cos_lat = np.cos(np.deg2rad((ymin + ymax) / 2))
    ax.set_xlim(xmin - pad_x, xmax + pad_x)
    ax.set_ylim(ymin - pad_y, ymax + pad_y)
    ax.set_aspect(1 / cos_lat)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def render_static(segments, bounds, closed_set, edges):
    """Panel 1: 'the static land-use model does not move.' Every segment gets
    the SAME flat grey at the SAME low alpha -- no value drives color or width
    anywhere. The only concession to orientation is a faint (still grey, not
    color-coded) outline of the closed Powell stretch, so a viewer can find the
    same spot in panel 2."""
    fig, ax = plt.subplots(figsize=FIGSIZE, facecolor=BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    rgba = mcolors.to_rgba(STATIC_GREY, alpha=STATIC_ALPHA)
    colors = np.tile(rgba, (len(segments), 1))
    widths = np.full(len(segments), 0.55)

    lc = LineCollection(segments, colors=colors, linewidths=widths, zorder=2)
    ax.add_collection(lc)

    # faint reference outline of the closed segments -- same grey family, just
    # slightly brighter/thicker, so it reads as "here is the zone" and nothing more
    closed_idx = [i for i, e in enumerate(edges) if e in closed_set]
    if closed_idx:
        closed_segs = [segments[i] for i in closed_idx]
        lc_ref = LineCollection(
            closed_segs,
            colors=[mcolors.to_rgba(CLOSED_OUTLINE_GREY, alpha=0.55)] * len(closed_segs),
            linewidths=1.8, zorder=3,
        )
        ax.add_collection(lc_ref)

    setup_axes(ax, bounds)
    ax.set_title("Static land-use model: zero change", color="white", fontsize=11)

    fig.savefig(OUT_STATIC, dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    print(f"Saved {OUT_STATIC}")


def render_diff(segments, bounds, diffs, closed_set, edges):
    """Panel 2: the metro analog of plot_closure_diff -- red where NO2 rose
    (traffic diverted here), blue where it fell, closed segments outlined
    bright yellow, symmetric diverging scale clipped at the 98th percentile of
    the nonzero changes so a few huge movers don't wash out the rest."""
    mag = np.abs(diffs[diffs != 0])
    vmax = float(np.percentile(mag, 98)) if mag.size else 1.0
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    cmap = matplotlib.colormaps["RdBu_r"]

    # DEVIATION from src/visualize.py's plot_closure_diff, noted in the report:
    # that function treats exactly-zero diffs as "unchanged grey" and colors
    # every other segment by cmap(norm(d)). At corridor scale that is fine --
    # almost every far-away segment truly never changes (nox_open == nox_closed
    # == 0 on both runs). At metro scale, with real LODES OD demand, tens of
    # thousands of segments carry a nonzero-but-tiny routing-noise diff (median
    # nonzero |diff| ~0.004 g against a 98th-percentile vmax ~0.89 g). RdBu_r
    # maps near-zero to near-white, so coloring all of those literally-nonzero
    # segments washes the whole metro in faint white lines and drowns the real
    # near-zone signal. Fix: treat |diff| below a noise floor (5% of vmax) the
    # same as exactly-zero -- dim grey, not white -- so only meaningful change
    # carries color. This does not change vmax/the color scale itself, only
    # which segments are considered "changed" for rendering purposes.
    noise_floor = 0.05 * vmax

    colors = np.empty((len(edges), 4))
    widths = np.empty(len(edges))
    for i, (e, d) in enumerate(zip(edges, diffs)):
        if e in closed_set:
            colors[i] = CLOSED_YELLOW
            widths[i] = 2.6
        elif abs(d) < noise_floor:
            colors[i] = UNCHANGED_GREY
            widths[i] = 0.4
        else:
            dc = np.clip(d, -vmax, vmax)
            colors[i] = cmap(norm(dc))
            widths[i] = 0.6 + 3.0 * abs(norm(dc) - 0.5) * 2

    fig, ax = plt.subplots(figsize=FIGSIZE, facecolor=BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    lc = LineCollection(segments, colors=colors, linewidths=widths, zorder=2)
    ax.add_collection(lc)
    setup_axes(ax, bounds)

    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.01)
    # short label -- the long "red = up, blue = down" suffix truncated at the
    # figure edge; the slide caption carries the direction reading instead
    cbar.set_label("NO₂ change when SE Powell closes (g)", color="white")
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")
    ax.set_title("Agent-based model: NO₂ moves", color="white", fontsize=11)

    fig.savefig(OUT_DIFF, dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
    print(f"Saved {OUT_DIFF}")


def main():
    G, edges, segments, bounds = load_graph_geometry()
    diffs = load_diffs(G, edges)
    closed_set = set(generate.closed_edges_in_zone(G))
    print(f"Closed set: {len(closed_set)} segments (config.CLOSURE = {config.CLOSURE})")

    render_static(segments, bounds, closed_set, edges)
    render_diff(segments, bounds, diffs, closed_set, edges)

    for path in (OUT_STATIC, OUT_DIFF):
        size_kb = os.path.getsize(path) / 1024
        print(f"{path}: {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
