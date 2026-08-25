"""Camera-ready variant of the static-vs-ABM closure figure (SRC Figure 1).

Advisor-requested rework for the SIGSPATIAL SRC camera-ready (Aug 25, 2026):
the figure prints at one column width (~3.3 in), so the in-figure suptitle and
footer text move into the LaTeX caption, and every label that remains is sized
to stay readable after the shrink. The blue/red panel headers stay, which the
advisor explicitly allowed ("You can leave the blue and red text").

Reads the same saved powell_through closure run every abstract number traces
to; runs NO simulation. The run name is pinned here rather than taken from
config, because config has since moved to the metro-scale defaults and this
figure must keep reproducing the committed paper numbers.

Run:  python src/static_vs_abm_camera.py
"""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import predictors
from generate import closed_edges_in_zone
from static_vs_abm import edge_vals, draw_change

RUN = "powell_through"       # pinned: the run the SRC abstract cites
OUT_DIR = os.path.join(config.BASE_DIR, "outputs", "demo")


def arterial_pct(G, edges, abm_open, abm_closed, target):
    """Percent NO2 change on one named arterial, computed from the data so the
    printed check below can be compared against the caption's cited numbers."""
    def _street(d):
        n = d.get("name")
        return "" if n is None else (str(n[0]) if isinstance(n, list) else str(n))
    name_by_edge = {(u, v, k): _street(d) for u, v, k, d in G.edges(keys=True, data=True)}
    o = c = 0.0
    for e, ov, cv in zip(edges, abm_open, abm_closed):
        if target.lower() in name_by_edge.get(e, "").lower():
            o += ov; c += cv
    return 100 * (c - o) / o if o > 0 else float("nan")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    G = predictors.load_network()
    if G.number_of_nodes() != 978:
        raise SystemExit(f"expected the 1.5 km Powell graph (978 nodes), "
                         f"got {G.number_of_nodes()}: wrong network cache")

    open_df = pd.read_parquet(
        os.path.join(config.PROCESSED_DIR, f"{RUN}_open_segments.parquet"))
    closed_df = pd.read_parquet(
        os.path.join(config.PROCESSED_DIR, f"{RUN}_closed_segments.parquet"))
    closed_set = set(closed_edges_in_zone(G))
    edges = list(G.edges(keys=True))

    abm_open = config.F_NO2 * edge_vals(
        edges, {(r.u, r.v, r.key): r.nox_g for r in open_df.itertuples()})
    abm_closed = config.F_NO2 * edge_vals(
        edges, {(r.u, r.v, r.key): r.nox_g for r in closed_df.itertuples()})
    abm_change = abm_closed - abm_open
    static_change = np.zeros(len(edges))   # a closure changes no land-use input

    for street in ("Powell", "Division", "Holgate"):
        print(f"{street}: {arterial_pct(G, edges, abm_open, abm_closed, street):+.1f}% "
              "(check against the caption)")

    # one shared diverging scale, clipped at the 98th pct of the ABM change
    mag = np.abs(abm_change[abm_change != 0])
    vmax = float(np.percentile(mag, 98)) if mag.size else 1.0
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    cmap = mpl.colormaps["RdBu_r"]

    # Built at ~2.1x print size: at \columnwidth (3.335 in) a 17 pt header
    # prints at ~8 pt, on par with the caption text, which answers the
    # "fonts are too small" note. Colorbar goes horizontal so the two map
    # panels get the full column width.
    # constrained_layout places the horizontal colorbar below the panels
    # without the two overlapping (a manual subplots_adjust after colorbar()
    # re-expands the axes over the bar)
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.55), layout="constrained")
    fig.patch.set_facecolor("white")
    draw_change(axes[0], G, edges, static_change, norm, vmax, cmap, closed_set)
    draw_change(axes[1], G, edges, abm_change, norm, vmax, cmap, closed_set)

    axes[0].set_title("Static land-use model\nchange: zero everywhere",
                      color="#1f4e79", fontsize=17, weight="bold", pad=6)
    axes[1].set_title("Agent-based model\nNO$_2$ redistributes",
                      color="#b3261e", fontsize=17, weight="bold", pad=6)

    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, location="bottom", shrink=0.92,
                        pad=0.02, aspect=35)
    cbar.set_label("NO$_2$ change (g)", fontsize=16)
    cbar.ax.tick_params(labelsize=15)

    out = os.path.join(OUT_DIR, "static_vs_abm_camera.png")
    fig.savefig(out, dpi=350, facecolor="white")
    plt.close(fig)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
