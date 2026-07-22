"""Build the chapter Section 6 figure: forest-comparison R^2 by feature set and
spatial block size, with the shuffle-control null band.

Read-only with respect to the simulation: reads the saved metro20k surface, the
Rao sites, and the land-use inputs; refits the (seeded) forests through the same
committed code paths the ledger numbers came from (forest_compare.compare and
forest_compare.shuffle_control, summer, areal OR+WA land use).

REPRODUCTION GATE: before drawing anything, the 2 km scores must reproduce the
banked ledger values (M20.10: land-use 0.394 / combined 0.460). If they do not,
the script aborts rather than produce a figure that disagrees with the ledger.

Outputs:
  <metro processed>/forest_figure_results.json   (the numbers behind the figure)
  outputs/figures/forest_compare_r2.png          (the figure itself)

Run:  python src/forest_figure.py
"""
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from mixed_rerun import apply_metro_dirs

RUN = "metro20k"
BLOCKS_M = [1000, 2000, 3000]
N_SHUFFLES = 10

# banked values this build must reproduce (RESULTS_LEDGER.md M20.10, 2 km)
GATE = {"land-use": 0.394, "combined": 0.460}
GATE_TOL = 0.005

# categorical palette (dataviz skill reference instance, validated 3-slot light)
COLORS = {"land-use": "#2a78d6", "abm": "#008300", "combined": "#e87ba4"}
LABELS = {"land-use": "land use", "abm": "ABM traffic", "combined": "combined"}
SURFACE, INK, INK2 = "#fcfcfb", "#0b0b0b", "#52514e"


def build_numbers():
    import forest_compare
    data = forest_compare.assemble(run_name=RUN, season="summer", demog="areal")
    out = {"run": RUN, "season": "summer", "demog": "areal",
           "n_sites": int(len(data["y"])), "blocks": {}}
    for bm in BLOCKS_M:
        res = forest_compare.compare(run_name=RUN, block_m=bm, data=data)
        shuf = forest_compare.shuffle_control(data, block_m=bm,
                                              n_shuffles=N_SHUFFLES)
        out["blocks"][str(bm)] = {
            "r2": {k: res["scores"][k]["r2"] for k in res["scores"]},
            "n_folds": res["n_folds"],
            "shuffle_mean": float(np.mean(shuf)),
            "shuffle_std": float(np.std(shuf)),
        }
        b = out["blocks"][str(bm)]
        print(f"{bm} m blocks: " +
              "  ".join(f"{k} {v:.3f}" for k, v in b["r2"].items()) +
              f"  | shuffled-combined {b['shuffle_mean']:.3f} "
              f"+/- {b['shuffle_std']:.3f}", flush=True)

    got = out["blocks"]["2000"]["r2"]
    for k, want in GATE.items():
        if abs(got[k] - want) > GATE_TOL:
            raise SystemExit(f"REPRODUCTION GATE FAILED: 2 km {k} = {got[k]:.3f}, "
                             f"ledger M20.10 says {want:.3f}. Not drawing a figure "
                             "that disagrees with the ledger; investigate first.")
    print("reproduction gate passed (2 km scores match ledger M20.10)")
    return out


def draw(numbers, path):
    fig, ax = plt.subplots(figsize=(7.2, 4.4), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    sets = ["land-use", "abm", "combined"]
    x = np.arange(len(BLOCKS_M))
    w = 0.26                       # < slot width, so adjacent bars keep a gap
    for i, s in enumerate(sets):
        vals = [numbers["blocks"][str(bm)]["r2"][s] for bm in BLOCKS_M]
        bars = ax.bar(x + (i - 1) * (w + 0.02), vals, w, color=COLORS[s],
                      label=LABELS[s], zorder=3)
        ax.bar_label(bars, fmt="%.2f", padding=2, fontsize=8.5, color=INK)

    # shuffle-control null: scrambled ABM rows, refit combined forest. Drawn as a
    # neutral band (mean +/- std) per group; the true combined bar clearing it is
    # the point of the figure.
    for xi, bm in zip(x, BLOCKS_M):
        b = numbers["blocks"][str(bm)]
        lo = b["shuffle_mean"] - b["shuffle_std"]
        hi = b["shuffle_mean"] + b["shuffle_std"]
        ax.fill_between([xi - 0.47, xi + 0.47], lo, hi, color="#9a9891",
                        alpha=0.35, zorder=2, linewidth=0,
                        label="shuffled-ABM null" if bm == BLOCKS_M[0] else None)
        ax.plot([xi - 0.47, xi + 0.47], [b["shuffle_mean"]] * 2, color="#6b6a65",
                lw=1.2, ls="--", zorder=2)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{bm // 1000} km blocks" for bm in BLOCKS_M],
                       fontsize=10, color=INK)
    ax.set_ylabel("out-of-fold R² (spatial block CV)", fontsize=10, color=INK)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(axis="y", color="#e4e2dc", lw=0.8, zorder=0)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#c9c7c0")
    ax.set_ylim(0, max(numbers["blocks"][str(bm)]["r2"]["combined"]
                       for bm in BLOCKS_M) * 1.22)
    ax.legend(frameon=False, fontsize=9, ncol=4, loc="upper left",
              labelcolor=INK)
    ax.set_title(f"Measured NO₂ at {numbers['n_sites']} sites: "
                 "predictive skill by feature set",
                 fontsize=11, color=INK, pad=10)

    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    print(f"figure -> {path}")


def main():
    apply_metro_dirs()
    numbers = build_numbers()
    res_path = os.path.join(config.PROCESSED_DIR, "forest_figure_results.json")
    with open(res_path, "w") as f:
        json.dump(numbers, f, indent=2)
    print(f"numbers -> {res_path}")
    fig_path = os.path.join(config.FIGURES_DIR, "forest_compare_r2.png")
    draw(numbers, fig_path)


if __name__ == "__main__":
    main()
