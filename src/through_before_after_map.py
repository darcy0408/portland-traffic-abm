"""Through-traffic BEFORE/AFTER figure (Jul 1).

Shows, on the same matched segments, the real city counts next to the model WITHOUT
and WITH regional through-traffic, all colored by rank. The point the eye should
catch: adding through-traffic moves the model map closer to the real map, brightening
the arterials and dimming the side-street shortcuts (SE 26th) the router over-used.

Three panels, all rank-colored (dark = quiet, bright = busy):
  left   : REAL PBOT/county ADT
  middle : MODEL throughput, local trips only (baseline, run 'powell_no2')
  right  : MODEL throughput, + 30% through-traffic (run 'powell_through')

SE Powell (the headline arterial) and SE 26th (the baseline's worst over-rate) are
ringed on all three, so one street can be traced across them. Reads saved files only,
runs no simulation. The two runs must exist first:
  python src/validate_traffic.py powell_no2
  python src/validate_traffic.py powell_through
Run it with:  python src/through_before_after_map.py
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
from validate_traffic_map import (
    _edge_name, _short, _mark_location, _rank_colors, _draw_map, _spearman,
    HIT_COL, MISS_COL, BG,
)

BASE_RUN = "powell_no2"        # local trips only
THRU_RUN = "powell_through"    # + 30% through-traffic


def _load(run):
    val = os.path.join(config.PROCESSED_DIR, f"{run}_count_validation.parquet")
    if not os.path.exists(val):
        raise SystemExit(f"No matched table for '{run}'; run "
                         f"`python src/validate_traffic.py {run}` first.")
    return pd.read_parquet(val)


def main():
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    edges = list(G.edges(keys=True))

    base = _load(BASE_RUN)
    thru = _load(THRU_RUN)
    # both tables index segments by row into G.edges order, so 'seg' -> edge is the
    # same mapping for both runs; align the through throughput onto the baseline rows
    thru_by_seg = dict(zip(thru["seg"].to_numpy(), thru["throughput"].to_numpy()))
    base = base[base["seg"].isin(thru_by_seg)].copy()
    base["thru_through"] = [thru_by_seg[s] for s in base["seg"].to_numpy()]
    seg_to_edge = {i: edges[i] for i in base["seg"].to_numpy()}

    # rank each quantity to a shared 0..1 percentile so all three maps mean the same
    real_pct = base["adt"].rank(pct=True).to_numpy()
    base_pct = base["throughput"].rank(pct=True).to_numpy()
    thru_pct = base["thru_through"].rank(pct=True).to_numpy()
    segs = base["seg"].to_numpy()
    real_e = {seg_to_edge[s]: p for s, p in zip(segs, real_pct)}
    base_e = {seg_to_edge[s]: p for s, p in zip(segs, base_pct)}
    thru_e = {seg_to_edge[s]: p for s, p in zip(segs, thru_pct)}

    rho_base = _spearman(base["adt"], base["throughput"])
    rho_thru = _spearman(base["adt"], base["thru_through"])

    # example streets: Powell (hit) and the BASELINE's worst over-rate (the miss),
    # so the miss is SE 26th and we can watch it fade in the through-traffic panel
    names = np.array([_edge_name(G, seg_to_edge[s]) for s in segs], dtype=object)
    is_powell = np.array(["Powell" in nm for nm in names])
    hit_i = int(np.where(is_powell)[0][np.argmax(base["adt"].to_numpy()[is_powell])])
    miss_i = int(np.argmax(base["throughput"].rank().to_numpy()
                           - base["adt"].rank().to_numpy()))
    hit_edge, miss_edge = seg_to_edge[segs[hit_i]], seg_to_edge[segs[miss_i]]

    cmap = mpl.colormaps["inferno"]
    fig = plt.figure(figsize=(19, 7), facecolor=BG)
    gs = fig.add_gridspec(1, 3, wspace=0.05)
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    panels = [
        (real_e, "REAL traffic (PBOT/county counts)\ncolor = rank of ADT"),
        (base_e, f"MODEL, local trips only\nrho = {rho_base:.2f}"),
        (thru_e, f"MODEL + 30% through-traffic\nrho = {rho_thru:.2f}"),
    ]
    for ax, (edge_pct, title) in zip(axes, panels):
        _draw_map(fig, ax, G, edge_pct, cmap, title)
        _mark_location(ax, G, hit_edge, HIT_COL, _short(names[hit_i]))
        _mark_location(ax, G, miss_edge, MISS_COL, _short(names[miss_i]))

    sm = mpl.cm.ScalarMappable(norm=mcolors.Normalize(0, 1), cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes, shrink=0.6, pad=0.01,
                        location="bottom", aspect=50)
    cbar.set_label("rank (percentile): dark = quiet street, bright = busy street",
                   color="white")
    cbar.ax.xaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "xticklabels"), color="white")

    fig.suptitle("Adding regional through-traffic moves the model toward the real "
                 f"counts:  rho {rho_base:.2f} -> {rho_thru:.2f}",
                 color="white", fontsize=15)

    out = os.path.join(config.FIGURES_DIR, "through_before_after_map.png")
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"Saved before/after figure to {out}")
    print(f"  baseline rho = {rho_base:+.3f}  ->  through-traffic rho = {rho_thru:+.3f}")
    print(f"  hit  (arterial) : {_short(names[hit_i])}")
    print(f"  miss (shortcut) : {_short(names[miss_i])}  "
          f"(baseline rank {int(base['throughput'].rank().to_numpy()[miss_i])} -> "
          f"through rank {int(base['thru_through'].rank().to_numpy()[miss_i])} of {len(segs)})")


if __name__ == "__main__":
    main()
