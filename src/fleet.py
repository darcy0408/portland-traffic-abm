"""Mixed-vehicle-fleet NOx, composed from the verified per-class HBEFA3 kernel.

WHY THIS EXISTS
---------------
Right now every vehicle in the sim emits as a single class (config.EMISSION_CLASS,
currently PC_D_EU4, diesel Euro 4). That is the worst case for NOx: diesels are the
NOx problem, so an all-diesel fleet OVERSTATES the NO2 surface. A real Portland fleet
is mostly gasoline passenger cars with a diesel minority and some heavier vehicles.
Replacing the single class with a weighted mix sharpens the NO2 surface (the project's
headline output). It does NOT change traffic volumes, so it does not move the 0.33
traffic-count match: that is a separate, signal-timing question (DATASETS.md section 7).

This module is STANDALONE on purpose (scouted Jun 26, scaffolded before it is wired in):
it reuses emissions.nox_g_per_s and emissions.HBEFA3_NOX_COEFFS unchanged, so it adds no
risk to the existing single-class path and changes no committed numbers. It is ready to
wire into generate.py after the Monday demo, see "INTEGRATION" at the bottom.

WHAT A FLEET IS
---------------
A fleet mix is an ordered list of (hbefa3_class_name, share) pairs whose shares sum to 1.
Each class name must exist in emissions.HBEFA3_NOX_COEFFS, so we only ever compose
coefficients that were already verified against SUMO's HelpersHBEFA3.cpp. To add classes
beyond the two Euro-4 rows (other Euro standards, light trucks, heavy duty), copy their
f0..f5 rows from the same SUMO source into HBEFA3_NOX_COEFFS first, then reference them
here. Do not invent coefficients.

CALIBRATING THE SHARES (the real-data part, post-Monday)
--------------------------------------------------------
DEFAULT_FLEET below is an ILLUSTRATIVE placeholder (gas-dominant passenger split) so the
module runs and demonstrates the effect today. It is NOT calibrated to Portland. The
real shares come from the EPA MOVES county database for Multnomah County (FIPS 41051),
which gives the vehicle-type mix, the gasoline/diesel split (the `avft` table), and the
model-year/age distribution. Recipe and table names are in DATASETS.md section 7. Map
each MOVES (source type, fuel, age->Euro standard) bucket onto an HBEFA3 class, sum the
populations into shares, and drop them in here. How finely to resolve the diesel/heavy-duty
share is a Christof calibration decision, because those classes dominate per-vehicle NOx.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import emissions  # the verified per-class HBEFA3 polynomial kernel (nox_g_per_s); reused, never duplicated

# Full HBEFA3 NOx coefficient table (f0..f5), extracted verbatim Jun 26 from Eclipse SUMO
# src/utils/emissions/HelpersHBEFA3.cpp (static array myFunctionParameter, NOx is row index 4
# of the 6-row CO2/CO/HC/fuel/NOx/PMx block). Source:
# https://github.com/eclipse-sumo/sumo/blob/main/src/utils/emissions/HelpersHBEFA3.cpp
# This is a SUPERSET of emissions.HBEFA3_NOX_COEFFS: the PC_D_EU4 and PC_G_EU4 rows here
# match that module's two rows digit-for-digit (the extraction was validated against them),
# so fleet.py stays self-contained without editing emissions.py. We evaluate every row with
# emissions.nox_g_per_s, so the polynomial kernel itself is still single-sourced.
# CAVEAT: the bare max(poly/3.6, 0) form is validated for passenger cars (it reproduces
# emissions.py exactly). SUMO may apply a per-class scaling factor inside compute() for some
# heavy classes; if a heavy-vehicle surface is ever calibrated, check that factor. Documented
# simplification, fine for the light-duty-dominated Powell fleet.
HBEFA3_NOX = {
    # Passenger cars, gasoline
    "PC_G_EU0": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "PC_G_EU1": (30.63, 2.031, 0.0, -3.595, 0.2137, -0.002299),
    "PC_G_EU2": (23.05, 1.089, 0.0, -2.081, 0.06925, 0.0),
    "PC_G_EU3": (7.204, 0.3327, 0.0, -0.6641, 0.0215, 0.0),
    "PC_G_EU4": (4.336, 0.4428, 0.0, -0.3204, 0.01371, 0.0),
    "PC_G_EU5": (4.02, 0.4289, 0.0, -0.286, 0.01257, 0.0),
    "PC_G_EU6": (3.444, 0.4035, 0.0, -0.2313, 0.01086, 0.0),
    # Passenger cars, diesel (the NOx-heavy ones)
    "PC_D_EU0": (28.84, 5.756, 0.0, -1.228, 0.1234, 0.0),
    "PC_D_EU1": (43.38, 5.386, 0.0, -3.436, 0.1704, 0.0),
    "PC_D_EU2": (58.93, 5.709, 0.0, -5.174, 0.2186, 0.0),
    "PC_D_EU3": (65.19, 7.25, 0.0, -6.12, 0.2648, 0.0),
    "PC_D_EU4": (47.45, 4.011, 0.0, -4.061, 0.1619, 0.0),
    "PC_D_EU5": (46.01, 4.064, 0.0, -3.872, 0.1567, 0.0),
    "PC_D_EU6": (16.31, 1.39, 0.0, -1.391, 0.05512, 0.0),
    # Light commercial / delivery, gasoline
    "LDV_G_EU0": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "LDV_G_EU1": (19.35, 3.279, 0.0, 0.8384, 0.0, 0.001006),
    "LDV_G_EU2": (6.574, 1.161, 0.0, 0.3115, 0.0, 0.0003318),
    "LDV_G_EU3": (0.5866, 0.2926, 0.0, 0.1955, 0.0, 0.0),
    "LDV_G_EU4": (1.1, 0.1892, 0.0, 0.08809, 0.0, 0.0),
    "LDV_G_EU5": (1.101, 0.1824, 0.0, 0.08517, 0.0, 0.0),
    "LDV_G_EU6": (1.109, 0.1806, 0.0, 0.08319, 0.0, 0.0),
    # Light commercial / delivery, diesel
    "LDV_D_EU0": (53.84, 11.77, 0.0, -3.702, 0.3365, 0.0),
    "LDV_D_EU1": (45.13, 10.42, 0.0, -2.941, 0.2852, 0.0),
    "LDV_D_EU2": (42.83, 9.371, 0.0, -2.973, 0.2623, 0.0),
    "LDV_D_EU3": (33.02, 6.747, 1.706, -1.94, 0.1688, 0.0),
    "LDV_D_EU4": (40.68, 6.272, 0.0, -3.613, 0.2148, 0.0),
    "LDV_D_EU5": (38.6, 6.079, 0.0, -3.414, 0.2026, 0.0),
    "LDV_D_EU6": (13.57, 2.119, 0.0, -1.211, 0.07068, 0.0),
    # Heavy-duty, urban bus, coach (diesel unless noted); f4 (v^2) is 0.0 in source
    "Bus": (218.7, 46.17, 0.0, 11.27, 0.0, 0.0),
    "Coach": (226.7, 60.86, 0.0, 16.97, 0.0, 0.0),
    "HDV": (305.6, 55.28, 0.0, 9.505, 0.0, 0.0),
    "HDV_G": (53.53, 33.43, 0.0, 11.47, 0.0, 0.007806),
    "HDV_D_EU0": (428.6, 104.2, 0.0, 24.18, 0.0, 0.0),
    "HDV_D_EU1": (299.3, 67.56, 0.0, 14.89, 0.0, 0.0),
    "HDV_D_EU2": (298.4, 67.21, 0.0, 15.36, 0.0, 0.0),
    "HDV_D_EU3": (241.1, 51.57, 0.0, 11.42, 0.0, 0.0),
    "HDV_D_EU4": (202.2, 42.34, 0.0, 8.858, 0.0, 0.0),
    "HDV_D_EU5": (164.8, 33.84, 0.0, 7.036, 0.0, 0.0),
    "HDV_D_EU6": (47.47, 11.68, 0.0, 2.737, 0.0, 0.0),
    # Battery-electric / zero-emission: explicit all-zero row (NOT from HBEFA3), so an EV
    # fleet share contributes a physically correct zero tailpipe NOx to the average.
    "BEV": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
}

# ILLUSTRATIVE default fleet, NOT Portland-calibrated. The 95/5 gasoline/diesel split is a
# rough US light-duty passenger-car figure, here only to show the mechanism and the
# direction of the effect (a gas-heavy fleet emits far less NOx than all-diesel). Replace
# with PORTLAND_FLEET (real Multnomah FIPS 41051 shares) before citing any number; that fleet
# is assembled from the data hunt in DATASETS.md section 7. See module docstring.
DEFAULT_FLEET = [
    ("PC_G_EU4", 0.95),   # gasoline passenger car
    ("PC_D_EU4", 0.05),   # diesel passenger car (NOx-heavy minority)
]

# PORTLAND_FLEET: a real, sourced Multnomah-County (FIPS 41051) traffic mix, assembled Jun 26
# from the data hunt (DATASETS.md section 7). Shares are TRAFFIC-weighted (what feeds the
# emission surface), not registration-weighted, and sum to 1.00. Provenance, honestly flagged:
#   - Type split (~95% light-duty passenger, ~5% rest): Oregon DMV 2022 registrations,
#     Multnomah row. LOCAL. Caveat: DMV "passenger" lumps cars + personal light trucks/SUVs.
#   - Diesel ~5% of light-duty: Oregon AFDC 2024 (statewide 6.6%) interpolated toward an urban
#     value. OREGON-derived, not Multnomah-measured.
#   - Age/standard bands (newest ~33%, mid ~38%, old ~14%): US national average age ~12.5 yr.
#     NATIONAL DEFAULT. EPA MOVES has an exact Multnomah age table to swap in later.
#   - Commercial/heavy ~5.4%: REAL LOCAL data, PBOT layer 253 "Vehicle Class Counts", 2014
#     counts on SE Powell at SE 28th (volume-weighted %Trucks = 5.4%). Crucially TwoAxleCF~0.99,
#     so ~99% are TWO-AXLE light commercial (delivery vans), NOT heavy multi-axle: mapped mostly
#     to LDV_D. Genuine heavy multi-axle is ~0.05% (HDV, a sliver). A small transit-bus share is
#     kept explicit because TriMet runs Powell frequently and buses are NOx-heavy (buses are
#     2-axle, so they hide inside this count; naming them is deliberate). The exact LDV/HDV/Bus
#     split inside the 5.4% is a Christof calibration knob.
#   - EV ~3%: zero tailpipe NOx (mapped to the BEV zero row).
# The NOx-critical buckets are the diesel cars (5%) and the commercial/bus diesel (~5.4%, now
# mostly light-commercial per the Powell class count): together the majority of fleet NOx, kept
# as distinct classes on purpose. Motorcycles (~1% of traffic) are folded into old gasoline as a
# documented simplification (no MC class extracted; minor NOx). These shares are the Christof
# calibration knob; tighten further with the MOVES 41051 age table and the layer-253 axle split.
PORTLAND_FLEET = [
    ("PC_G_EU6", 0.33),    # newest gasoline passenger car (Tier 3 ~ Euro 6)
    ("PC_G_EU5", 0.196),   # mid-age gasoline (+0.006 rebalance, see note below)
    ("PC_G_EU4", 0.19),    # mid/older gasoline
    ("PC_G_EU3", 0.15),    # old gasoline (+ ~1% motorcycle folded in as gasoline)
    ("PC_D_EU5", 0.03),    # diesel passenger car, Euro 5  (NOx-critical)
    ("PC_D_EU6", 0.02),    # diesel passenger car, Euro 6  (NOx-critical)
    ("BEV",      0.03),    # battery-electric, zero tailpipe NOx
    ("LDV_D_EU5", 0.045),  # two-axle light commercial diesel (bulk of Powell's ~5.4% trucks)
    ("HDV_D_EU5", 0.004),  # genuine heavy multi-axle diesel (~0.05% on Powell, a sliver)
    ("Bus",       0.005),  # TriMet diesel transit bus (NOx-heavy; named deliberately)
]
# Rebalanced PC_G_EU5 0.19 -> 0.196 to keep the shares summing to 1.00 after the layer-253
# commercial split (the freed share goes back to the dominant mid-age gasoline bucket).


def validate(mix):
    """Check a fleet mix is usable: known classes and shares summing to ~1.

    Fails loudly rather than silently renormalizing, so a typo in the shares (the
    most likely calibration mistake) is caught instead of quietly rescaled.
    """
    if not mix:
        raise ValueError("fleet mix is empty")
    unknown = [c for c, _ in mix if c not in HBEFA3_NOX]
    if unknown:
        raise ValueError(
            f"unknown HBEFA3 class(es) {unknown}; add their f0..f5 row to "
            "fleet.HBEFA3_NOX (copied from SUMO HelpersHBEFA3.cpp) first")
    total = sum(share for _, share in mix)
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"fleet shares sum to {total:.6f}, not 1.0")
    bad = [(c, s) for c, s in mix if s < 0.0]
    if bad:
        raise ValueError(f"negative share(s): {bad}")


def resolved(mix):
    """Turn a fleet mix into [(coeffs_tuple, share), ...] for the hot loop.

    Resolve the class-name -> coefficient lookup ONCE, before any per-step loop, the
    same pattern emissions.active_coeffs() uses for the single-class path.
    """
    validate(mix)
    return [(HBEFA3_NOX[c], share) for c, share in mix]


def fleet_nox_g_per_s(v_mps, a_mps2, resolved_mix):
    """Expected NOx (g/s) for one vehicle drawn from the fleet, at this (v, a).

    The share-weighted average of the per-class HBEFA3 rates. This is the simplest
    drop-in: every vehicle emits the fleet-average rate, so no per-vehicle state is
    needed and the segment total is just the existing accumulation with this function
    swapped in. `resolved_mix` is the output of resolved(); pass it in, do not rebuild
    it each call.
    """
    return sum(share * emissions.nox_g_per_s(v_mps, a_mps2, coeffs)
               for coeffs, share in resolved_mix)


def sample_class(mix, rng):
    """Draw one HBEFA3 class name from the fleet distribution (stochastic path).

    Use this if you prefer heterogeneous agents over the expected-value path: assign
    each vehicle a class at spawn with this, store it on the vehicle, and emit with
    that class's coeffs for the whole trip. More ABM-faithful (real fleets are discrete
    vehicles, not an averaged blend) but it needs a per-vehicle attribute wired into
    generate.py and a seeded rng for reproducibility. `rng` is a numpy Generator or any
    object with .random(); pin it off config.SEED so runs reproduce.
    """
    validate(mix)
    r = rng.random()
    cumulative = 0.0
    for class_name, share in mix:
        cumulative += share
        if r < cumulative:
            return class_name
    return mix[-1][0]   # guard against float rounding at the top of the range


def _demo():
    """Quantify the effect offline (no sim): the realistic Portland fleet emits far less
    NOx per vehicle than the current all-diesel (PC_D_EU4) assumption, so today's NO2
    surface is an UPPER BOUND. Run with `python src/fleet.py`."""
    diesel_only = HBEFA3_NOX["PC_D_EU4"]    # the current single-class assumption
    portland = resolved(PORTLAND_FLEET)
    points = [(0.0, 0.0), (10.0, 0.0), (13.9, 0.0), (13.9, 1.0), (20.0, 0.0)]
    print("PORTLAND_FLEET (sourced, traffic-weighted):")
    for c, s in PORTLAND_FLEET:
        print(f"    {c:>10}  {s:>5.2f}")
    print(f"\n{'v (m/s)':>8} {'a (m/s^2)':>10} {'all-diesel g/s':>16} "
          f"{'fleet g/s':>12} {'fleet/diesel':>13}")
    ratios = []
    for v, a in points:
        d = emissions.nox_g_per_s(v, a, diesel_only)
        f = fleet_nox_g_per_s(v, a, portland)
        ratio = (f / d) if d > 0 else float("nan")
        ratios.append(ratio)
        print(f"{v:8.1f} {a:10.1f} {d:16.6f} {f:12.6f} {ratio:13.2f}")
    avg = sum(r for r in ratios if r == r) / sum(1 for r in ratios if r == r)
    print(f"\nAcross these (v,a) points the realistic fleet emits ~{avg:.0%} of the "
          "all-diesel NOx, i.e. the current surface overstates NOx by roughly "
          f"{1/avg:.1f}x. Exact per-segment effect needs the one authoritative rerun "
          "(post-Monday); these are per-vehicle point comparisons.")


if __name__ == "__main__":
    _demo()


# INTEGRATION (after the Monday demo; do not wire in before, it moves cited numbers)
# ----------------------------------------------------------------------------------
# Expected-value path (simplest, recommended for the surface):
#   in generate.py, once before the step loop:   mix = fleet.resolved(fleet.PORTLAND_FLEET)
#   replace   nox = emissions.nox_g_per_s(v, a, coeffs)
#   with      nox = fleet.fleet_nox_g_per_s(v, a, mix)
# Stochastic path (heterogeneous agents):
#   at vehicle spawn:   veh.emission_class = fleet.sample_class(fleet.PORTLAND_FLEET, rng)
#   per step:           nox = emissions.nox_g_per_s(v, a, fleet.HBEFA3_NOX[veh.emission_class])
# Either way: add a config.FLEET_MIX knob (default = single-class for back-compat), pin the
# seed, and rerun generate.py once so the new NO2 numbers are authoritative before citing.
