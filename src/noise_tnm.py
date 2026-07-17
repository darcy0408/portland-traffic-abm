"""FHWA TNM (REMEL) road-traffic noise surface, the US side of the comparison.

This is the deliberate mirror of src/noise.py (the CNOSSOS-EU surface), built to
the NOISE_TNM_DESIGN.md spec. It runs no simulation: it reads the SAME saved
per-segment run results, recovers the SAME congestion-aware speed, applies the
SAME flow term and the SAME line propagation, and swaps in exactly one thing:
the per-vehicle emission curve. CNOSSOS's category-1 source model is replaced by
the FHWA Traffic Noise Model's automobile REMEL (Reference Energy Mean Emission
Level). Every disagreement between the two output surfaces therefore traces to
the two countries' measured per-vehicle emission curves and their low-speed
behavior, which is the comparison the design isolates (design principle in
NOISE_TNM_DESIGN.md section 2).

-----------------------------------------------------------------------------
SOURCE MODEL (what is implemented)
-----------------------------------------------------------------------------
Reference: FHWA Traffic Noise Model, Version 1.0 Technical Manual (Menge,
Rossano, Anderson, Bajdek 1998; FHWA-PD-96-010, DOT-VNTSC-FHWA-98-2), Appendix A
"Vehicle Noise Emissions", equation (5). The REMEL is the energy-mean maximum
A-weighted pass-by sound level of one vehicle, measured at 15 m (50 ft), as a
function of speed s in km/h:

  E_A(s) = (0.6214 * s)^(A/10) * 10^(B/10) + 10^(C/10)
  L_E(s) = 10 * log10( E_A(s) )                       [dB(A) at 15 m]

The 0.6214 converts km/h to mph inside the fitted power law. The first term is
the moving (speed-dependent) noise; the 10^(C/10) term is a constant additive
energy floor, the vehicle's minimum (idle-like) level, so the curve levels off
at C as s -> 0 instead of diverging. That built-in floor is itself a structural
difference from CNOSSOS, whose rolling term keeps falling with log10(v) and
needs an application-rule speed floor (20 km/h in noise.py). The TNM 1.0 manual
states no separate validity speed range for the REMEL; the C constant IS the
low-speed behavior, so no artificial floor is applied here (design D5, resolved:
the manual was searched for a stated validity range and none exists; the FHWA
TNM 3.0 Technical Manual confirms the reading, describing C as "the minimum
level" and A as "the slope").

We use the built-in vehicle type "Automobiles" (two axles, four tires, the
passenger-car class), AVERAGE pavement, CRUISE throttle. That is the parity
match for the CNOSSOS category-1 cars-only v1 on the other side. Coefficients
(verification status in TNM_RESULTS.md; the constants below are FHWA's, from
the TNM Technical Manual constants table):

  A = 41.740807    (speed slope, shared by all automobile pavement rows)
  B = 1.148546     (average-pavement offset)
  C = 50.128316    (cruise-throttle minimum level)

Overall dB(A) only (design D3): the REMEL A/B/C give the overall A-weighted
level directly; the 1/3-octave spectral constants D1..J2 of equation (5) are
deliberately not implemented, matching the design's overall-level comparison.

-----------------------------------------------------------------------------
CONVERSION TO SOUND POWER (design D2)
-----------------------------------------------------------------------------
CNOSSOS works in per-vehicle sound POWER; the REMEL is a sound PRESSURE level at
15 m. To feed the REMEL into the same line-source machinery, back out a sound
power assuming hemispherical spreading over the ground plane (the half-space
geometry the REMEL was measured in: microphone 1.5 m high, 15 m to the side of
a vehicle on the ground):

  L_W = L_E + 10 * log10( 2 * pi * r^2 ),  r = 15 m   (about +31.5 dB)

The 2-pi (half space) vs 4-pi (free field) convention choice is worth 3 dB and
makes the ABSOLUTE offset between the two surfaces soft (design D4); the shape
of the comparison is the meaningful part.

-----------------------------------------------------------------------------
EVERYTHING ELSE IS IMPORTED FROM noise.py, NOT COPIED
-----------------------------------------------------------------------------
The run loader, the graph loader, the segment-length lookup, the receiver
distance, and the propagation function are imported from noise.py so "identical
steps 2 and 3" is enforced by construction. The recovered congestion-aware
speed and flow are not recomputed here either: this script calls
noise.build_noise_surface() and takes its q_vph / v_mean_mps columns as the
single source of truth, so both surfaces are guaranteed to see byte-identical
traffic. The flow term 10*log10(Q/(1000*v)) is the one CNOSSOS line-source
formula that operates per band in noise.py and per overall level here; it is
restated in one line below with the same constants.

Output: data/processed/<run>_noise_tnm.parquet with the same columns as the
CNOSSOS parquet plus noise_db renamed noise_tnm_db (and the CNOSSOS noise_db
kept alongside for convenience, since it comes for free).

Usage (standalone, like noise.py; no config.py changes by design):
  python src/noise_tnm.py            # uses config.RUN_NAME
  python src/noise_tnm.py <run_name>
"""
import os
import sys

