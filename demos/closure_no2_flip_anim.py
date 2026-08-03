"""CLOSURE NO2 FLIP for the Progress Update 2 closure slide (render-only demo).

The companion to closure_reroute_anim.py's car-dot flip: the same ~3 km window
around the SE Powell closure zone, showing the modeled NO2 surface alternating
between STREET OPEN and STREET CLOSED. Both end states are the real saved
surfaces of the mixed-fleet seed-42 metro closure run (the same run family the
slide's cited numbers come from); the crossfade between them is a display
device only, exactly like the committed noise_closure_flip.gif. No simulation
runs here.

Reads (never writes):
  - .claude/worktrees/metro5k-scaleup/data/processed/
        sweepmix_powell_42_open_segments.parquet
        sweepmix_powell_42_closed_segments.parquet
  - .claude/worktrees/metro5k-scaleup/data/network/graph.graphml
  - config.F_NO2, config.CLOSURE

Writes exactly one file: outputs/figures/closure_no2_flip.gif (gitignored).

Style matches demos/no2_reveal_anim.py (magma, log scale, #07111f background)
so the two NO2 visuals in the deck read as one family.
"""
import math
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
import matplotlib.animation as animation
from matplotlib.collections import LineCollection
from matplotlib.patches import Ellipse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

WORKTREE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".claude", "worktrees", "metro5k-scaleup",
)
if not os.path.isdir(WORKTREE):
    # Running from a sibling worktree (repo root is .claude/worktrees/<x>):
    # the metro caches live next door, not underneath us (Aug 3 fix).
    WORKTREE = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "metro5k-scaleup")
PROCESSED = os.path.join(WORKTREE, "data", "processed")
GRAPH_PATH = os.path.join(WORKTREE, "data", "network", "graph.graphml")
OPEN_PARQUET = os.path.join(PROCESSED, "sweepmix_powell_42_open_segments.parquet")
CLOSED_PARQUET = os.path.join(PROCESSED, "sweepmix_powell_42_closed_segments.parquet")
OUT_GIF = os.path.join(config.FIGURES_DIR, "closure_no2_flip.gif")

BG_COLOR = "#07111f"
CMAP_NAME = "magma"
VMIN = 1e-3

# Same window as closure_reroute_anim.py, so the two panels sit side by side
# on the slide showing the same piece of city.
CLAT, CLON, RADIUS_M = config.CLOSURE
HALF_LON, HALF_LAT = 0.0192, 0.0135

# Streets to label (matched against OSM edge names inside the window). The x
# placement is a fraction of the window width; y comes from the street's own
# edges' mean latitude near the window center.
LABEL_STREETS = ["Southeast Division Street",
                 "Southeast Powell Boulevard",
                 "Southeast Holgate Boulevard"]


def load():
    """Graph + the two per-segment NO2 arrays, subset to the zoom window."""
    t0 = time.time()
    G = ox.load_graphml(GRAPH_PATH)
    print(f"graph loaded: {G.number_of_edges()} edges ({time.time()-t0:.0f}s)")

    def no2_map(path):
        df = pd.read_parquet(path)
        return {(u, v, k): config.F_NO2 * n for u, v, k, n in
                zip(df["u"], df["v"], df["key"], df["nox_g"])}

    open_no2, closed_no2 = no2_map(OPEN_PARQUET), no2_map(CLOSED_PARQUET)

    lon0, lon1 = CLON - HALF_LON, CLON + HALF_LON
    lat0, lat1 = CLAT - HALF_LAT, CLAT + HALF_LAT
    node_xy = {n: (d["x"], d["y"]) for n, d in G.nodes(data=True)}

    segments, vo, vc = [], [], []
    label_lats = {name: [] for name in LABEL_STREETS}
    for u, v, k, data in G.edges(keys=True, data=True):
        x0, y0 = node_xy[u]
        x1, y1 = node_xy[v]
        if not (lon0 <= 0.5 * (x0 + x1) <= lon1 and lat0 <= 0.5 * (y0 + y1) <= lat1):
            continue
        geom = data.get("geometry")
        coords = np.asarray(geom.coords) if geom is not None else np.array([(x0, y0), (x1, y1)])
        segments.append(coords)
        vo.append(open_no2.get((u, v, k), 0.0))
        vc.append(closed_no2.get((u, v, k), 0.0))
        nm = data.get("name")
        names = [nm] if isinstance(nm, str) else (nm if isinstance(nm, list) else [])
        for name in LABEL_STREETS:
            # only central edges vote on the label latitude, so a curving
            # street far from the window center cannot drag its label away
            if name in names and abs(0.5 * (x0 + x1) - CLON) < HALF_LON * 0.4:
                label_lats[name].append(0.5 * (y0 + y1))
    print(f"window: {len(segments)} segments")
    return segments, np.array(vo), np.array(vc), label_lats


