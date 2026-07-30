"""Hand-checkable scenarios for the Webster signal-timing DECISION (Phase 4,
increment 1). Same discipline as scenarios.py / lanes_scenarios.py /
driver_scenarios.py / mobil_scenarios.py: each scenario's expected cycle and
split is derived BY HAND (shown as exact rational arithmetic in the comments,
using fractions.Fraction so the expectation is computed independently of
src/webster.py, not by re-running the same code) and then checked against the
REAL `webster.cycle_and_split`. The module is pure arithmetic, so there is no
excuse for loose tolerances: everything is asserted to within 1e-9 of the exact
closed-form value, and several exactly-clamped/degenerate cases are asserted
bit-for-bit.

Five cases:
  1. SYMMETRIC     equal EW/NS flow -> split exactly 0.5 by symmetry; the
                    unclamped optimal cycle (29.36 s) is below cycle_min_s, so
                    the clamp fires and the returned cycle is exactly 30.0.
  2. ASYMMETRIC     the headline result: a heavy EW approach gets MORE than half
                    the cycle, and the exact split is asserted (not just >0.5).
  3. OVERSATURATED  Y >= 1: the optimal-cycle formula has no valid answer, so
                    the fallback (cycle_max_s) fires; the split stays finite and
                    proportional to the flow ratios.
  4. FLOORS         a starved approach's Webster-optimal green undercuts
                    min_green_s and gets raised to the floor (its partner
                    shrinks by the same amount); with zero demand on both
                    phases the degenerate (cycle_min_s, 0.5) case fires.
  5. CRITICAL       an iterable of per-approach flows behaves exactly like a
                    scalar equal to their max (the critical approach governs).

Run: python src/webster_scenarios.py
"""
import math
import os
import sys
from fractions import Fraction as F

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import webster

PASS, FAIL = "PASS", "FAIL"
TOL = 1e-9

# Shared a-priori constants (mirror config.WEBSTER_* defaults; hardcoded here so
# the gate does not depend on config.py's values ever changing under it).
SAT = 1900.0
LOST = 4.0
CMIN = 30.0
CMAX = 120.0
MING = 7.0


def _check(label, ok, detail):
    print(f"   [{PASS if ok else FAIL}] {label}: {detail}")
    return bool(ok)


def _close(actual, expected, tol=TOL):
    return abs(actual - expected) < tol


def scenario_symmetric():
    print("\n1) SYMMETRIC: equal EW/NS flow -> split exactly 0.5, clamp fires")
    print("   400 veh/h each side, sat flow 1900 veh/h/lane, lost time 4 s/phase.")
    print("   y = 400/1900 = 4/19 on both phases, Y = 8/19.")
    print("   L = 2*4 = 8.  C0 = (1.5*8+5)/(1-8/19) = 17/(11/19) = 323/11 = 29.36 s,")
    print("   which is BELOW cycle_min_s (30.0), so the clamp raises it to 30.0.")
    cycle, split = webster.cycle_and_split(400.0, 400.0, sat_flow=SAT,
                                           lost_time_s=LOST, cycle_min_s=CMIN,
                                           cycle_max_s=CMAX, min_green_s=MING)
    y = F(400, 1900)
    Y = 2 * y
    L = 2 * F(int(LOST))
    unclamped_c0 = (F(3, 2) * L + 5) / (1 - Y)
    print(f"   unclamped C0 = {float(unclamped_c0):.4f} s (hand: 29.3636...)")
    print(f"   actual: cycle={cycle:.6f} s, split_ew={split:.6f}")
    ok = [_check("clamp fires: cycle == cycle_min_s exactly", cycle == CMIN,
                 f"cycle = {cycle}"),
          _check("split == 0.5 exactly (symmetric flows)", split == 0.5,
                 f"split_ew = {split}")]
    return all(ok)