import numpy as np

# make sibling modules importable whether run from repo root or from src/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import noise  # the CNOSSOS side; its loaders/propagation are reused verbatim


# --- FHWA TNM automobile REMEL constants ------------------------------------
# Vehicle type "Automobiles", AVERAGE pavement, CRUISE throttle, from the TNM
# Technical Manual constants table (Table 5 in the 1.0 manual / Table 10 in the
# 3.0 manual; the 1.0 ROSA P digitization is missing the table page, so the
# numeric values are taken from FHWA's TNM 3.0 Technical Manual, which
# reproduces the same emission database; see TNM_RESULTS.md for the full
# verification trail).
REMEL_A = 41.740807   # slope of the moving term against log10(speed in mph)
REMEL_B = 1.148546    # average-pavement level offset of the moving term
REMEL_C = 50.128316   # cruise-throttle constant energy floor (idle-like level)

# Reference geometry of the REMEL measurement: maximum pass-by level at 15 m.
REMEL_REF_DIST_M = 15.0

# km/h -> mph conversion baked into the fitted power law (1 km = 0.6214 mi).
KPH_TO_MPH = 0.6214

# D2 conversion: pressure level at 15 m -> sound power, assuming hemispherical
# (half-space) spreading over the ground plane the REMEL was measured above.
# 10*log10(2*pi*15^2) = 31.5 dB.
POWER_CONV_DB = 10.0 * np.log10(2.0 * np.pi * REMEL_REF_DIST_M ** 2)


def remel_dba(v_kph):
    """Automobile REMEL L_E(s): max pass-by dB(A) at 15 m for one car at v_kph.

    TNM Technical Manual eq. (5), overall A-weighted part. No speed floor is
    applied: the 10^(C/10) energy floor makes the curve level off at C dB(A)
    as speed -> 0, which is TNM's own low-speed behavior (design D5)."""
    v = np.asarray(v_kph, dtype=float)
    e_a = (KPH_TO_MPH * v) ** (REMEL_A / 10.0) * 10.0 ** (REMEL_B / 10.0) \
        + 10.0 ** (REMEL_C / 10.0)
    return 10.0 * np.log10(e_a)


def tnm_vehicle_power_dba(v_kph):
    """Per-vehicle A-weighted sound power (dB) implied by the REMEL at v_kph,
    via the D2 half-space conversion. This is the TNM analogue of the CNOSSOS
    A-weighted per-vehicle power, the quantity the two models are compared on."""
    return remel_dba(v_kph) + POWER_CONV_DB


