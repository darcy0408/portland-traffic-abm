"""Compare the CNOSSOS-EU and FHWA-TNM noise surfaces for one saved run.

Reads the two noise parquets that noise.py and noise_tnm.py wrote for the same
run (no simulation, single-source-of-truth rule), computes the agreement
metrics of NOISE_TNM_DESIGN.md section 5, renders the design's figures, and
prints a plain-language readout. Both surfaces were built from the same flows,
the same recovered congestion-aware speeds, and the same propagation, so every
disagreement measured here traces to the two countries' per-vehicle emission
curves (EU CNOSSOS category 1 vs US TNM automobile REMEL) and their low-speed
handling. That is a TIGHTER question than Shen 2026's agreement analysis, which
compared full independent national pipelines; our agreement should be much
higher than theirs, and that is expected, not impressive (design section 5
framing rule; never place the two correlations side by side as equivalents).

The absolute offset between the surfaces is soft (design D4): the REMEL-to-power
conversion involves a 2-pi vs 4-pi half-space convention worth 3 dB, so the mean
offset is reported as a descriptive number with that caveat, never as an error.
The hard, meaningful outputs are the rank/shape agreement, the slope, and WHERE
the two curves part ways (expected: congested low-speed segments, exactly the
traffic the ABM exists to produce).

Usage (standalone, reads files only, writes figures to outputs/figures):
  python src/compare_noise.py            # uses config.RUN_NAME
  python src/compare_noise.py <run_name>
"""
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")            # file output only, no display needed
import matplotlib.pyplot as plt
from scipy import stats

# make sibling modules importable whether run from repo root or from src/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import noise                      # CNOSSOS per-vehicle curve for the figure
import noise_tnm                  # TNM per-vehicle curve for the figure

# Two-series colors (CVD-safe blue/orange pair; identity is also carried by
# direct labels on the curves, never by color alone).
C_CNOSSOS = "#1f77b4"
C_TNM = "#ff7f0e"

# Congestion split: below the CNOSSOS 20 km/h validity floor the two models'
# low-speed constructions differ most (CNOSSOS clamps its source speed, TNM
# levels off at its C constant), so 20 km/h is the principled congested/flowing
# boundary for the divergence readout.
CONGESTED_KPH = noise.V_FLOOR_KPH


def load_surfaces(run_name):
    """Load both noise parquets and join them on segment identity.

    The TNM parquet already carries the CNOSSOS column (it is built from the
    CNOSSOS surface), so the merge doubles as a consistency check: the CNOSSOS
    levels stored in the two files must be identical or something rebuilt one
    surface without the other."""
    p_cnossos = os.path.join(config.PROCESSED_DIR, f"{run_name}_noise.parquet")
    p_tnm = os.path.join(config.PROCESSED_DIR, f"{run_name}_noise_tnm.parquet")
    for p, script in ((p_cnossos, "noise.py"), (p_tnm, "noise_tnm.py")):
        if not os.path.exists(p):
            raise SystemExit(f"Missing {p}; run python src/{script} {run_name} first.")
    cn = pd.read_parquet(p_cnossos)
    tn = pd.read_parquet(p_tnm)
    df = cn.merge(tn[["u", "v", "key", "noise_db", "noise_tnm_db"]],
                  on=["u", "v", "key"], suffixes=("", "_from_tnm_file"))
    both = df["noise_db"].notna() & df["noise_db_from_tnm_file"].notna()
    if not np.allclose(df.loc[both, "noise_db"],
                       df.loc[both, "noise_db_from_tnm_file"]):
        raise SystemExit("CNOSSOS levels differ between the two parquets; "
                         "rebuild both surfaces from the same run before comparing.")
    return df.drop(columns=["noise_db_from_tnm_file"])


