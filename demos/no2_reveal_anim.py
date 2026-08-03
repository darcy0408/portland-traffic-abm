"""RENDER-ONLY DEMO: animated "reveal" of the full-metro NO2 surface.

Reads (never writes, never simulates):
  - segments:  .claude/worktrees/metro5k-scaleup/data/processed/metro20k_mixed_segments.parquet
               (columns u, v, key, value, nox_g, throughput -- the mixed-fleet
               full-metro run's saved per-segment results)
  - graph:     .claude/worktrees/metro5k-scaleup/data/network/graph.graphml
               (~62k nodes / 159k edges, epsg:4326)

Both paths point into the metro5k-scaleup worktree because that is where the
metro-scale run that produced outputs/figures/metro20k_mixed_no2_map.png lives.
This script does not modify anything in that worktree; it only reads the two
files above.

Writes exactly one file: outputs/figures/metro20k_no2_reveal.gif (gitignored).

What this is: the static map outputs/figures/metro20k_mixed_no2_map.png colors
every street segment by its modeled NO2 (config.F_NO2 * nox_g, log color
scale). This script draws the SAME segments, in the SAME final coloring, but
reveals them progressively from dimmest to brightest NO2 across ~35 frames,
then holds on the completed map. The reveal order is a rendering device only
-- it does not represent time evolution or a simulated rush hour, and the
slide caption says so explicitly.

Performance note: with 159,410 segments, the segment geometry is built into
ONE matplotlib LineCollection up front. Each animation frame only mutates
that collection's per-segment RGBA colors (an O(N) numpy assignment); no
artist is ever re-created or re-added, which is what makes ~55 frames of a
159k-segment network affordable to render.
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
import matplotlib.patches as mpatches
import matplotlib.animation as animation

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # repo-root config: only used here for F_NO2, FIGURES_DIR, STUDY_CENTER

# --- Read-only inputs (metro5k-scaleup worktree; do not write here) ---
WORKTREE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".claude", "worktrees", "metro5k-scaleup",
)
if not os.path.isdir(WORKTREE):
    # Running from a sibling worktree (repo root is .claude/worktrees/<x>):
    # the metro caches live next door, not underneath us (Aug 3 fix).
    WORKTREE = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "metro5k-scaleup")
SEGMENTS_PATH = os.path.join(WORKTREE, "data", "processed", "metro20k_mixed_segments.parquet")
GRAPH_PATH = os.path.join(WORKTREE, "data", "network", "graph.graphml")

# --- Output ---
OUT_GIF = os.path.join(config.FIGURES_DIR, "metro20k_no2_reveal.gif")

# --- Style constants, reverse-engineered from the committed static PNG ---
# (outputs/figures/metro20k_mixed_no2_map.png does not match src/visualize.py's
# generic viridis/PowerNorm _segment_heatmap style -- it was made by a one-off
# scratchpad script, per SESSION_NOTES.md, with its own magma/log-scale look.
# These constants were read off the actual PNG pixels: background sampled at
# RGB(7,17,31) = #07111f, colorbar is a log scale, colormap reads as magma.)
BG_COLOR = "#07111f"
CMAP_NAME = "magma"
VMIN = 1e-3     # clip floor for the log color scale (round number, matches the
                 # "10^-3" tick sitting at the bottom of the static map's colorbar)

# Old Update-1 study area, for the same dashed-box annotation the static map
# carries. Center point is unchanged between the 1.5 km Powell baseline and the
# current 20 km metro run (see config.py's STUDY_CENTER history comment); only
# the radius grew. 1500 m is the "committed baseline" radius noted there.
OLD_STUDY_RADIUS_M = 1500


def load_data():
    """Load the segments table and graph; return arrays aligned edge-by-edge."""
    df = pd.read_parquet(SEGMENTS_PATH)
    nox_by_edge = {(u, v, k): n for u, v, k, n in
                   zip(df["u"], df["v"], df["key"], df["nox_g"])}

    t0 = time.time()
    G = ox.load_graphml(GRAPH_PATH)
    print(f"Loaded graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges "
          f"({time.time()-t0:.1f}s)")

    node_xy = {n: (d["x"], d["y"]) for n, d in G.nodes(data=True)}

    segments = []
    vals = np.empty(G.number_of_edges(), dtype=float)
    xmin = ymin = np.inf
    xmax = ymax = -np.inf
    for i, (u, v, k, data) in enumerate(G.edges(keys=True, data=True)):
        geom = data.get("geometry")
        if geom is not None:
            coords = np.asarray(geom.coords)
        else:
            coords = np.array([node_xy[u], node_xy[v]])
        segments.append(coords)
        xmin = min(xmin, coords[:, 0].min()); xmax = max(xmax, coords[:, 0].max())
        ymin = min(ymin, coords[:, 1].min()); ymax = max(ymax, coords[:, 1].max())
        vals[i] = config.F_NO2 * nox_by_edge.get((u, v, k), 0.0)

    bounds = (xmin, ymin, xmax, ymax)
    return G, segments, vals, bounds


def build_final_colors_widths(vals):
    """Reproduce the static map's per-segment color/width, exactly as saved.

    Positive NO2 -> magma, log-normalized (clip floor VMIN, ceiling = data max,
    matching the static PNG's colorbar range). Zero/unused segments -> a color
    indistinguishable from background (they read as gaps in the static map).
    """
    positive = vals > 0
    vmax = float(vals.max())
    norm = mcolors.LogNorm(vmin=VMIN, vmax=vmax, clip=True)
    cmap = matplotlib.colormaps[CMAP_NAME]

    colors = np.zeros((len(vals), 4))
    widths = np.full(len(vals), 0.3)

    t = norm(np.clip(vals[positive], VMIN, vmax))
    colors[positive] = cmap(t)
    widths[positive] = 0.35 + 2.3 * t

    # unused segments: darkest magma value, same as the map's near-invisible gaps
    colors[~positive] = cmap(0.0)

    return colors, widths, norm, cmap


def reveal_order(vals):
    """Ascending-NO2 order to reveal the POSITIVE-valued segments in, dimmest
    first. Zero-value ("never used") segments are deliberately excluded here:
    they are all tied at exactly 0, so an argsort over the full array would
    give them an arbitrary (and visually clustered, not network-wide) relative
    order. Instead they are treated as an always-on base layer (see main()),
    which reads as the full street skeleton appearing at once, faint, with
    colored segments lighting up on top of it in true brightness order."""
    positive_idx = np.flatnonzero(vals > 0)
    order_within_positive = np.argsort(vals[positive_idx], kind="stable")
    return positive_idx[order_within_positive]


def study_area_box(lat0, lon0, radius_m):
    """Old Update-1 study-area bounding box in (lon, lat), matching the
    dashed-box annotation on the static map."""
    dlat = radius_m / 111320.0
    dlon = radius_m / (111320.0 * np.cos(np.radians(lat0)))
    return lon0 - dlon, lat0 - dlat, lon0 + dlon, lat0 + dlat


def main():
    G, segments, vals, bounds = load_data()
    colors_final, widths, norm, cmap = build_final_colors_widths(vals)
    base_mask = vals <= 0            # always-on, never-used street skeleton
    order = reveal_order(vals)        # positive segments only, ascending

    n_reveal = 35
    n_hold = 20
    fps = 6          # half the earlier 12 fps -> the reveal plays ~2x slower
    chunks = np.array_split(order, n_reveal)

    xmin, ymin, xmax, ymax = bounds
    pad_x = (xmax - xmin) * 0.02
    pad_y = (ymax - ymin) * 0.02
    cos_lat = np.cos(np.deg2rad((ymin + ymax) / 2))

    # Full-bleed axes (Aug 3): the metro extent is square after the aspect
    # correction, so the axes fill the whole frame and the colorbar becomes an
    # inset inside the map's sparse right edge instead of stealing figure width.
    fig, ax = plt.subplots(figsize=(5.6, 5.6), facecolor=BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_xlim(xmin - pad_x, xmax + pad_x)
    ax.set_ylim(ymin - pad_y, ymax + pad_y)
    ax.set_aspect(1 / cos_lat)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    from matplotlib.collections import LineCollection
    # start fully transparent -- "light up from nothing"
    start_colors = colors_final.copy()
    start_colors[:, 3] = 0.0
    lc = LineCollection(segments, colors=start_colors, linewidths=widths, zorder=2)
    ax.add_collection(lc)

    # colorbar, matching the static map's log-scale NO2 label; drawn as an
    # inset over the map's sparse right edge so the map keeps the full frame
    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    # dark backing panel so the bar, ticks and label stay readable over the
    # bright arterials at the map's right edge (drawn in ax, below the inset)
    # zorder 4: above the street LineCollection (2) but below the inset axes
    # (child axes draw at zorder 5; a higher rect would cover the bar itself)
    ax.add_patch(mpatches.Rectangle(
        (0.86, 0.185), 0.14, 0.635, transform=ax.transAxes,
        facecolor=BG_COLOR, edgecolor="none", alpha=0.85, zorder=4))
    cax = ax.inset_axes([0.955, 0.22, 0.022, 0.56])
    cbar = fig.colorbar(sm, cax=cax)
    # ticks and label on the LEFT of the bar, reaching into the map, so nothing
    # clips off the frame's right edge
    cbar.ax.yaxis.set_ticks_position("left")
    cbar.ax.yaxis.set_label_position("left")
    cbar.set_label("modeled NO2 per segment (g, log scale)",
                   color="white", fontsize=8)
    cbar.ax.yaxis.set_tick_params(color="white", labelsize=7)
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")
    cbar.outline.set_visible(False)

    # Update-1 study-area annotation, same as the static map
    lat0, lon0 = config.STUDY_CENTER
    bx0, by0, bx1, by1 = study_area_box(lat0, lon0, OLD_STUDY_RADIUS_M)
    box = mpatches.Rectangle(
        (bx0, by0), bx1 - bx0, by1 - by0,
        linestyle="--", edgecolor="#16d6c1", facecolor="none",
        linewidth=1.6, zorder=5, alpha=0.0,  # faded in only once revealed (see update())
    )
    ax.add_patch(box)
    text_x, text_y = bx1 + (xmax - xmin) * 0.03, by0 - (ymax - ymin) * 0.10
    callout_line, = ax.plot([bx1, text_x], [by0, text_y], color="#16d6c1",
                             linewidth=1.0, zorder=5, alpha=0.0)
    callout_text = ax.text(
        text_x, text_y, "Update 1's whole\nstudy area",
        color="#16d6c1", fontsize=8, fontweight="bold", zorder=5, alpha=0.0,
        va="top",
    )

    # Lead with ~1 s of the COMPLETE map before the reveal: the GIF's first
    # frame is what PDF exports and non-animating renderers show, and a
    # near-empty dim map there reads as a broken slide. In looping playback
    # (full -> dim -> build -> full -> ...) the lead is indistinguishable
    # from the trailing hold.
    n_lead = 12
    n_frames = n_lead + n_reveal + n_hold

    def update(lead_i):
        if lead_i < n_lead:
            lc.set_color(colors_final)
            box.set_alpha(1.0)
            callout_line.set_alpha(1.0)
            callout_text.set_alpha(1.0)
            return lc, box, callout_line, callout_text
        frame_i = lead_i - n_lead
        if frame_i < n_reveal:
            revealed = base_mask.copy()   # the never-used skeleton is always on
            for c in chunks[: frame_i + 1]:
                revealed[c] = True
            frame_colors = colors_final.copy()
            frame_colors[~revealed, 3] = 0.0
            lc.set_color(frame_colors)
            # fade the annotation in over the last third of the reveal
            ann_alpha = np.clip((frame_i - n_reveal * 0.66) / (n_reveal * 0.34), 0, 1)
        else:
            lc.set_color(colors_final)
            ann_alpha = 1.0
        box.set_alpha(ann_alpha)
        callout_line.set_alpha(ann_alpha)
        callout_text.set_alpha(ann_alpha)
        return lc, box, callout_line, callout_text

    anim = animation.FuncAnimation(fig, update, frames=n_frames, blit=False)

    t0 = time.time()
    anim.save(OUT_GIF, writer=animation.PillowWriter(fps=fps), dpi=170,
              savefig_kwargs={"facecolor": BG_COLOR})
    print(f"Saved {OUT_GIF} in {time.time()-t0:.1f}s "
          f"({n_frames} update() calls -> fewer stored GIF frames, since Pillow "
          f"merges byte-identical consecutive frames -- e.g. the hold -- into "
          f"one frame with accumulated duration; total playback time is "
          f"preserved, {fps} fps)")
    plt.close(fig)

    size_mb = os.path.getsize(OUT_GIF) / 1e6
    print(f"GIF size: {size_mb:.2f} MB, frames: {n_frames}")


if __name__ == "__main__":
    main()