def scenario_asymmetric():
    print("\n2) ASYMMETRIC: heavy EW (700) vs light NS (300) -> EW gets MORE green")
    print("   y_ew = 700/1900 = 7/19, y_ns = 300/1900 = 3/19, Y = 10/19.")
    print("   L = 8.  C0 = 17/(1-10/19) = 17/(9/19) = 323/9 = 35.8889 s (no clamp).")
    print("   g_tot = C0 - 8 = 251/9.  g_ew = g_tot*(7/10) = 1757/90 = 19.5222 s,")
    print("   g_ns = g_tot*(3/10) = 251/30 = 8.3667 s (both clear the 7.0 s floor).")
    print("   split_ew = (g_ew + 4) / C0 = (2117/90)/(323/9) = 2117/3230 = 0.655418.")
    cycle, split = webster.cycle_and_split(700.0, 300.0, sat_flow=SAT,
                                           lost_time_s=LOST, cycle_min_s=CMIN,
                                           cycle_max_s=CMAX, min_green_s=MING)
    y_ew, y_ns = F(700, 1900), F(300, 1900)
    Y = y_ew + y_ns
    L = 2 * F(int(LOST))
    c0 = (F(3, 2) * L + 5) / (1 - Y)
    g_tot = c0 - L
    g_ew = g_tot * (y_ew / Y)
    expected_split = (g_ew + F(int(LOST))) / c0
    print(f"   actual: cycle={cycle:.6f} s (hand: {float(c0):.6f}), "
          f"split_ew={split:.9f} (hand: {float(expected_split):.9f})")
    ok = [_check("cycle matches hand-derived C0", _close(cycle, float(c0)),
                 f"|{cycle} - {float(c0)}| < {TOL}"),
          _check("EW split strictly > 0.5 (heavy approach favored)", split > 0.5,
                 f"split_ew = {split}"),
          _check("split matches hand-derived exact value",
                 _close(split, float(expected_split)),
                 f"|{split} - {float(expected_split)}| < {TOL}")]
    return all(ok)


def scenario_oversaturated():
    print("\n3) OVERSATURATED: Y >= 1 -> cycle falls back to cycle_max_s")
    print("   EW at exactly saturation (1900 veh/h, y_ew = 1) plus NS 1000 veh/h")
    print("   (y_ns = 10/19). Y = 1 + 10/19 = 29/19 >= 1: Webster's (1-Y) denominator")
    print("   is negative, so the optimal-cycle formula is invalid; the fallback")
    print("   (cycle_max_s = 120.0) fires. g_tot = 120-8 = 112, split still")
    print("   proportional: g_ew = 112*(1/(29/19)) = 2128/29 = 73.379 s,")
    print("   split_ew = (2128/29+4)/120 = 2244/3480 = 187/290 = 0.644828.")
    cycle, split = webster.cycle_and_split(1900.0, 1000.0, sat_flow=SAT,
                                           lost_time_s=LOST, cycle_min_s=CMIN,
                                           cycle_max_s=CMAX, min_green_s=MING)
    expected_split = F(187, 290)
    print(f"   actual: cycle={cycle:.6f} s, split_ew={split:.9f} "
          f"(hand: {float(expected_split):.9f})")
    ok = [_check("cycle == cycle_max_s exactly", cycle == CMAX, f"cycle = {cycle}"),
          _check("split is finite", math.isfinite(split), f"split_ew = {split}"),
          _check("split matches hand-derived proportional value",
                 _close(split, float(expected_split)),
                 f"|{split} - {float(expected_split)}| < {TOL}")]
    return all(ok)


