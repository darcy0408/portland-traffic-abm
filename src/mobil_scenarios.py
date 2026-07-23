"""Hand-checkable scenarios for the MOBIL lane-change DECISION (Phase 3).

Same discipline as scenarios.py / lanes_scenarios.py / driver_scenarios.py: small
situations whose outcome you can predict by hand, evaluated through the REAL pieces
-- generate.idm_acceleration for every acceleration and mobil.wants_change for the
decision, never a reimplementation. These test the decision layer in ISOLATION
(two lanes, a handful of cars, one candidate move) before it is wired into the
networked step_vehicles. Each scenario names the geometry, the expected verdict,
and prints the MOBIL incentive margin so the number is inspectable.

Four cases:
  1. STUCK + CLEAR LANE   fast car trapped behind a slow one, target lane open
                          ahead  -> changes (big acceleration gain, nobody behind).
  2. UNSAFE CUT-IN        same want, but a fast car sits right behind the gap in
                          the target lane -> blocked by the safety criterion.
  3. NO INCENTIVE         car already on open road, target lane no better
                          -> stays (gain below threshold).
  4. POLITENESS           a safe change that helps the mover a little but forces a
                          faster car behind it to brake -> taken when selfish
                          (p = 0), declined when polite (p = 0.5). Same geometry,
                          same safety, only the politeness weight differs.

Run: python src/mobil_scenarios.py
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import mobil
from generate import idm_acceleration

PASS, FAIL = "PASS", "FAIL"
L = config.VEHICLE_LENGTH_M
V0 = 50.0 / 3.6                       # 13.9 m/s desired speed, one limit for all cars


def _check(label, ok, detail):
    print(f"   [{PASS if ok else FAIL}] {label}: {detail}")
    return bool(ok)


def _accel(v, pos, lead=None):
    """IDM acceleration of a car at (v, pos) behind an optional leader.
    lead = (leader_v, leader_pos) or None for open road. Uses the REAL kernel, so
    the gap = leader_pos - vehicle_length - pos is the same clear gap step_vehicles
    computes."""
    if lead is None:
        return idm_acceleration(v, 1e6, v, V0)     # free road: no car ahead
    lead_v, lead_pos = lead
    return idm_acceleration(v, lead_pos - L - pos, lead_v, V0)


def scenario_stuck_clear():
    print("\n1) STUCK BEHIND A SLOW CAR, TARGET LANE CLEAR AHEAD -> change")
    print("   Ego at 100 m doing 13.9 m/s catches a 5 m/s crawler at 130 m in its")
    print("   lane; the next lane is empty ahead. Expect: strong gain, nobody behind,")
    print("   so MOBIL changes.")
    p = mobil.params_from_config(config)
    self_before = _accel(V0, 100.0, lead=(5.0, 130.0))     # braking hard for the crawler
    self_after = _accel(V0, 100.0, lead=None)              # free in the target lane
    change, margin = mobil.wants_change(self_before, self_after,
                                        old_pair=None, new_pair=None, params=p)
    print(f"   self accel {self_before:+.3f} -> {self_after:+.3f} m/s^2, "
          f"margin {margin:+.3f} (threshold {p.a_thr})")
    return _check("changes lane", change, f"wants_change = {change}")


def scenario_unsafe_cutin():
    print("\n2) SAME WANT, BUT A FAST CAR SITS IN THE GAP -> blocked by safety")
    print("   As (1), but the target lane has a 13.9 m/s follower at 96 m, just")
    print("   behind the ego's 100 m. Cutting in would overlap it and force braking")
    print("   far past b_safe. Expect: safety criterion vetoes the change.")
    p = mobil.params_from_config(config)
    self_before = _accel(V0, 100.0, lead=(5.0, 130.0))
    self_after = _accel(V0, 100.0, lead=None)
    new_before = _accel(V0, 96.0, lead=None)               # the follower, free for now
    new_after = _accel(V0, 96.0, lead=(V0, 100.0))         # ego cuts in 4 m ahead of it
    change, margin = mobil.wants_change(self_before, self_after, old_pair=None,
                                        new_pair=(new_before, new_after), params=p)
    print(f"   new follower accel {new_before:+.3f} -> {new_after:+.3f} m/s^2 "
          f"(b_safe = -{p.b_safe}), margin {margin:+.3f}")
    return _check("does NOT change (unsafe)", not change, f"wants_change = {change}")


def scenario_no_incentive():
    print("\n3) ALREADY ON OPEN ROAD, TARGET LANE NO BETTER -> stay")
    print("   Ego cruising at the limit with no car ahead in either lane. Expect:")
    print("   no acceleration to gain, so the margin is below threshold and it stays.")
    p = mobil.params_from_config(config)
    self_before = _accel(V0, 100.0, lead=None)             # already free
    self_after = _accel(V0, 100.0, lead=None)              # target lane equally free
    change, margin = mobil.wants_change(self_before, self_after,
                                        old_pair=None, new_pair=None, params=p)
    print(f"   self accel {self_before:+.3f} -> {self_after:+.3f} m/s^2, "
          f"margin {margin:+.3f} (threshold {p.a_thr})")
    return _check("does NOT change (no incentive)", not change, f"wants_change = {change}")


def scenario_politeness():
    print("\n4) POLITENESS: a safe change that inconveniences a faster car behind")
    print("   Ego (12 m/s) mildly held by a 10 m/s leader at 140 m wants the open")
    print("   next lane, but a 13.9 m/s car at 70 m is coming up that lane and would")
    print("   have to brake ~2 m/s^2 (safe, < b_safe) if the ego enters. Expect: a")
    print("   selfish driver (p = 0) takes it, a polite one (p = 0.5) yields.")
    self_before = _accel(12.0, 100.0, lead=(10.0, 140.0))  # mildly slowed
    self_after = _accel(12.0, 100.0, lead=None)            # open target lane
    new_before = _accel(V0, 70.0, lead=None)               # fast car behind, free now
    new_after = _accel(V0, 70.0, lead=(12.0, 100.0))       # must brake for the ego
    print(f"   self gain {self_before:+.3f} -> {self_after:+.3f}; new follower "
          f"{new_before:+.3f} -> {new_after:+.3f} m/s^2")

    selfish = mobil.MobilParams(politeness=0.0, a_thr=config.MOBIL_A_THRESHOLD,
                                b_safe=config.MOBIL_B_SAFE)
    polite = mobil.MobilParams(politeness=0.5, a_thr=config.MOBIL_A_THRESHOLD,
                               b_safe=config.MOBIL_B_SAFE)
    ch_s, m_s = mobil.wants_change(self_before, self_after, None,
                                   (new_before, new_after), selfish)
    ch_p, m_p = mobil.wants_change(self_before, self_after, None,
                                   (new_before, new_after), polite)
    print(f"   margin: selfish (p=0) {m_s:+.3f} -> change {ch_s};  "
          f"polite (p=0.5) {m_p:+.3f} -> change {ch_p}")
    ok = [_check("safe in both cases (not a safety veto)",
                 new_after >= -config.MOBIL_B_SAFE,
                 f"new follower brakes {new_after:+.3f} >= -{config.MOBIL_B_SAFE}"),
          _check("selfish driver changes", ch_s, f"wants_change = {ch_s}"),
          _check("polite driver yields", not ch_p, f"wants_change = {ch_p}")]
    return all(ok)


if __name__ == "__main__":
    print("MOBIL lane-change decision scenarios  (real IDM accels, hand-checkable)")
    print("=" * 70)
    results = {
        "stuck+clear -> change": scenario_stuck_clear(),
        "unsafe cut-in -> blocked": scenario_unsafe_cutin(),
        "no incentive -> stay": scenario_no_incentive(),
        "politeness": scenario_politeness(),
    }
    print("\n" + "=" * 70)
    for name, ok in results.items():
        print(f"   {PASS if ok else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} MOBIL scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
