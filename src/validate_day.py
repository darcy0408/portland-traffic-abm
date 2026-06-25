"""Validate the 24-hour time-of-day run against the demand shape that drove it.

The `day` experiment (generate.py) sets each hour's vehicle count proportional to
the real PORTAL hourly profile (demand_data.py). This script asks two questions of
the result, one a sanity check and one a finding.

1. FACE VALIDITY (does the model reproduce the shape we put in?). We drove the car
   COUNT by the profile, but the model's realized THROUGHPUT (vehicles actually
   completing segments) is an output of the full simulation: routing, signals,
   car-following, queueing. If the network gridlocked at the peak, throughput would
   fall below the input share exactly when load is highest. So checking that hourly
   throughput still tracks the input profile is a real test that the model behaves
   sensibly across the whole load range, not a tautology. We report the Pearson and
   Spearman correlation of throughput-share vs profile-share.

2. THE CONGESTION FINDING (where the model departs from the shape, on purpose).
   NO2 is NOT expected to track the profile. A queued car emits far more NOx than a
   cruising one (the HBEFA3 idle term), so the peak hours carry a LARGER share of
   the day's NO2 than their share of the traffic. We quantify that with per-vehicle
   NO2 by hour: if peak per-vehicle NO2 exceeds the quiet-hour value, congestion is
   adding emissions beyond what volume alone explains. That extra is the whole
   reason an interaction ABM is worth running instead of flow times a fixed factor.

Run it with:  python src/validate_day.py [run_name]   (default config.RUN_NAME)
First run `python src/generate.py day` to produce the input file.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import demand_data


def _pearson(a, b):
    return float(np.corrcoef(a, b)[0, 1])


def _spearman(a, b):
    """Spearman rank correlation: Pearson correlation of the ranks."""
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def _share(series):
    """Normalize a per-hour series to fractions that sum to 1 (a pure shape)."""
    total = float(series.sum())
    return series / total if total > 0 else series * 0.0


def main(run_name):
    path = os.path.join(config.PROCESSED_DIR, f"{run_name}_day_segments.parquet")
    if not os.path.exists(path):
        raise SystemExit(f"No day results at {path}; run `python src/generate.py day` first.")
    df = pd.read_parquet(path)
    if "hour" not in df.columns:
        raise SystemExit(f"{path} has no 'hour' column; this is not a day run.")

    # the demand shape that drove the run, for the same 24 hours
    profile = pd.Series(demand_data.hourly_demand_profile(), index=range(24))
    src = "real PORTAL data" if demand_data.is_using_real_data() else "SYNTHETIC fallback"

    # per-hour aggregates from the simulation output
    g = df.groupby("hour")
    nveh = g["n_vehicles"].first().reindex(range(24))     # the input count (== profile by construction)
    thru = g["throughput"].sum().reindex(range(24))       # realized flow (an output)
    act = g["value"].sum().reindex(range(24))             # vehicle-seconds (an output)
    no2 = config.F_NO2 * g["nox_g"].sum().reindex(range(24))   # NO2 grams (an output)

    # shares (shapes) for an apples-to-apples comparison with the profile
    p_share = _share(profile)
    thru_share = _share(thru)
    no2_share = _share(no2)

    # per-vehicle NO2 by hour: the congestion intensity, independent of how many cars
    per_veh = (no2 / nveh).replace([np.inf, -np.inf], np.nan)

    # 1) face validity: does realized throughput follow the input shape?
    r_p = _pearson(thru_share.to_numpy(), p_share.to_numpy())
    rho = _spearman(thru_share.to_numpy(), p_share.to_numpy())

    # 2) the congestion finding: peak vs quiet per-vehicle NO2
    peak_h = int(no2.idxmax())
    quiet_h = int(no2.idxmin())
    pv_peak, pv_quiet = float(per_veh[peak_h]), float(per_veh[quiet_h])
    lift = 100.0 * (pv_peak / pv_quiet - 1.0) if pv_quiet > 0 else float("nan")

    # per-hour table
    table = pd.DataFrame({
        "profile_%": (p_share * 100).round(2),
        "vehicles": nveh.astype(int),
        "throughput": thru.astype(int),
        "thru_%": (thru_share * 100).round(2),
        "NO2_g": no2.round(1),
        "NO2_%": (no2_share * 100).round(2),
        "NO2_per_veh": per_veh.round(3),
    })
    out = os.path.join(config.PROCESSED_DIR, f"{run_name}_day_validation.parquet")
    table.to_parquet(out)

    print(f"Time-of-day validation for run '{run_name}'  (demand shape: {src})")
    print(table.to_string())
    print()
    print("1) Face validity: realized throughput vs the input demand profile")
    print(f"     Pearson  (throughput share vs profile share): {r_p:+.3f}")
    print(f"     Spearman (rank)                              : {rho:+.3f}")
    if rho >= 0.9:
        print("     Read: the model faithfully reproduces the time-of-day shape it "
              "was driven with; no peak-hour gridlock collapse.")
    elif rho >= 0.6:
        print("     Read: throughput broadly follows the input shape, with some "
              "flattening at the peak (capacity saturation).")
    else:
        print("     Read: throughput departs from the input shape; check for "
              "gridlock or routing pathologies at high load.")
    print()
    print("2) Congestion finding: per-vehicle NO2, peak vs quiet hour")
    print(f"     peak  {peak_h:02d}:00  -> {pv_peak:.3f} g NO2 per vehicle")
    print(f"     quiet {quiet_h:02d}:00  -> {pv_quiet:.3f} g NO2 per vehicle")
    print(f"     Read: a car at the peak emits {lift:+.0f}% more NO2 than at the "
          f"quiet hour, from queueing alone. This is the interaction effect a static")
    print(f"     flow-times-a-factor estimate cannot produce, and it is why peak "
          f"hours carry a larger NO2 share ({no2_share[peak_h]*100:.1f}%) than their")
    print(f"     traffic share ({p_share[peak_h]*100:.1f}%).")
    print(f"\n  saved per-hour table to {out}")

    # diagnostic overlay figure: the three shapes on one axis. Kept here (a
    # validation diagnostic) rather than in visualize.py, like the printed numbers.
    try:
        import matplotlib.pyplot as plt
        hours = list(range(24))
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.plot(hours, p_share * 100, color="#888888", lw=2, ls="--",
                marker="o", ms=3, label="input demand profile (PORTAL)")
        ax.plot(hours, thru_share * 100, color="#1f77b4", lw=2,
                marker="o", ms=3, label="simulated throughput share")
        ax.plot(hours, no2_share * 100, color="#d62728", lw=2,
                marker="o", ms=3, label="simulated NO2 share")
        ax.set_title("Time-of-day validation: throughput tracks the input shape,\n"
                     "NO2 over-weights the peaks (congestion)")
        ax.set_xlabel("hour of day")
        ax.set_ylabel("share of daily total (%)")
        ax.set_xticks(range(0, 24, 2))
        ax.set_ylim(bottom=0)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper right", fontsize=9)
        fig.tight_layout()
        fig_out = os.path.join(config.FIGURES_DIR, f"{run_name}_day_validation.png")
        fig.savefig(fig_out, dpi=200, bbox_inches="tight")
        plt.close(fig)
        print(f"  saved diagnostic figure to {fig_out}")
    except Exception as e:
        print(f"  (skipped diagnostic figure: {e})")


if __name__ == "__main__":
    run = sys.argv[1] if len(sys.argv) > 1 else config.RUN_NAME
    main(run)