def colors_widths(vals, norm, cmap):
    colors = np.zeros((len(vals), 4))
    widths = np.full(len(vals), 0.5)
    pos = vals > 0
    t = norm(np.clip(vals[pos], VMIN, None))
    colors[pos] = cmap(t)
    widths[pos] = 0.6 + 3.2 * np.asarray(t)
    colors[~pos] = cmap(0.0)
    return colors, widths


def main():
    segments, vo, vc, label_lats = load()
    vmax = float(max(vo.max(), vc.max()))
    norm = mcolors.LogNorm(vmin=VMIN, vmax=vmax, clip=True)
    cmap = matplotlib.colormaps[CMAP_NAME]
    co, wo = colors_widths(vo, norm, cmap)
    cc, wc = colors_widths(vc, norm, cmap)

    # Full-bleed axes (Aug 3): the window is square by construction, so the
    # axes can fill the whole frame; the state label and caption draw inside
    # the map instead of in figure margin space. The slide's own title carries
    # the beat, so no area is spent on framing.
    fig, ax = plt.subplots(figsize=(5.6, 5.6), facecolor=BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.set_xlim(CLON - HALF_LON, CLON + HALF_LON)
    ax.set_ylim(CLAT - HALF_LAT, CLAT + HALF_LAT)
    ax.set_aspect(1.0 / math.cos(math.radians(CLAT)))
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)

    lc = LineCollection(segments, colors=co, linewidths=wo, zorder=2)
    ax.add_collection(lc)

    # closure-zone ring: 150 m radius converted per-axis (longitude degrees are
    # foreshortened by cos(lat)), so it displays as a true circle under the
    # map's aspect correction instead of a squashed ellipse
    ring = Ellipse((CLON, CLAT),
                   width=2 * RADIUS_M / (111320.0 * math.cos(math.radians(CLAT))),
                   height=2 * RADIUS_M / 111320.0, fill=False,
                   linestyle="--", linewidth=1.8, edgecolor="#16d6c1", zorder=5)
    ax.add_patch(ring)

    # street-name labels on the right edge, at each street's own latitude
    for name in LABEL_STREETS:
        if not label_lats[name]:
            continue
        short = name.replace("Southeast ", "SE ").replace(" Boulevard", "").replace(" Street", "")
        ax.text(CLON + HALF_LON * 0.96, float(np.median(label_lats[name])), short,
                color="#e6edf3", fontsize=9, fontweight="bold",
                ha="right", va="center", zorder=6,
                bbox=dict(facecolor=BG_COLOR, edgecolor="none", alpha=0.75, pad=1.5))

    # The OPEN/CLOSED state label is functional (it is what flips), so it stays,
    # as an in-map overlay on a dark backing box rather than a title band.
    state = ax.text(0.5, 0.978, "NO₂ surface  |  street OPEN",
                    transform=ax.transAxes, color="#e6edf3", fontsize=13,
                    ha="center", va="top", zorder=7,
                    bbox=dict(facecolor=BG_COLOR, edgecolor="none",
                              alpha=0.8, pad=2.5))
    ax.text(0.5, 0.012, "modeled NO₂ per segment (log color scale) "
            "· dashed ring = closure zone",
            transform=ax.transAxes, color="#9da7b3", fontsize=8.5,
            ha="center", va="bottom", zorder=7,
            bbox=dict(facecolor=BG_COLOR, edgecolor="none", alpha=0.8, pad=1.5))

    # frame plan at 6 fps: open hold, fade, closed hold, fade back = 6 s loop
    HOLD, FADE = 12, 6
    total = HOLD + FADE + HOLD + FADE

    def update(i):
        if i < HOLD:                       # open
            a = 0.0
        elif i < HOLD + FADE:              # fading to closed
            a = (i - HOLD + 1) / FADE
        elif i < HOLD + FADE + HOLD:       # closed
            a = 1.0
        else:                              # fading back to open
            a = 1.0 - (i - HOLD - FADE - HOLD + 1) / FADE
        lc.set_color((1 - a) * co + a * cc)
        lc.set_linewidths((1 - a) * wo + a * wc)
        if a < 0.5:
            state.set_text("NO₂ surface  |  street OPEN")
            ring.set_edgecolor("#16d6c1")
        else:
            state.set_text("NO₂ surface  |  street CLOSED")
            ring.set_edgecolor("#e74c3c")
        return (lc, ring, state)

    anim = animation.FuncAnimation(fig, update, frames=total, blit=False)
    t0 = time.time()
    anim.save(OUT_GIF, writer=animation.PillowWriter(fps=6), dpi=170,
              savefig_kwargs={"facecolor": BG_COLOR})
    plt.close(fig)
    print(f"wrote {OUT_GIF} ({os.path.getsize(OUT_GIF)/1e6:.1f} MB, "
          f"{total} frames, {time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
