"""The Thursday one-pager: the metro calibrated-experiment result as one figure.

Analysis-only (CLAUDE.md single-source-of-truth): reads the per-run
`data/processed/metrocal_*_summary.json` files the Orca runs wrote; never runs
a sim. Two panels, same two series (realism stack vs base model) over the
demand ladder:

  A) busiest Powell segment veh/hr, mean +/- SD over 8 seeds, with the real
     peak band shaded -- THE validation picture: realism enters the band
     at the untuned a-priori demand, base saturates ~1,000 and never does.
     The band is derived from ODOT's measured Powell AADT, NOT from the PBOT
     counts (those stay held out; see calibrate_demand.py's honesty note).
     Mislabeling it "PBOT counts" would assert the opposite of the project's
     validation claim, so the provenance is spelled out on the figure itself.
  B) network-wide stuck vehicle-hours (measured, below 5 km/h) -- realism
     roughly halves gridlock at every demand level.

Colors are the dataviz-validated categorical pair (blue/orange, CVD-checked).

Run: python src/metro_calibrated_figure.py
Writes: outputs/figures/metro_calibrated_band.png
"""
import glob
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import config

# Powell peak-hour directional band, veh/hr. Provenance: ODOT 2018 verified AADT
# 34,900 at Powell/SE 26th, x 50% directional split x the 8-10% K-factor
# (src/calibrate_demand.py). The held-out PBOT counts are NOT its source.
REAL_BAND = (1400, 1745)
COLORS = {"realism": "#2a78d6", "base": "#eb6834"}   # validated pair
LABELS = {"realism": "realism stack\n(MOBIL + Webster + green-wave)",
          "base": "base model\n(single lane, uniform signals)"}


def load():
    """{(arm, n_veh): [summary, ...]} for hour runs only."""
    groups = {}
    for path in glob.glob(os.path.join(config.PROCESSED_DIR,
                                       "metrocal_*_summary.json")):
        with open(path) as f:
            s = json.load(f)
        if "smoke" in s["name"] or s["name"].startswith("metrocal_day_"):
            continue
        groups.setdefault((s["arm"], s["n_veh"]), []).append(s)
    return groups


def series(groups, arm, key):
    """demands, means, sds for one arm and one summary key."""
    demands = sorted({n for a, n in groups if a == arm})
    means, sds = [], []
    for n in demands:
        vals = np.array([s[key] for s in groups[(arm, n)]], dtype=float)
        means.append(vals.mean())
        sds.append(vals.std(ddof=1))
    return np.array(demands), np.array(means), np.array(sds)


def main():
    groups = load()
    n_seeds = max(len(v) for v in groups.values())
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(11, 4.6))

    # --- panel A: busiest Powell vs demand, with the real band ---------------
    ax_a.axhspan(*REAL_BAND, color="#dce9dc", zorder=0)
    ax_a.text(0.02, (REAL_BAND[1] - 40), "real Powell peak band "
              f"({REAL_BAND[0]:,}–{REAL_BAND[1]:,} veh/hr, from ODOT AADT)",
              transform=ax_a.get_yaxis_transform(), fontsize=8.5,
              color="#3a5a3a", va="top")
    for arm in ("realism", "base"):
        d, m, sd = series(groups, arm, "busiest_powell_veh_hr")
        ax_a.errorbar(d, m, yerr=sd, color=COLORS[arm], lw=2, marker="o",
                      ms=6, capsize=3, label=LABELS[arm].replace("\n", " "))
        # direct label at the line's right end (identity never color-alone)
        ax_a.annotate(arm, (d[-1], m[-1]), xytext=(8, 0),
                      textcoords="offset points", color=COLORS[arm],
                      fontsize=9, fontweight="bold", va="center")
    # the a-priori demand marker: nothing was tuned toward the band
    d0 = min(n for _, n in groups)
    ax_a.axvline(d0, color="#999999", lw=0.8, ls=":")
    ax_a.text(d0, 380, " a-priori demand\n (untuned)", fontsize=8,
              color="#666666", va="bottom")
    ax_a.set_title("Does the model carry real Powell volume?", fontsize=11,
                   loc="left", fontweight="bold")
    ax_a.set_ylabel("busiest Powell segment (veh/hr)")
    ax_a.legend(loc="lower right", fontsize=8, frameon=False)
    ax_a.set_ylim(0, 1900)

    # --- panel B: measured network stuck time --------------------------------
    for arm in ("realism", "base"):
        d, m, sd = series(groups, arm, "network_stuck_veh_h")
        ax_b.errorbar(d, m, yerr=sd, color=COLORS[arm], lw=2, marker="o",
                      ms=6, capsize=3)
        ax_b.annotate(arm, (d[-1], m[-1]), xytext=(8, 0),
                      textcoords="offset points", color=COLORS[arm],
                      fontsize=9, fontweight="bold", va="center")
    ax_b.set_title("Vehicle-hours stuck (< 5 km/h), network-wide",
                   fontsize=11, loc="left", fontweight="bold")
    ax_b.set_ylabel("stuck vehicle-hours (measured)")
    ax_b.set_ylim(0, None)

    for ax in (ax_a, ax_b):
        ax.set_xlabel("demand (vehicles in the metro network)")
        ax.set_xticks([16500, 24750, 33000])
        ax.get_xaxis().set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.grid(axis="y", color="#e6e6e6", lw=0.7)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.margins(x=0.14)

    fig.suptitle("Metro scale: the realism stack reaches the real Powell band; "
                 "the base model saturates below it",
                 fontsize=12, fontweight="bold", x=0.02, ha="left")
    # Two lines: the one-line version overflows the right edge at this figsize.
    # Claim discipline: state what was NOT fitted, rather than calling the band
    # "held-out" (the PBOT counts are the held-out set; the band is ODOT AADT).
    fig.text(0.02, 0.935, f"Portland 20 km OSM network (159k directed edges), "
             f"LODES OD demand, mean ± SD over {n_seeds} seeds. Orca, Jul 29.\n"
             f"All parameters a-priori; nothing was fitted to the band or to "
             f"the held-out PBOT counts.", fontsize=8.5, color="#555555",
             va="top", linespacing=1.5)
    fig.tight_layout(rect=(0, 0, 1, 0.86))

    out = os.path.join(config.FIGURES_DIR, "metro_calibrated_band.png")
    fig.savefig(out, dpi=200)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