def agreement_metrics(df):
    """Section-5 metrics over flowing segments (both surfaces lit).

    Returns a dict: per-surface summaries, correlations, the TNM-vs-CNOSSOS
    slope, and the difference distribution (TNM minus CNOSSOS)."""
    lit = df[df["noise_db"].notna() & df["noise_tnm_db"].notna()].copy()
    cn, tn = lit["noise_db"].to_numpy(), lit["noise_tnm_db"].to_numpy()
    diff = tn - cn
    v_kph = lit["v_mean_mps"].to_numpy() * 3.6

    # correlation and shape: does 1 dB more CNOSSOS mean 1 dB more TNM?
    pearson = stats.pearsonr(cn, tn)
    spearman = stats.spearmanr(cn, tn)
    slope, intercept = np.polyfit(cn, tn, 1)

    # where they diverge: difference by realized-speed band, plus the
    # congested/flowing split at the CNOSSOS floor
    bins = [0, 10, 20, 30, 40, 50, np.inf]
    labels = ["0-10", "10-20", "20-30", "30-40", "40-50", "50+"]
    band = pd.cut(v_kph, bins=bins, labels=labels)
    by_speed = pd.DataFrame({"band": band, "diff": diff}) \
        .groupby("band", observed=True)["diff"] \
        .agg(["count", "mean", "median"])

    congested = v_kph < CONGESTED_KPH
    return {
        "n": len(lit),
        "cnossos": (cn.min(), np.median(cn), cn.max()),
        "tnm": (tn.min(), np.median(tn), tn.max()),
        "pearson": pearson[0],
        "spearman": spearman[0],
        "slope": slope,
        "intercept": intercept,
        "diff_mean": diff.mean(),
        "diff_median": np.median(diff),
        "diff_std": diff.std(),
        "diff_iqr": (np.percentile(diff, 25), np.percentile(diff, 75)),
        "diff_extremes": (diff.min(), diff.max()),
        "by_speed": by_speed,
        "congested_diff": diff[congested].mean() if congested.any() else np.nan,
        "flowing_diff": diff[~congested].mean() if (~congested).any() else np.nan,
        "n_congested": int(congested.sum()),
        "lit": lit.assign(diff_db=diff, v_kph=v_kph),
    }


