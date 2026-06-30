"""Traffic-layer validation FIGURE (Christof, Jun 29): show the model's traffic
next to the real Portland counts on the same streets, so the match can be judged
by eye, before any NO2.

Christof's ask: validate the traffic foundation first. Lead with "do the cars go
where the real counts say cars go?", not with the pollution surface downstream of
it. This script answers that with three panels read from saved files (no sim run):

  left  map : real PBOT/county ADT, per matched segment, colored by RANK
  right map : the model's throughput, same segments, colored by RANK
  scatter   : rank(real) vs rank(model), the Spearman scatter, with rho

Color is RANK (percentile), not raw value, because the two quantities are in
different units (vehicles/day vs vehicles/simulated-hour) and the absolute level
is not calibrated yet. Coloring both maps by rank makes them directly comparable:
the same color means the same position in the ordering, so a street that is bright
on the left should be bright on the right if the model orders streets like reality.
Only the segments that have a real count are colored; the rest stay dim grey, so
the figure never implies a comparison where there is no ground truth.

Run it with:  python src/validate_traffic_map.py [run_name]   (default config.RUN_NAME)
Needs the matched table from validate_traffic.py first:
  python src/traffic_counts.py        # pull the counts (once)
  python src/validate_traffic.py R     # writes R_count_validation.parquet
  python src/validate_traffic_map.py R
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

BG = "#0e0e12"
GREY = (0.16, 0.16, 0.20, 1.0)   # streets with no real count: not part of the comparison


def _edge_name(G, edge):
    """Street name for a (u, v, k) edge; joins the list OSM sometimes stores."""
    nm = G.edges[edge].get("name", "")
    if isinstance(nm, list):
        nm = ", ".join(dict.fromkeys(nm))
    return nm or ""


def _short(name):
    """Shorten a street name for an on-figure label (Southeast 26th Avenue -> SE 26th Ave)."""
    for a, b in [("Southeast", "SE"), ("Northeast", "NE"), ("Southwest", "SW"),
                 ("Northwest", "NW"), ("Boulevard", "Blvd"), ("Avenue", "Ave"),
                 ("Street", "St"), ("Place", "Pl")]:
        name = name.replace(a, b)
    return name


HIT_COL = "#1fe0c8"    # cyan: the model's best agreement (a headline arterial)
MISS_COL = "#ff45d0"   # magenta: the model's worst over-rate (a quiet street it over-uses)


def _mark_location(ax, G, edge, color, label):
    """Ring an edge's location on a map with an open circle (so the street's own
    rank color still shows through) and label it, so the same street can be traced
    across all three panels."""
    u, v, k = edge
    geom = G.edges[edge].get("geometry")
    if geom is not None:
        xs, ys = geom.xy
        mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
    else:
        mx = 0.5 * (G.nodes[u]["x"] + G.nodes[v]["x"])
        my = 0.5 * (G.nodes[u]["y"] + G.nodes[v]["y"])
    ax.scatter([mx], [my], s=320, facecolors="none", edgecolors=color,
               linewidths=2.6, zorder=10)
    ax.annotate(label, (mx, my), textcoords="offset points", xytext=(9, 6),
                color=color, fontsize=9, weight="bold", zorder=11)


def _spearman(a, b):
    """Spearman rank correlation: Pearson correlation of the ranks."""
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def _rank_colors(G, edge_to_pct, cmap):
    """One color and width per edge in G order. Matched segments are colored by
    their percentile (0..1); everything else is dim grey and thin."""
    colors, widths = [], []
    for e in G.edges(keys=True):
        pct = edge_to_pct.get(e)
        if pct is None:
            colors.append(GREY)
            widths.append(0.4)
        else:
            colors.append(cmap(pct))
            widths.append(0.8 + 3.2 * pct)   # higher rank -> thicker line
    return colors, widths


def _draw_map(fig, ax, G, edge_to_pct, cmap, title):
    colors, widths = _rank_colors(G, edge_to_pct, cmap)
    ox.plot_graph(G, ax=ax, edge_color=colors, edge_linewidth=widths,
                  node_size=0, bgcolor=BG, show=False, close=False)
    ax.set_facecolor(BG)
    ax.set_title(title, color="white", fontsize=12)


def main(run_name):
    val_path = os.path.join(config.PROCESSED_DIR, f"{run_name}_count_validation.parquet")
    if not os.path.exists(val_path):
        raise SystemExit(f"No matched table at {val_path}; run "
                         f"`python src/validate_traffic.py {run_name}` first.")
    per_seg = pd.read_parquet(val_path)
    abm = pd.read_parquet(os.path.join(config.PROCESSED_DIR, f"{run_name}_segments.parquet"))
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))

    # per_seg["seg"] is the row index into the abm table, whose rows are in G.edges
    # order (save_results writes segment_totals.items()). So seg -> edge directly.
    edges = list(G.edges(keys=True))
    seg_to_edge = {i: edges[i] for i in per_seg["seg"].to_numpy()}

    # rank each quantity to a 0..1 percentile so the two maps share one color meaning
    real_pct = per_seg["adt"].rank(pct=True).to_numpy()
    model_pct = per_seg["throughput"].rank(pct=True).to_numpy()
    real_by_edge = {seg_to_edge[s]: p for s, p in zip(per_seg["seg"], real_pct)}
    model_by_edge = {seg_to_edge[s]: p for s, p in zip(per_seg["seg"], model_pct)}

    rho = _spearman(per_seg["adt"], per_seg["throughput"])
    n = len(per_seg)

    # pick two example segments to highlight in ALL three panels, so the audience
    # can trace one street from the maps to the scatter: the model's best agreement
    # on a headline arterial (Powell) and its worst over-rate (a quiet street the
    # route-finder over-uses). Both come from the data, not hard-coded.
    ranks_real = per_seg["adt"].rank().to_numpy()
    ranks_model = per_seg["throughput"].rank().to_numpy()
    segs = per_seg["seg"].to_numpy()
    seg_names = np.array([_edge_name(G, seg_to_edge[s]) for s in segs], dtype=object)
    is_powell = np.array(["Powell" in nm for nm in seg_names])
    hit_i = int(np.where(is_powell)[0][np.argmax(per_seg["adt"].to_numpy()[is_powell])])
    miss_i = int(np.argmax(ranks_model - ranks_real))
    hit_edge, miss_edge = seg_to_edge[segs[hit_i]], seg_to_edge[segs[miss_i]]

    cmap = mpl.colormaps["inferno"]
    fig = plt.figure(figsize=(18, 7), facecolor=BG)
    gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.0, 0.9], wspace=0.08)
    ax_real = fig.add_subplot(gs[0, 0])
    ax_model = fig.add_subplot(gs[0, 1])
    ax_sc = fig.add_subplot(gs[0, 2])

    _draw_map(fig, ax_real, G, real_by_edge, cmap,
              "REAL traffic (PBOT/county counts)\ncolor = rank of ADT")
    _draw_map(fig, ax_model, G, model_by_edge, cmap,
              "MODEL traffic (ABM throughput)\ncolor = rank of vehicles through segment")

    # ring the same two example streets on both maps in their scatter colors, so
    # the eye can check: Powell bright in both (agreement), 26th dark-then-bright
    for ax in (ax_real, ax_model):
        _mark_location(ax, G, hit_edge, HIT_COL, _short(seg_names[hit_i]))
        _mark_location(ax, G, miss_edge, MISS_COL, _short(seg_names[miss_i]))

    # shared rank colorbar spanning the two maps
    sm = mpl.cm.ScalarMappable(norm=mcolors.Normalize(0, 1), cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=[ax_real, ax_model], shrink=0.6, pad=0.01,
                        location="bottom", aspect=40)
    cbar.set_label("rank (percentile): dark = quiet street, bright = busy street",
                   color="white")
    cbar.ax.xaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "xticklabels"), color="white")

    # scatter: the Spearman picture
    ax_sc.set_facecolor(BG)
    ax_sc.scatter(ranks_real, ranks_model, s=22, c="#f2b134", alpha=0.8,
                  edgecolors="none")
    lim = [0, n + 1]
    ax_sc.plot(lim, lim, ls="--", color="#888", lw=1.2)   # perfect-agreement line
    # least-squares trend through the rank cloud
    b, a = np.polyfit(ranks_real, ranks_model, 1)
    xs = np.array(lim)
    ax_sc.plot(xs, b * xs + a, color="#e0482b", lw=2)
    # mark the same two example streets as on the maps (open circle + label); both
    # dots sit high on the plot, so drop their labels below to clear the title
    for i, role, col, dx, ha in [(hit_i, "hit", HIT_COL, -10, "right"),
                                 (miss_i, "miss", MISS_COL, 10, "left")]:
        ax_sc.scatter([ranks_real[i]], [ranks_model[i]], s=140, facecolors="none",
                      edgecolors=col, linewidths=2.4, zorder=5)
        ax_sc.annotate(f"{_short(seg_names[i])} ({role})",
                       (ranks_real[i], ranks_model[i]), textcoords="offset points",
                       xytext=(dx, -16), ha=ha, color=col, fontsize=10, weight="bold",
                       zorder=6)

    ax_sc.set_xlim(lim); ax_sc.set_ylim(lim)
    ax_sc.set_xlabel("rank of REAL traffic count (ADT)", color="white")
    ax_sc.set_ylabel("rank of MODEL traffic (throughput)", color="white")
    ax_sc.set_title(f"Spearman rho = {rho:.2f}", color="white", fontsize=12)
    ax_sc.tick_params(colors="white")
    for s in ax_sc.spines.values():
        s.set_color("#555")
    ax_sc.grid(True, alpha=0.18)

    fig.suptitle(f"Does the model put traffic where the city counts it?  "
                 f"n = {n} segments, Spearman rho = {rho:.2f}  (run '{run_name}')",
                 color="white", fontsize=15)

    out = os.path.join(config.FIGURES_DIR, f"{run_name}_traffic_validation_map.png")
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"Saved traffic validation figure to {out}")
    print(f"  {n} matched segments, Spearman rho(real ADT, model throughput) = {rho:+.3f}")


if __name__ == "__main__":
    run = sys.argv[1] if len(sys.argv) > 1 else config.RUN_NAME
    main(run)