def scenario_floors():
    print("\n4) FLOORS: a starved approach is raised to min_green_s; zero demand")
    print("   -> (cycle_min_s, 0.5)")
    print("   4a) EW 900, NS 20 veh/h. y_ew = 9/19, y_ns = 1/95, Y = 46/95.")
    print("       L=8, C0 = 17/(49/95) = 1615/49 = 32.9592 s (no clamp).")
    print("       g_tot = 1223/49. Unfloored g_ns = g_tot*(1/46) = 1223/2254 = 0.543 s")
    print("       -- under the 7.0 s floor. NS is raised to exactly 7.0 s and EW")
    print("       absorbs the deficit: g_ew = 1223/49 - 7 = 880/49 = 17.9592 s.")
    print("       split_ew = (880/49+4)/(1615/49) = 1076/1615 = 0.666254.")
    cycle_a, split_a = webster.cycle_and_split(900.0, 20.0, sat_flow=SAT,
                                               lost_time_s=LOST, cycle_min_s=CMIN,
                                               cycle_max_s=CMAX, min_green_s=MING)
    c0 = F(1615, 49)
    expected_split_a = F(1076, 1615)
    # Recover the implied g_ns from the returned split to check the FLOOR itself
    # fired (not just the aggregate number): g_ew = split*cycle - lost_time_s,
    # g_ns = (cycle - L) - g_ew.
    g_ew_actual = split_a * cycle_a - LOST
    g_ns_actual = (cycle_a - 2 * LOST) - g_ew_actual
    print(f"   actual: cycle={cycle_a:.6f} s (hand: {float(c0):.6f}), "
          f"split_ew={split_a:.9f} (hand: {float(expected_split_a):.9f}), "
          f"implied g_ns={g_ns_actual:.6f} s")

    print("   4b) Zero flow on both phases -> degenerate case: (cycle_min_s, 0.5).")
    cycle_b, split_b = webster.cycle_and_split(0.0, 0.0, sat_flow=SAT,
                                               lost_time_s=LOST, cycle_min_s=CMIN,
                                               cycle_max_s=CMAX, min_green_s=MING)
    print(f"   actual: cycle={cycle_b}, split_ew={split_b}")

    ok = [_check("4a cycle matches hand-derived C0", _close(cycle_a, float(c0)),
                 f"|{cycle_a} - {float(c0)}| < {TOL}"),
          _check("4a split matches hand-derived floored value",
                 _close(split_a, float(expected_split_a)),
                 f"|{split_a} - {float(expected_split_a)}| < {TOL}"),
          _check("4a NS green raised to exactly min_green_s",
                 _close(g_ns_actual, MING),
                 f"g_ns = {g_ns_actual}, min_green_s = {MING}"),
          _check("4b cycle == cycle_min_s exactly", cycle_b == CMIN,
                 f"cycle = {cycle_b}"),
          _check("4b split == 0.5 exactly (no demand)", split_b == 0.5,
                 f"split_ew = {split_b}")]
    return all(ok)


def scenario_critical_approach():
    print("\n5) CRITICAL APPROACH: an iterable of per-approach flows behaves")
    print("   exactly like a scalar equal to their max (the critical approach")
    print("   governs, not a sum or an average).")
    print("   flows_ew = [300, 700] must produce the IDENTICAL result to")
    print("   flows_ew = 700 (max(300, 700) == 700), against a fixed NS = 400.")
    cycle_iter, split_iter = webster.cycle_and_split([300.0, 700.0], 400.0,
                                                      sat_flow=SAT, lost_time_s=LOST,
                                                      cycle_min_s=CMIN, cycle_max_s=CMAX,
                                                      min_green_s=MING)
    cycle_scalar, split_scalar = webster.cycle_and_split(700.0, 400.0, sat_flow=SAT,
                                                         lost_time_s=LOST, cycle_min_s=CMIN,
                                                         cycle_max_s=CMAX, min_green_s=MING)
    print(f"   iterable [300,700]: cycle={cycle_iter:.9f}, split_ew={split_iter:.9f}")
    print(f"   scalar    700     : cycle={cycle_scalar:.9f}, split_ew={split_scalar:.9f}")
    ok = [_check("cycle identical (bitwise)", cycle_iter == cycle_scalar,
                 f"{cycle_iter} == {cycle_scalar}"),
          _check("split identical (bitwise)", split_iter == split_scalar,
                 f"{split_iter} == {split_scalar}")]
    return all(ok)


if __name__ == "__main__":
    print("Webster signal-timing decision scenarios  (pure arithmetic, hand-checkable)")
    print("=" * 76)
    results = {
        "symmetric -> split 0.5, cycle clamped": scenario_symmetric(),
        "asymmetric -> heavy approach favored": scenario_asymmetric(),
        "oversaturated -> cycle_max_s fallback": scenario_oversaturated(),
        "floors -> min_green_s / zero-demand degenerate case": scenario_floors(),
        "critical approach -> max of an iterable": scenario_critical_approach(),
    }
    print("\n" + "=" * 76)
    for name, ok in results.items():
        print(f"   {PASS if ok else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} Webster scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