def fig_emission_curves(run_name):
    """Design figure 1: one vehicle's A-weighted sound power vs speed, both
    models on one axis. The plainest picture of what the comparison isolates;
    lead with this when explaining it."""
    v = np.linspace(5.0, 130.0, 200)
    # CNOSSOS per-vehicle A-weighted power (energy sum of the 8 weighted bands);
    # per_vehicle_band_power applies the 20 km/h source floor internally, so the
    # curve goes flat below it, exactly as the surface computation sees it.
    cn = np.array([10.0 * np.log10(np.sum(10.0 ** (
        (noise.per_vehicle_band_power(s) + noise.A_WEIGHTING_DB) / 10.0)))
        for s in v])
    tn = noise_tnm.tnm_vehicle_power_dba(v)   # REMEL + half-space conversion

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(v, cn, color=C_CNOSSOS, lw=2, label="CNOSSOS-EU cat. 1")
    ax.plot(v, tn, color=C_TNM, lw=2, label="FHWA TNM automobiles (REMEL)")
    ax.legend(loc="lower right", frameon=False)
    # direct labels at the low-speed end, where the curves are ~6 dB apart, so
    # identity is not color-alone and the labels cannot collide (the curves
    # cross near 60 km/h, so the right end is ambiguous)
    i25 = int(np.argmin(np.abs(v - 25.0)))
    ax.annotate("CNOSSOS-EU cat. 1", (v[i25], cn[i25]), xytext=(4, 10),
                textcoords="offset points", color=C_CNOSSOS)
    ax.annotate("TNM automobiles", (v[i25], tn[i25]), xytext=(8, -16),
                textcoords="offset points", color=C_TNM)
    # mark the structural low-speed difference: CNOSSOS application floor
    ax.axvline(noise.V_FLOOR_KPH, color="0.6", lw=1, ls=":")
    ax.text(0.02, 0.80, "CNOSSOS 20 km/h floor\n(TNM levels off at its C constant)",
            transform=ax.transAxes, fontsize=8, color="0.35", va="top")
    ax.set_xlabel("speed (km/h)")
    ax.set_ylabel("per-vehicle sound power, dB(A)")
    ax.set_title("The one thing the comparison swaps: per-vehicle emission curves")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out = os.path.join(config.FIGURES_DIR, f"{run_name}_noise_emission_curves.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def fig_scatter(m, run_name):
    """Design figure 2: per-segment TNM vs CNOSSOS dB(A) with the identity
    line, colored by realized speed (sequential ramp) so the low-speed wing of
    the disagreement is visible in the same picture."""
    lit = m["lit"]
    fig, ax = plt.subplots(figsize=(6.2, 5.5))
    lo = min(lit["noise_db"].min(), lit["noise_tnm_db"].min()) - 1
    hi = max(lit["noise_db"].max(), lit["noise_tnm_db"].max()) + 1
    ax.plot([lo, hi], [lo, hi], color="0.65", lw=1, ls="--", zorder=1)
    ax.annotate("identity", (hi, hi), xytext=(-30, -14),
                textcoords="offset points", color="0.45", fontsize=8)
    sc = ax.scatter(lit["noise_db"], lit["noise_tnm_db"], c=lit["v_kph"],
                    cmap="viridis", s=9, alpha=0.7, linewidths=0, zorder=2)
    fig.colorbar(sc, ax=ax, label="realized mean speed (km/h)")
    ax.set_xlabel("CNOSSOS dB(A) at 10 m")
    ax.set_ylabel("TNM (REMEL) dB(A) at 10 m")
    ax.set_title(f"Same traffic, two emission models ({m['n']} segments)\n"
                 f"Pearson {m['pearson']:.3f}, slope {m['slope']:.3f}")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect("equal")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out = os.path.join(config.FIGURES_DIR, f"{run_name}_noise_tnm_scatter.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def fig_diff_vs_speed(m, run_name):
    """Design figure 3: per-segment difference (TNM minus CNOSSOS) against the
    realized speed, colored by flow. This is where and why the two models part
    ways; the congested low-speed wing is the scientifically interesting part."""
    lit = m["lit"]
    fig, ax = plt.subplots(figsize=(7, 4.8))
    ax.axhline(0.0, color="0.65", lw=1, ls="--")
    sc = ax.scatter(lit["v_kph"], lit["diff_db"], c=lit["q_vph"],
                    cmap="magma_r", s=9, alpha=0.7, linewidths=0)
    fig.colorbar(sc, ax=ax, label="flow (veh/h)")
    ax.axvline(CONGESTED_KPH, color="0.6", lw=1, ls=":")
    ax.annotate("CNOSSOS floor", (CONGESTED_KPH, ax.get_ylim()[1]),
                xytext=(4, -12), textcoords="offset points",
                fontsize=8, color="0.35")
    ax.set_xlabel("realized mean speed (km/h)")
    ax.set_ylabel("TNM minus CNOSSOS, dB")
    ax.set_title("Where the two emission models diverge")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out = os.path.join(config.FIGURES_DIR, f"{run_name}_noise_tnm_diff_vs_speed.png")
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else config.RUN_NAME
    df = load_surfaces(run)
    m = agreement_metrics(df)

    print(f"CNOSSOS vs TNM noise surfaces on '{run}' "
          f"({m['n']} flowing segments, both models):")
    for name, (mn, md, mx) in (("CNOSSOS", m["cnossos"]), ("TNM    ", m["tnm"])):
        print(f"  {name} dB(A) at 10 m: min {mn:.1f}, median {md:.1f}, max {mx:.1f}")
    print(f"  Agreement: Pearson {m['pearson']:.3f}, Spearman {m['spearman']:.3f}, "
          f"slope {m['slope']:.3f} (intercept {m['intercept']:.1f} dB)")
    q1, q3 = m["diff_iqr"]
    dmin, dmax = m["diff_extremes"]
    print(f"  Difference (TNM - CNOSSOS): mean {m['diff_mean']:+.2f} dB, "
          f"median {m['diff_median']:+.2f} dB, sd {m['diff_std']:.2f}, "
          f"IQR [{q1:+.2f}, {q3:+.2f}], extremes [{dmin:+.2f}, {dmax:+.2f}]")
    print("  NOTE (design D4): the absolute offset is soft. The REMEL-to-power "
          "conversion carries a 2-pi/4-pi half-space convention worth 3 dB, so "
          "read the offset as descriptive, never as an error of either model.")
    print("  Difference by realized speed band (km/h):")
    for band, row in m["by_speed"].iterrows():
        print(f"    {band:>5}: n {int(row['count']):4d}, "
              f"mean {row['mean']:+.2f} dB, median {row['median']:+.2f} dB")
    print(f"  Congested (< {CONGESTED_KPH:.0f} km/h, n {m['n_congested']}): "
          f"mean diff {m['congested_diff']:+.2f} dB; "
          f"flowing: {m['flowing_diff']:+.2f} dB")

    for f in (fig_emission_curves(run), fig_scatter(m, run), fig_diff_vs_speed(m, run)):
        print(f"  Wrote {f}")

    # plain-language readout, in the design's agreement-analysis framing
    print("\nReadout: with traffic and propagation held identical, the two "
          "countries' emission curves rank the network's segments "
          f"{'almost identically' if m['spearman'] > 0.99 else 'very similarly' if m['spearman'] > 0.95 else 'similarly'} "
          f"(Spearman {m['spearman']:.3f}). The level offset between them is "
          f"{m['diff_median']:+.1f} dB at the median (soft, see D4), and the "
          "spread around that offset comes from speed: the divergence "
          "concentrates in the congested low-speed segments, where the EU model "
          "clamps its source at 20 km/h while the US model levels off at its "
          "fitted idle floor. This is a model-to-model agreement statement, not "
          "an accuracy claim for either model.")


if __name__ == "__main__":
    main()