def tnm_segment_line_power_dba(q_vph, v_kph):
    """A-weighted line-source sound power per metre for flow q_vph at v_kph.

    Same flow term as noise.segment_line_power_dba: Q/(1000*v) is the mean
    number of vehicles present per metre of road, using the TRUE (unfloored)
    speed, so a jam piles up more simultaneous sources exactly as on the
    CNOSSOS side. Returns None where there is no flow."""
    if q_vph <= 0 or v_kph <= 0:
        return None
    return tnm_vehicle_power_dba(v_kph) + 10.0 * np.log10(q_vph / (1000.0 * v_kph))


def build_noise_surface_tnm(run_name=None, dist_m=noise.RECEIVER_DIST_M):
    """Build the per-segment TNM-emission noise surface for one saved run.

    Calls noise.build_noise_surface() first, so the segment set, lengths, flows,
    and recovered congestion-aware speeds are the CNOSSOS surface's own numbers
    (identical input by construction, design D1), then computes the TNM level
    from those same q_vph / v_mean_mps with noise.propagate_line (identical
    propagation by construction, design D2). Returns that DataFrame with the
    CNOSSOS noise_db column kept and a new noise_tnm_db column added."""
    df = noise.build_noise_surface(run_name)

    tnm = np.full(len(df), np.nan)
    for i, r in enumerate(df.itertuples()):
        # same flow guard as the CNOSSOS loop: no flow -> silent (NaN)
        if not (r.q_vph > 0 and np.isfinite(r.v_mean_mps) and r.v_mean_mps > 0):
            continue
        lwa_per_m = tnm_segment_line_power_dba(r.q_vph, r.v_mean_mps * 3.6)
        if lwa_per_m is None:
            continue
        tnm[i] = noise.propagate_line(lwa_per_m, dist_m)  # imported, not copied
    df["noise_tnm_db"] = tnm
    return df


def main():
    """Build and save the TNM noise surface, with the design's sanity anchors.

    Reads the existing run parquet (via noise.py), writes
    data/processed/<run>_noise_tnm.parquet, prints summary stats plus the
    design section-7 sanity anchors so every run re-verifies them."""
    run = sys.argv[1] if len(sys.argv) > 1 else config.RUN_NAME
    surf = build_noise_surface_tnm(run)

    out = os.path.join(config.PROCESSED_DIR, f"{run}_noise_tnm.parquet")
    surf.to_parquet(out, index=False)

    lit = surf["noise_tnm_db"].dropna()
    print(f"Built TNM (REMEL) noise surface for '{run}': {len(surf)} segments, "
          f"{len(lit)} carry flow ({len(surf) - len(lit)} silent).")
    if len(lit):
        print(f"  dB(A) at {noise.RECEIVER_DIST_M:.0f} m receiver: "
              f"min {lit.min():.1f}, median {lit.median():.1f}, max {lit.max():.1f}")

    # sanity anchor 1 (design section 7): the implemented REMEL at round speeds.
    # These are the manual's own curve values to eyeball against Figure 7.
    print("  REMEL check L_E(s) at 15 m:",
          ", ".join(f"{s} km/h -> {remel_dba(s):.1f} dB(A)"
                    for s in (20, 50, 100)))
    # sanity anchor 2: implied per-vehicle sound power at 50 km/h vs the
    # CNOSSOS ledger anchor A2 (96 dB(A)). Tens of dB apart = units bug loose.
    cnossos_50 = 10.0 * np.log10(np.sum(10.0 ** (
        (noise.per_vehicle_band_power(50.0) + noise.A_WEIGHTING_DB) / 10.0)))
    print(f"  Anchor 2, per-vehicle A-weighted power at 50 km/h: "
          f"TNM {tnm_vehicle_power_dba(50.0):.1f} dB vs CNOSSOS {cnossos_50:.1f} dB")
    print(f"Saved to {out}")
    print("Compare the two surfaces with: python src/compare_noise.py "
          + ("" if run == config.RUN_NAME else run))


if __name__ == "__main__":
    main()
