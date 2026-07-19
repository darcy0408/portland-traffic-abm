"""Through-traffic BEFORE/AFTER SCATTER (Jul 1).

the mentor cares about the POINTS, not the maps: whether the streets fall on the
agreement line. This shows the same Spearman scatter twice, side by side, WITHOUT
through-traffic (baseline) and WITH it, so the effect on the point cloud is visible.
Each dot is one of the matched street segments; the dashed line is perfect agreement
and the red line is the actual trend. Reads the two runs' saved validation tables,
runs no simulation.

  python src/validate_traffic.py powell_no2
  python src/validate_traffic.py powell_through
  python src/through_before_after_scatter.py
"""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from validate_traffic_map import _spearman

BG = "#0e0e12"
RUNS = [("powell_no2", "MODEL, local trips only"),
        ("powell_through", "MODEL + 30% through-traffic")]


def _load(run):
    p = os.path.join(config.PROCESSED_DIR, f"{run}_count_validation.parquet")
    if not os.path.exists(p):
        raise SystemExit(f"No matched table for '{run}'; run "
                         f"`python src/validate_traffic.py {run}` first.")
    return pd.read_parquet(p)


def _panel(ax, per_seg, title):
    rr = per_seg["adt"].rank().to_numpy()
    rm = per_seg["throughput"].rank().to_numpy()
    n = len(per_seg)
    rho = _spearman(per_seg["adt"], per_seg["throughput"])
    ax.set_facecolor(BG)
    ax.scatter(rr, rm, s=22, c="#f2b134", alpha=0.8, edgecolors="none")
    lim = [0, n + 1]
    ax.plot(lim, lim, ls="--", color="#888", lw=1.2)          # perfect agreement
    b, a = np.polyfit(rr, rm, 1)
    xs = np.array(lim)
    ax.plot(xs, b * xs + a, color="#e0482b", lw=2)            # actual trend
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("rank of REAL traffic count (ADT)", color="white")
    ax.set_ylabel("rank of MODEL traffic (throughput)", color="white")
    ax.set_title(f"{title}\nSpearman rho = {rho:.2f}", color="white", fontsize=12)
    ax.tick_params(colors="white")
    for s in ax.spines.values():
        s.set_color("#555")
    ax.grid(True, alpha=0.18)
    return rho


def main():
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.2), facecolor=BG)
    rhos = [_panel(ax, _load(run), title) for ax, (run, title) in zip(axes, RUNS)]
    fig.suptitle("Do the streets move onto the agreement line?  "
                 f"rho {rhos[0]:.2f} (local only)  ->  {rhos[1]:.2f} (+ through-traffic)",
                 color="white", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = os.path.join(config.FIGURES_DIR, "through_before_after_scatter.png")
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"Saved before/after scatter to {out}")
    print(f"  baseline rho = {rhos[0]:+.3f}  ->  through-traffic rho = {rhos[1]:+.3f}")


if __name__ == "__main__":
    main()
