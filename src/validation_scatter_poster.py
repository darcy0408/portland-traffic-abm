"""Poster version of the traffic-count comparison scatter (light background).

Reads the SAVED matched-count table that validate_traffic.py wrote for a run
(<run>_count_validation.parquet: one row per matched segment, mean real ADT vs
model throughput) and draws rank(real) vs rank(model) with every matched
segment shown, both axes labeled, and two streets named: SE Powell Blvd (the
model's best agreement on the headline arterial) and the segment the model
over-rates most (SE Brooklyn St in the powell_through run). No simulation, no
fitting; same data and same Spearman as validate_traffic_map.py.

Usage:
    python src/validation_scatter_poster.py --run powell_through
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd

# config.py lives at the repo root; the sibling figure scripts do the same two appends
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402
from validate_traffic_map import _spearman, _edge_name, _short

POSTER_DIR = os.path.join(config.BASE_DIR, "outputs", "poster")
INK = "#1a1a1a"
DOT = "#4a6fa5"
HIT_COL = "#1f8f7a"
MISS_COL = "#b3261e"


def main(run_name):
    val_path = os.path.join(config.PROCESSED_DIR, f"{run_name}_count_validation.parquet")
    if not os.path.exists(val_path):
        raise SystemExit(f"No matched table at {val_path}")
    per_seg = pd.read_parquet(val_path)
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    edges = list(G.edges(keys=True))
    seg_to_edge = {i: edges[i] for i in per_seg["seg"].to_numpy()}

    ranks_real = per_seg["adt"].rank().to_numpy()
    ranks_model = per_seg["throughput"].rank().to_numpy()
    rho = _spearman(per_seg["adt"], per_seg["throughput"])
    n = len(per_seg)

    # the same two example segments validate_traffic_map picks, from the data
    segs = per_seg["seg"].to_numpy()
    names = np.array([_edge_name(G, seg_to_edge[s]) for s in segs], dtype=object)
    is_powell = np.array(["Powell" in nm for nm in names])
    hit_i = int(np.where(is_powell)[0][np.argmax(per_seg["adt"].to_numpy()[is_powell])])
    miss_i = int(np.argmax(ranks_model - ranks_real))

    fig, ax = plt.subplots(figsize=(9.0, 8.8), layout="constrained")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.scatter(ranks_real, ranks_model, s=44, c=DOT, alpha=0.75, edgecolors="none")
    lim = [-14, n + 15]
    ax.plot(lim, lim, ls="--", color="#888", lw=1.6)
    # Street labels sit in EMPTY regions of the plot (upper-left for Powell, lower-
    # right for Brooklyn) with a leader line to the ringed point, so the text never
    # covers plotted points. Positions are in rank units of this 356-segment plot.
    # Powell: the strip above the top row of points (y just under the axis limit).
    # Brooklyn: the empty upper-left corner. Both checked against the rendered plot.
    for i, col, xy_text, ha in [(hit_i, HIT_COL, (0.56 * n, n + 9), "left"),
                                (miss_i, MISS_COL, (0.03 * n, 0.92 * n), "left")]:
        ax.scatter([ranks_real[i]], [ranks_model[i]], s=420, facecolors="none",
                   edgecolors=col, linewidths=3.2, zorder=5, clip_on=False)
        ax.annotate(_short(names[i]), (ranks_real[i], ranks_model[i]),
                    xytext=xy_text, textcoords="data", ha=ha, va="center",
                    color=col, fontsize=27, weight="bold", zorder=6,
                    arrowprops=dict(arrowstyle="-", color=col, lw=1.8,
                                    shrinkA=2, shrinkB=10))
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("Rank: observed daily traffic (PBOT, county)",
                  fontsize=26, color=INK)
    ax.set_ylabel("Rank: modeled vehicles per segment, one hour",
                  fontsize=26, color=INK)
    ax.set_title(f"Spearman rank correlation {rho:.2f}, n = {n}\n"
                 "dashed line: equal ranks", fontsize=25,
                 color=INK, weight="bold", pad=12)
    ax.tick_params(labelsize=26, colors=INK)
    for s in ax.spines.values():
        s.set_color("#999")
    ax.grid(True, alpha=0.25)

    os.makedirs(POSTER_DIR, exist_ok=True)
    stem = os.path.join(POSTER_DIR, "validation_scatter_poster")
    # tight bbox so no label is cut off whatever the type size; the poster builder
    # reads the saved image's real aspect ratio
    fig.savefig(stem + ".pdf", facecolor="white", bbox_inches="tight", pad_inches=0.15)
    fig.savefig(stem + ".png", dpi=300, facecolor="white", bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print(f"Saved {stem}.pdf and {stem}.png")
    print(f"  n = {n}, Spearman rho = {rho:+.3f}; labeled: {names[hit_i]} / {names[miss_i]}")


if __name__ == "__main__":
    run = sys.argv[sys.argv.index("--run") + 1] if "--run" in sys.argv else config.RUN_NAME
    main(run)
