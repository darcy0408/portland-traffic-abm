"""Offline PREVIEW of the mixed-fleet effect on the EXISTING NO2 surface (no sim).

Purpose: show, before the authoritative rerun, roughly how much the realistic
PORTLAND_FLEET (src/fleet.py) lowers the NO2 surface that was computed under the
current all-diesel (PC_D_EU4) assumption. It runs NO simulation and writes NO files:
it reads one saved run's per-segment parquet and prints a comparison. So it cannot
move any cited demo number, and it stays separate from the demo workstream.

HOW (and the approximation, stated honestly)
--------------------------------------------
The saved per-segment NOx (nox_g) was accumulated step by step over each vehicle's
real speed AND acceleration history, all as class PC_D_EU4. We do not have that
per-step (v, a) history offline, only the segment's realized MEAN speed, recovered
the same way noise.py does it:  v_mean = length * throughput / value.

So we reweight each segment's NOx by the fleet/diesel ratio evaluated at that mean
speed and ZERO acceleration (a cruise approximation):

    nox_fleet(segment) = nox_diesel(segment) * [ fleet_nox(v_mean, 0) / diesel_nox(v_mean, 0) ]

This is APPROXIMATE: it assumes the fleet/diesel ratio is roughly constant over the
segment's real (v, a) profile, and it ignores that idle and hard-acceleration steps
have a different ratio than cruise. It is a preview of direction and rough magnitude,
not the final answer. The EXACT per-segment fleet surface needs the one authoritative
generate.py rerun with fleet.py wired in (held until after Monday's demo). Treat these
numbers as "about this much, spatially like this," not as citable results.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import emissions
import fleet
# reuse noise.py's loaders and speed-recovery helpers rather than duplicate them
from noise import load_run_segments, load_network, _edge_length_and_name

# the current single-class assumption the saved surface was built with
DIESEL_COEFFS = fleet.HBEFA3_NOX[config.EMISSION_CLASS]


def fleet_diesel_ratio(v_mps, resolved_mix):
    """fleet/diesel NOx ratio at the given speed and zero acceleration. NaN if the
    diesel cruise rate is zero (no defined ratio)."""
    d = emissions.nox_g_per_s(v_mps, 0.0, DIESEL_COEFFS)
    if d <= 0:
        return np.nan
    return fleet.fleet_nox_g_per_s(v_mps, 0.0, resolved_mix) / d


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else config.RUN_NAME
    df = load_run_segments(run).copy()
    G = load_network()
    length, name = _edge_length_and_name(G)

    df["length_m"] = [length.get((r.u, r.v, r.key), np.nan) for r in df.itertuples()]
    df["street"] = [name.get((r.u, r.v, r.key)) for r in df.itertuples()]

    # congestion-aware realized mean speed (m/s), same recovery as noise.py
    flowing = (df["throughput"] > 0) & (df["value"] > 0)
    v_mean = np.full(len(df), np.nan)
    v_mean[flowing.to_numpy()] = (
        df.loc[flowing, "length_m"] * df.loc[flowing, "throughput"]
        / df.loc[flowing, "value"]
    ).to_numpy()
    df["v_mean_mps"] = v_mean

    mix = fleet.resolved(fleet.PORTLAND_FLEET)
    ratio = np.array([fleet_diesel_ratio(vi, mix) if np.isfinite(vi) else np.nan
                      for vi in df["v_mean_mps"]])
    df["ratio"] = ratio

    # apply the reweight; segments with no defined speed carry ~0 NOx anyway (no flow),
    # so reweighting them by the flow-weighted mean ratio changes nothing material
    valid = np.isfinite(ratio)
    flow_weighted_mean_ratio = float(np.average(ratio[valid],
                                                weights=df["nox_g"].to_numpy()[valid]))
    eff_ratio = np.where(valid, ratio, flow_weighted_mean_ratio)
    df["nox_diesel"] = df["nox_g"]
    df["nox_fleet"] = df["nox_g"] * eff_ratio

    # NO2 = F_NO2 * NOx (config), the same fraction the surface uses downstream
    f = config.F_NO2
    tot_d_nox = df["nox_diesel"].sum()
    tot_f_nox = df["nox_fleet"].sum()
    overall = tot_f_nox / tot_d_nox if tot_d_nox else float("nan")

    print(f"Mixed-fleet PREVIEW on existing run '{run}' (APPROXIMATE, no sim):")
    print(f"  fleet = PORTLAND_FLEET ({len(fleet.PORTLAND_FLEET)} classes), "
          f"baseline = all-{config.EMISSION_CLASS}")
    print()
    print(f"  network NOx  : diesel {tot_d_nox:10.1f} g  ->  fleet {tot_f_nox:10.1f} g")
    print(f"  network NO2  : diesel {f*tot_d_nox:10.1f} g  ->  fleet {f*tot_f_nox:10.1f} g"
          f"   (F_NO2={f})")
    print(f"  overall      : fleet is {overall:5.1%} of all-diesel  "
          f"(surface overstates NOx by ~{1/overall:.2f}x)")
    print()

    # how much the effect VARIES across segments (it depends on realized speed)
    r = df.loc[valid, "ratio"]
    print("  per-segment fleet/diesel ratio (varies with congestion-recovered speed):")
    print(f"    min {r.min():.2f} | median {r.median():.2f} | max {r.max():.2f}  "
          f"(lower ratio = bigger fleet correction)")
    print()

    # top streets by diesel NO2, with the fleet value beside them
    by_street = (df.dropna(subset=["street"])
                   .groupby("street")[["nox_diesel", "nox_fleet"]].sum())
    by_street["no2_diesel"] = f * by_street["nox_diesel"]
    by_street["no2_fleet"] = f * by_street["nox_fleet"]
    by_street["pct"] = (by_street["nox_fleet"] / by_street["nox_diesel"] - 1.0) * 100.0
    top = by_street.sort_values("no2_diesel", ascending=False).head(10)
    print("  top streets by NO2 (g), diesel vs fleet:")
    print(f"    {'street':<28}{'NO2 diesel':>12}{'NO2 fleet':>12}{'change':>9}")
    for street, row in top.iterrows():
        s = (street[:26] + "..") if len(str(street)) > 28 else str(street)
        print(f"    {s:<28}{row['no2_diesel']:>12.1f}{row['no2_fleet']:>12.1f}"
              f"{row['pct']:>8.0f}%")

    print()
    print("  APPROXIMATE preview only (cruise-ratio reweight; ignores per-step accel/idle).")
    print("  Exact surface needs the authoritative rerun with fleet.py wired in (post-demo).")


if __name__ == "__main__":
    main()
