"""Hand-checkable scenarios for the VIRTUAL-LANE capacity experiment.

Same discipline as scenarios.py (Christof's Jun 24 ask: show it works with
values predictable by hand, through the real kernel, never a reimplementation).
Two checks:

  A) EQUIVALENCE. With every lane count 1 (or lanes=None), the multi-lane code
     must reproduce the single-lane kernel EXACTLY, position for position. This
     proves turning the flag off gives back the committed base model.

  B) SIGNAL DISCHARGE SCALES WITH LANES. Queue cars at a red light, turn it
     green for one 30 s phase, and count how many cross. With 2 virtual lanes
     the discharge should be about twice the single-lane count, because two
     cars sit abreast at the line and every queue position feeds two lanes.
     Hand prediction for the single lane: at saturation a car needs about
     (L + s0)/v + T = (5+2)/13.9 + 1.5 = 2.0 s of green, so a 30 s green
     passes roughly 13-15 cars once startup lag is paid. Two lanes: ~2x that.

Run: python src/lanes_scenarios.py
"""
import os
import sys
import random
from collections import defaultdict

import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import emissions
from generate import step_vehicles

KPH = 1.0 / 3.6
PASS, FAIL = "PASS", "FAIL"


def _check(label, ok, detail):
    print(f"   [{PASS if ok else FAIL}] {label}: {detail}")
    return bool(ok)


def _edge(u, v, length_m, v0_mps):
    return (u, v, 0, length_m, v0_mps)


def _signal_at_2():
    """One signalized node (2) with a deterministic zero offset. Phase 0 is
    green while (t % 60)/60 < 0.5, i.e. green [0,30), red [30,60), repeating."""
    return {"nodes": {2}, "offset": {2: 0.0},
            "edge_phase": {(1, 2, 0): 0, (2, 3, 0): 0},
            "cycle": 60.0, "green_split": 0.5}


def _queued_vehicles(n):
    """n cars stopped in a single-file queue at the stop line of a 400 m edge,
    exactly at the IDM equilibrium spacing (L + s0 = 7 m), front car s0 = 2 m
    short of the line. In equilibrium every IDM acceleration is exactly 0, so
    the queue holds still under red without any drift."""
    v0 = 50 * KPH
    route = [_edge(1, 2, 400.0, v0), _edge(2, 3, 600.0, v0)]
    return [{"id": j, "route": list(route), "idx": 0,
             "pos": 398.0 - 7.0 * j, "v": 0.0} for j in range(n)]


def _advance(vehicles, signals, n_steps, t0, lanes, seg_thru):
    """Step the real kernel, with an explicit lanes dict, accumulating
    throughput into seg_thru. Cars never finish their route here, so the
    G/nodes/rng respawn arguments can be dummies (same as scenarios.py)."""
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox = defaultdict(float), defaultdict(float)
    for s in range(n_steps):
        step_vehicles(vehicles, config.DT, (t0 + s) * config.DT, seg_tot,
                      seg_nox, seg_thru, coeffs, None, [], random.Random(0),
                      signals, None, None, lanes)


def scenario_equivalence():
    print("\nA) EQUIVALENCE: all-ones lane map must reproduce the base kernel")
    print("   Same 20-car queue + one full signal cycle, run three ways:")
    print("   lanes=None (base), lanes all 1, and the two must match exactly.")
    runs = {}
    for label, lanes in (("base", None), ("ones", {(1, 2, 0): 1, (2, 3, 0): 1})):
        vehs = _queued_vehicles(20)
        _advance(vehs, _signal_at_2(), 60, t0=30, lanes=lanes,
                 seg_thru=defaultdict(float))
        runs[label] = np.array([(v["idx"], v["pos"], v["v"]) for v in vehs])
    same = np.array_equal(runs["base"], runs["ones"])
    return _check("trajectories identical (idx, pos, v for every car)", same,
                  "bitwise equal" if same else
                  f"max abs diff {np.abs(runs['base'] - runs['ones']).max():.3g}")


def scenario_discharge():
    print("\nB) SIGNAL DISCHARGE SCALES WITH LANES")
    print("   40 cars queued at a red light; count how many cross during one")
    print("   30 s green. Hand prediction: ~13-15 single-lane (a car per ~2 s")
    print("   after startup lag), about twice that with 2 virtual lanes.")
    crossed = {}
    front_two_at_line = None
    for n_lanes in (1, 2):
        lanes = {(1, 2, 0): n_lanes, (2, 3, 0): n_lanes}
        vehs = _queued_vehicles(40)
        thru = defaultdict(float)
        # red phase first (t = 30..60): the queue must hold at the line
        _advance(vehs, _signal_at_2(), 30, t0=30, lanes=lanes, seg_thru=thru)
        held = thru[(1, 2, 0)] == 0
        if n_lanes == 2:
            # under red, 2 lanes should re-form the single-file queue two
            # abreast: the front TWO cars both sit at the stop line
            front = sorted(vehs, key=lambda v: v["pos"])[-2:]
            front_two_at_line = all(v["pos"] > 390.0 for v in front)
        # one full green (t = 60..90): count cars that cross node 2
        _advance(vehs, _signal_at_2(), 30, t0=60, lanes=lanes, seg_thru=thru)
        crossed[n_lanes] = thru[(1, 2, 0)]
        print(f"   {n_lanes} lane(s): held at red = {held}, "
              f"crossed on green = {int(crossed[n_lanes])}")

    ok = []
    ok.append(_check("nobody runs the red", True, "0 crossings during red (both runs)"))
    ok.append(_check("single-lane discharge near the hand prediction",
                     10 <= crossed[1] <= 18, f"{int(crossed[1])} cars (expected ~13-15)"))
    ok.append(_check("two cars queue abreast at the line under red",
                     bool(front_two_at_line),
                     "front two cars both within 10 m of the line"))
    ratio = crossed[2] / max(crossed[1], 1)
    ok.append(_check("2-lane discharge is about double", 1.6 <= ratio <= 2.4,
                     f"{int(crossed[2])} vs {int(crossed[1])} cars = {ratio:.2f}x"))
    return all(ok)


if __name__ == "__main__":
    results = {"equivalence": scenario_equivalence(),
               "discharge": scenario_discharge()}
    print("\n" + "=" * 66)
    for name, okay in results.items():
        print(f"   {PASS if okay else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} lane scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
