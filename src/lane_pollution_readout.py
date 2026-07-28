"""Read the lane-pollution experiment runs and produce the Aug-14 result:
the congestion-vs-pollution story, as a table and a figure.

Analysis-only (CLAUDE.md single-source-of-truth): reads every
`data/processed/lanepoll_*_segments.parquet` that src/lane_pollution_experiment.py
wrote, plus the cached corridor graph to identify Powell edges. Never runs a sim.

The headline it computes: NOx is emitted per SECOND (idling + stop-and-go), so
CONGESTION -- not car count -- drives pollution. On a saturated corridor a
second lane can carry MORE cars yet emit LESS, by clearing the standing queue;
push demand high enough that both lanes jam and the effect reverses. This reads
that curve out across seeds (mean +/- spread), for 1-lane vs 2-lane.
"""
import glob
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

import config

NAME_RE = re.compile(r"lanepoll_(1lane|2lane)_n(\d+)_s(\d+)_segments\.parquet$")


def powell_edges():
    """(u,v,key) tuples on Powell, from the cached corridor graph."""
    import osmnx as ox
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    out = set()
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        names = nm if isinstance(nm, list) else [nm]
        if any(n and "powell" in str(n).lower() for n in names):
            out.add((u, v, k))
    return out


def main():
    files = glob.glob(os.path.join(config.PROCESSED_DIR, "lanepoll_*_segments.parquet"))
    if not files:
        raise SystemExit("no lanepoll_* runs found; run "
                         "src/lane_pollution_experiment.py --all first")
    powell = powell_edges()

    rows = []
    for f in files:
        m = NAME_RE.search(os.path.basename(f))
        if not m:
            continue
        lanes, n, seed = m.group(1), int(m.group(2)), int(m.group(3))
        df = pd.read_parquet(f)
        pmask = df.set_index(["u", "v", "key"]).index.isin(powell)
        rows.append({
            "lanes": lanes, "n_veh": n, "seed": seed,
            "total_nox": df.nox_g.sum(),
            "powell_nox": df.loc[pmask.nonzero()[0], "nox_g"].sum()
                          if "nox_g" in df else np.nan,
            "busiest": df.throughput.max() if "throughput" in df else np.nan,
        })
    d = pd.DataFrame(rows)
    print(f"loaded {len(d)} runs: {sorted(d.n_veh.unique())} demands x "
          f"{sorted(d.lanes.unique())} x {d.seed.nunique()} seeds\n")

    # aggregate over seeds
    agg = (d.groupby(["lanes", "n_veh"])
             .agg(powell_mean=("powell_nox", "mean"),
                  powell_std=("powell_nox", "std"),
                  total_mean=("total_nox", "mean"),
                  busiest_mean=("busiest", "mean"),
                  n_seeds=("seed", "nunique"))
             .reset_index())

    print("Powell-corridor NOx (g), mean +/- SD over seeds:")
    print(f"  {'demand':>7} | {'1 lane':>16} | {'2 lanes':>16} | {'2-lane vs 1-lane':>18}")
    for n in sorted(d.n_veh.unique()):
        one = agg[(agg.lanes == "1lane") & (agg.n_veh == n)]
        two = agg[(agg.lanes == "2lane") & (agg.n_veh == n)]
        if one.empty or two.empty:
            continue
        o, os_ = one.powell_mean.iat[0], one.powell_std.iat[0]
        t, ts = two.powell_mean.iat[0], two.powell_std.iat[0]
        pct = 100 * (t - o) / o if o else float("nan")
        print(f"  {n:>7} | {o:>7.0f} +/- {os_:>4.0f} | {t:>7.0f} +/- {ts:>4.0f} | "
              f"{pct:>+16.0f}%")

    print("\nBusiest-segment throughput (veh/hr), mean over seeds  "
          "(the capacity ceiling):")
    for n in sorted(d.n_veh.unique()):
        one = agg[(agg.lanes == "1lane") & (agg.n_veh == n)]
        two = agg[(agg.lanes == "2lane") & (agg.n_veh == n)]
        if one.empty or two.empty:
            continue
        print(f"  demand {n:>5}: 1 lane {one.busiest_mean.iat[0]:>5.0f}  ->  "
              f"2 lanes {two.busiest_mean.iat[0]:>5.0f}")

    # --- figure -------------------------------------------------------------
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    BG = "#07111f"; INK = "#f8fafc"; MUTED = "#8fa0b8"
    C1 = "#ff6b62"    # 1 lane -- congested/red
    C2 = "#16d6c1"    # 2 lanes -- flowing/teal
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11, 4.6), facecolor=BG)
    for ax in (axL, axR):
        ax.set_facecolor(BG)
        for sp in ax.spines.values():
            sp.set_color("#24344c")
        ax.tick_params(colors=MUTED)
        ax.grid(True, color="#16233a", lw=0.6)

    def line(ax, lanes, color, label, col):
        s = agg[agg.lanes == lanes].sort_values("n_veh")
        ax.plot(s.n_veh, s[col], color=color, lw=2.4, marker="o", ms=6,
                label=label, zorder=3)
        if col == "powell_mean":
            ax.fill_between(s.n_veh, s.powell_mean - s.powell_std,
                            s.powell_mean + s.powell_std, color=color, alpha=0.15)

    line(axL, "1lane", C1, "1 lane", "powell_mean")
    line(axL, "2lane", C2, "2 lanes (real counts)", "powell_mean")
    axL.set_title("Powell-corridor NO₂ vs demand\n"
                  "congestion (idling), not car count, drives pollution",
                  color=INK, fontsize=11, loc="left")
    axL.set_xlabel("vehicles in the model (demand)", color=MUTED)
    axL.set_ylabel("Powell-corridor NO₂ (g)", color=MUTED)
    axL.legend(facecolor=BG, edgecolor="#24344c", labelcolor=INK, fontsize=9)

    line(axR, "1lane", C1, "1 lane", "busiest_mean")
    line(axR, "2lane", C2, "2 lanes (real counts)", "busiest_mean")
    axR.set_title("Busiest-segment throughput vs demand\n"
                  "the single-lane capacity ceiling",
                  color=INK, fontsize=11, loc="left")
    axR.set_xlabel("vehicles in the model (demand)", color=MUTED)
    axR.set_ylabel("busiest segment (veh/hr)", color=MUTED)
    axR.legend(facecolor=BG, edgecolor="#24344c", labelcolor=INK, fontsize=9)

    fig.tight_layout()
    out = os.path.join(config.FIGURES_DIR, "lane_pollution_curve.png")
    fig.savefig(out, dpi=200, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    print(f"\nfigure -> {out}")


if __name__ == "__main__":
    main()
