"""Per-vehicle driver heterogeneity for the IDM (traffic-realism Phase 2).

WHY THIS EXISTS
---------------
The base model gives every vehicle the single config IDM parameter set
(IDM_A_MAX, IDM_B_COMF, IDM_T, IDM_S0, and each segment's speed limit as the
desired speed). So every car on a given segment is dynamically identical and the
segment's speed VARIANCE is exactly zero. Real drivers differ: some accept a
higher desired speed, keep shorter headways, accelerate harder. This module draws
a per-vehicle IDM parameter set at spawn so a population of drivers disperses on
open road and each segment carries a real speed spread.

That spread is the point, not decoration: CNOSSOS road-noise emission is nonlinear
in speed, so two segments with the same MEAN speed but different speed VARIANCE
emit different noise. The homogeneous model cannot produce that; this can. It also
quantifies one of the three named model limitations (homogeneous drivers) as a
switchable, measurable feature.

METHOD
------
Treiber & Kesting's recommended heterogeneity approach: multiply each IDM
parameter by a driver-specific factor drawn from a Gaussian centered on 1. Here
each factor is N(1, sigma) truncated to [1 - 2*sigma, 1 + 2*sigma] (clamped, a
documented minor simplification -- the ~4.6% of mass past 2 sigma piles onto the
bounds; the exact tail shape is not load-bearing). Truncation keeps every drawn
parameter strictly positive and bounds the desired-speed spread so Gate B stays
hand-predictable. Each parameter has its own sigma in config.

DISCIPLINE (mirrors fleet.py, so the two heterogeneity layers behave alike)
---------------------------------------------------------------------------
- OFF by default (config.DRIVER_HETEROGENEITY). When off, generate.py attaches no
  per-vehicle params and every vehicle uses the config defaults: the committed
  base model, bitwise unchanged, so no cited number moves.
- Drawn from a DEDICATED seeded RNG stream (config.RANDOM_SEED + 3), separate from
  the trip stream (SEED), the signal stream (SEED + 1) and the fleet stream
  (SEED + 2). Turning heterogeneity on therefore consumes no trip/route/fleet
  draw: the same seed gives the same INITIAL vehicle population (identical spawn
  order, origins, destinations, routes) and leaves every other stream aligned.
  It does NOT leave the realized traffic identical, and must not be described
  that way: changed dynamics change when vehicles finish their trips, which
  shifts respawn timing, which hands later vehicles different trip draws. That
  divergence is the effect being measured, not a leak -- the stream separation
  buys a controlled comparison (same starting population, one mechanism changed),
  not a fixed traffic realization. Contrast fleet.py, where the same discipline
  DOES leave traffic bit-identical, because fleet draws touch only emission
  chemistry and never the dynamics.
- With every sigma 0 each factor is EXACTLY 1.0 (no rng draw consumed), so the
  drawn parameter set is exactly the config defaults and the machinery is provably
  inert (Gate A: src/driver_scenarios.py).
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# The IDM parameters that vary, each with its own config sigma (a FRACTIONAL
# standard deviation: sigma 0.12 means a ~12% spread in that parameter). "v0" is
# the desired-speed multiplier, applied per-segment to that segment's speed limit;
# the other four scale the absolute IDM values. Iteration order is fixed, so the
# per-vehicle draw sequence is deterministic given the seed.
PARAMS = ("v0", "a_max", "b_comf", "T", "s0")


def sigmas():
    """Per-parameter fractional standard deviations, read from config. A sigma of
    0 freezes that parameter at its config default (that factor is not drawn)."""
    return {
        "v0":     config.DRIVER_SIGMA_V0,
        "a_max":  config.DRIVER_SIGMA_A,
        "b_comf": config.DRIVER_SIGMA_B,
        "T":      config.DRIVER_SIGMA_T,
        "s0":     config.DRIVER_SIGMA_S0,
    }


def validate(sig):
    """Fail loudly on an unusable sigma set, rather than silently misbehaving:
    unknown parameter, negative sigma, or a sigma >= 0.5 (which would push the
    truncated factor's lower bound 1 - 2*sigma to <= 0 and hand a car a
    nonpositive IDM parameter)."""
    unknown = [p for p in sig if p not in PARAMS]
    if unknown:
        raise ValueError(f"unknown driver parameter(s) {unknown}; known: {PARAMS}")
    bad = {p: s for p, s in sig.items() if s < 0.0}
    if bad:
        raise ValueError(f"negative driver sigma(s): {bad}")
    big = {p: s for p, s in sig.items() if s >= 0.5}
    if big:
        raise ValueError(
            f"driver sigma(s) >= 0.5 would make a truncated factor <= 0: {big}")


def _factor(rng, sigma):
    """One multiplicative factor ~ N(1, sigma), truncated to [1-2s, 1+2s].

    sigma == 0 returns exactly 1.0 WITHOUT consuming an rng draw, so an all-zero
    sigma set advances the driver stream not at all and yields the config defaults
    bit-for-bit (the inertness guarantee). `rng` is a random.Random (its .gauss),
    pinned off config.RANDOM_SEED + 3 by the caller so runs reproduce.
    """
    if sigma == 0.0:
        return 1.0
    z = rng.gauss(0.0, 1.0)
    return min(max(1.0 + sigma * z, 1.0 - 2.0 * sigma), 1.0 + 2.0 * sigma)


def sample(rng, sig=None):
    """Draw one vehicle's IDM parameters from the truncated-Gaussian factors.

    Returns a dict ready to hand to generate.step_vehicles / idm_acceleration:
        {"v0_factor", "a_max", "b_comf", "T", "s0"}
    v0 stays a FACTOR (the desired-speed multiplier, applied per segment to that
    segment's speed limit, since the limit differs edge to edge); the other four
    are ABSOLUTE values (config default * drawn factor). With every sigma 0 the
    dict equals the config defaults exactly.

    `sig` defaults to sigmas() from config; pass an explicit dict to isolate one
    parameter in a scenario. Draw order follows PARAMS, so the stream is
    deterministic.
    """
    sig = sigmas() if sig is None else sig
    f = {p: _factor(rng, sig[p]) for p in PARAMS}
    return {
        "v0_factor": f["v0"],                     # desired-speed multiplier (per-segment)
        "a_max":  config.IDM_A_MAX  * f["a_max"],
        "b_comf": config.IDM_B_COMF * f["b_comf"],
        "T":      config.IDM_T      * f["T"],
        "s0":     config.IDM_S0     * f["s0"],
    }


def _demo():
    """Quantify the desired-speed spread offline (no sim). Run: python src/drivers.py"""
    import random
    sig = sigmas()
    validate(sig)
    rng = random.Random(config.RANDOM_SEED + 3)
    n = 2000
    draws = [sample(rng, sig) for _ in range(n)]
    facs = sorted(d["v0_factor"] for d in draws)
    mean = sum(facs) / n
    var = sum((x - mean) ** 2 for x in facs) / n
    print(f"driver heterogeneity sigmas: {sig}")
    print(f"\n{n} v0-factor draws (sigma_v0 = {sig['v0']}):")
    print(f"  min {facs[0]:.3f}  p10 {facs[n//10]:.3f}  mean {mean:.3f}  "
          f"p90 {facs[9*n//10]:.3f}  max {facs[-1]:.3f}  sd {var**0.5:.3f}")
    print(f"  truncation bounds: [{1-2*sig['v0']:.3f}, {1+2*sig['v0']:.3f}]")
    print("\nA 50 km/h (13.9 m/s) segment therefore carries desired speeds from "
          f"~{13.9*facs[0]:.1f} to ~{13.9*facs[-1]:.1f} m/s across drivers, so its "
          "speed variance is nonzero -- the input the CNOSSOS noise nonlinearity needs.")


if __name__ == "__main__":
    _demo()
