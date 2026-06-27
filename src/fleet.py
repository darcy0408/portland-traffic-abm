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
import emissions  # the verified per-class HBEFA3 kernel; we never duplicate it here

# ILLUSTRATIVE default fleet, NOT Portland-calibrated. Uses only the two Euro-4 classes
# already present in emissions.HBEFA3_NOX_COEFFS. The 95/5 gasoline/diesel split is a
# rough US light-duty passenger-car figure, here only to show the mechanism and the
# direction of the effect (a gas-heavy fleet emits far less NOx than all-diesel). Replace
# with MOVES FIPS 41051 shares before citing any number. See module docstring.
DEFAULT_FLEET = [
    ("PC_G_EU4", 0.95),   # gasoline passenger car
    ("PC_D_EU4", 0.05),   # diesel passenger car (NOx-heavy minority)
]


def validate(mix):
    """Check a fleet mix is usable: known classes and shares summing to ~1.

    Fails loudly rather than silently renormalizing, so a typo in the shares (the
    most likely calibration mistake) is caught instead of quietly rescaled.
    """
    if not mix:
        raise ValueError("fleet mix is empty")
    unknown = [c for c, _ in mix if c not in emissions.HBEFA3_NOX_COEFFS]
    if unknown:
        raise ValueError(
            f"unknown HBEFA3 class(es) {unknown}; add their f0..f5 row to "
            "emissions.HBEFA3_NOX_COEFFS (copied from SUMO HelpersHBEFA3.cpp) first")
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
    return [(emissions.HBEFA3_NOX_COEFFS[c], share) for c, share in mix]


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
    """Show the mechanism and the direction of the effect: the illustrative gas-heavy
    fleet emits far less NOx per vehicle than the current all-diesel assumption. Run
    with `python src/fleet.py`. These numbers are illustrative (uncalibrated fleet)."""
    diesel_only = [emissions.HBEFA3_NOX_COEFFS["PC_D_EU4"]]
    mix = resolved(DEFAULT_FLEET)
    points = [(0.0, 0.0), (10.0, 0.0), (13.9, 0.0), (13.9, 1.0), (20.0, 0.0)]
    print("Illustrative fleet (uncalibrated):", DEFAULT_FLEET)
    print(f"{'v (m/s)':>8} {'a (m/s^2)':>10} {'all-diesel g/s':>16} "
          f"{'fleet g/s':>12} {'fleet/diesel':>13}")
    for v, a in points:
        d = emissions.nox_g_per_s(v, a, diesel_only[0])
        f = fleet_nox_g_per_s(v, a, mix)
        ratio = (f / d) if d > 0 else float("nan")
        print(f"{v:8.1f} {a:10.1f} {d:16.6f} {f:12.6f} {ratio:13.2f}")
    print("\nThe all-diesel assumption overstates NOx; a realistic mix lowers it. "
          "Replace DEFAULT_FLEET with MOVES FIPS 41051 shares before citing numbers.")


if __name__ == "__main__":
    _demo()


# INTEGRATION (after the Monday demo; do not wire in before, it moves cited numbers)
# ----------------------------------------------------------------------------------
# Expected-value path (simplest):
#   in generate.py, once before the step loop:   fleet = fleet.resolved(fleet.DEFAULT_FLEET)
#   replace   nox = emissions.nox_g_per_s(v, a, coeffs)
#   with      nox = fleet.fleet_nox_g_per_s(v, a, fleet)
# Stochastic path (heterogeneous agents):
#   at vehicle spawn:   veh.emission_class = fleet.sample_class(fleet.DEFAULT_FLEET, rng)
#   per step:           nox = emissions.nox_g_per_s(v, a, emissions.HBEFA3_NOX_COEFFS[veh.emission_class])
# Either way: add a config.FLEET_MIX knob (default = single-class for back-compat), pin the
# seed, and rerun generate.py once so the new NO2 numbers are authoritative before citing.
