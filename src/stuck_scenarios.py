"""Hand-checkable scenarios for the STUCK-TIME accumulator (calibrated-demand
plan, Phase 3: "cars stuck" measured, not inferred).

Same discipline as scenarios.py / driver_scenarios.py (Christof's Jun 24 ask:
values predictable by hand, through the REAL kernel, never a reimplementation).
Three checks:

  A) MEASUREMENT AT A RED. A car sitting at a red light is stuck by definition:
     held for a 30 s red, its segment must accumulate stuck_sum = 30.0 vehicle-
     seconds exactly (every one of its vehicle-seconds is below 5 km/h), while a
     free car cruising at 50 km/h on its own segment accumulates exactly 0. And
     stuck_sum can never exceed value (total vehicle-seconds) on any segment --
     a stuck second IS a vehicle-second.

  B) THE THRESHOLD IS SHARP. One-step checks with an exactly known average
     speed either side of the 5 km/h line (4.97 counts as stuck, 5.03 does
     not), plus a sustained 20 km/h cruiser that accumulates ZERO over a full
     window -- slow is not stuck. (The one-step form is deliberate: at dt = 1 s
     a desired speed below 4*a_max*dt = 6 m/s is an UNSTABLE Euler fixed point
     of the IDM update, so a car cannot HOLD e.g. 6 km/h -- it oscillates
     through the line. 20 km/h is on the stable side, so the sustained check
     is honest.)

  C) INERTNESS. stuck_stats is PURE MEASUREMENT: the same queue-and-signal
     scenario run with and without the accumulator must produce bitwise
     identical trajectories (idx, pos, v for every car). Nothing in the
     accumulator can feed back into the dynamics. (kernel_regression.py
     additionally proves the surrounding edit changed no base physics.)

  D) HOUR BUCKETS (real-demand plan Phase A2). Buckets are the same seconds,
     filed by ELAPSED hour. A car held at a red that STRADDLES the 3600 s
     boundary (signal offset 45 s puts the red on t mod 60 in [45,15) wrapping,
     i.e. exactly t = 3585..3614) must split its 30 stuck seconds
     exactly 15/15 between hour 0 and hour 1 -- the hand-check. Then the
     identities: the hour totals sum to the flat total; in "segments" mode
     each segment's buckets sum to that segment's stuck_sum; "network" mode
     files no segments at all; and the buckets, like the accumulator itself,
     leave trajectories bitwise unchanged.

Run: python src/stuck_scenarios.py
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


def _no_signals():
    return {"nodes": set(), "offset": {}, "edge_phase": {},
            "cycle": 60.0, "green_split": 0.5}


def _signal_at_2():
    """One signalized node (2), zero offset: phase 0 green on [0,30), red [30,60)."""
    return {"nodes": {2}, "offset": {2: 0.0},
            "edge_phase": {(1, 2, 0): 0, (2, 3, 0): 0},
            "cycle": 60.0, "green_split": 0.5}


def _run(vehs, signals, n_steps, t0=0, stuck_stats=None, stuck_by_hour=None):
    """Step the real kernel n_steps, mutating vehs in place. Cars never finish
    their route here, so the G/nodes/rng respawn args are dummies (the same
    shortcut as driver_scenarios.py). Returns the per-segment vehicle-seconds
    so scenario A can compare stuck_sum against value."""
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox, seg_thru = defaultdict(float), defaultdict(float), defaultdict(float)
    for s in range(n_steps):
        step_vehicles(vehs, config.DT, (t0 + s) * config.DT, seg_tot, seg_nox,
                      seg_thru, coeffs, None, [], random.Random(0), signals,
                      None, None, stuck_stats=stuck_stats,
                      stuck_by_hour=stuck_by_hour)
    return seg_tot


def scenario_red_light():
    print("\nA) MEASUREMENT AT A RED: a held car is stuck, a cruising car is not")
    n_steps = 30
    print(f"   One car stopped at the stop line through a {n_steps} s red; one car")
    print(f"   cruising free at 50 km/h on its own segment. Every held second is")
    print(f"   below {config.STUCK_SPEED_KMH:.0f} km/h, no cruising second is.")
    v0 = 50 * KPH
    held = {"id": 0, "route": [_edge(1, 2, 400.0, v0), _edge(2, 3, 600.0, v0)],
            "idx": 0, "pos": 398.0, "v": 0.0}
    # own segment (unique node pair) => its own queue, genuinely free
    cruiser = {"id": 1, "route": [_edge(11, 12, 100_000.0, v0)],
               "idx": 0, "pos": 0.0, "v": v0}
    stuck = {"stuck_sum": defaultdict(float)}
    # t0=30 puts the whole window inside the red half of the cycle
    seg_tot = _run([held, cruiser], _signal_at_2(), n_steps, t0=30, stuck_stats=stuck)

    got_held = stuck["stuck_sum"][(1, 2, 0)]
    got_cruise = stuck["stuck_sum"][(11, 12, 0)]
    ok = []
    ok.append(_check("held car's segment accumulates the full red, exactly",
                     got_held == n_steps * config.DT,
                     f"stuck_sum {got_held:.1f} s vs {n_steps * config.DT:.1f} s held"))
    ok.append(_check("cruising car accumulates zero stuck time",
                     got_cruise == 0.0, f"stuck_sum {got_cruise:.1f} s at 50 km/h"))
    within = all(stuck["stuck_sum"][e] <= seg_tot[e] + 1e-12 for e in seg_tot)
    ok.append(_check("stuck_sum never exceeds value on any segment",
                     within,
                     f"held segment: stuck {got_held:.1f} of {seg_tot[(1, 2, 0)]:.1f} veh-s"))
    return all(ok)


def scenario_threshold():
    print("\nB) THE THRESHOLD IS SHARP: 4.97 km/h is stuck, 5.03 km/h is not")
    print(f"   One step each at a known speed either side of the "
          f"{config.STUCK_SPEED_KMH:.0f} km/h line, then a")
    print("   sustained 20 km/h cruiser for 30 s: slow is not stuck.")
    ok = []
    # one step at v = v0 (a free car at its desired speed has acceleration ~0,
    # magnitude ~1e-11 m/s^2, so the step's average speed IS that speed to ten
    # decimals): the step counts as stuck exactly when that speed is below the
    # line. One step, not a window, because a desired speed this low is an
    # unstable fixed point of the dt = 1 s Euler update (see module docstring) --
    # a longer run would measure the oscillation, not the threshold.
    for kmh, is_stuck in ((4.97, True), (5.03, False)):
        v = kmh * KPH
        car = {"id": 0, "route": [_edge(1, 2, 100_000.0, v)],
               "idx": 0, "pos": 0.0, "v": v}
        stuck = {"stuck_sum": defaultdict(float)}
        _run([car], _no_signals(), 1, stuck_stats=stuck)
        got = stuck["stuck_sum"][(1, 2, 0)]
        want = config.DT if is_stuck else 0.0
        side = "below" if is_stuck else "above"
        ok.append(_check(f"{kmh} km/h ({side} the line) counts {want:.0f} s",
                         got == want, f"stuck_sum {got:.1f} s"))

    # sustained: 20 km/h (5.56 m/s) is on the STABLE side of the Euler update,
    # so this car genuinely holds its slow-but-moving speed for the whole window
    n_steps = 30
    cruiser = {"id": 1, "route": [_edge(11, 12, 100_000.0, 20 * KPH)],
               "idx": 0, "pos": 0.0, "v": 20 * KPH}
    stuck = {"stuck_sum": defaultdict(float)}
    _run([cruiser], _no_signals(), n_steps, stuck_stats=stuck)
    got = stuck["stuck_sum"][(11, 12, 0)]
    ok.append(_check("20 km/h for 30 s: slow but never stuck",
                     got == 0.0, f"stuck_sum {got:.1f} s over {n_steps} s"))
    return all(ok)


def scenario_inertness():
    print("\nC) INERTNESS: measuring stuck time cannot change any trajectory")
    print("   A 20-car queue through a signal cycle, run twice -- with the")
    print("   accumulator and without. Trajectories must be bitwise identical.")
    v0 = 50 * KPH

    def queued():
        route = [_edge(1, 2, 400.0, v0), _edge(2, 3, 600.0, v0)]
        return [{"id": j, "route": list(route), "idx": 0,
                 "pos": 398.0 - 7.0 * j, "v": 0.0} for j in range(20)]

    runs = {}
    for label, stuck in (("off", None), ("on", {"stuck_sum": defaultdict(float)})):
        vehs = queued()
        _run(vehs, _signal_at_2(), 60, t0=30, stuck_stats=stuck)
        runs[label] = np.array([(v["idx"], v["pos"], v["v"]) for v in vehs])
    same = np.array_equal(runs["off"], runs["on"])
    return _check("trajectories identical (idx, pos, v for every car)", same,
                  "bitwise equal" if same else
                  f"max abs diff {np.abs(runs['off'] - runs['on']).max():.3g}")


def _signal_at_2_offset(offset):
    """The same single signal, phase-shifted: green when ((t+offset) % 60) < 30,
    so offset 45 puts the RED on t mod 60 in [45, 15) wrapping -- i.e. exactly
    t = 3585..3614, a red that straddles the 3600 s hour boundary. The shift is
    needed because the 60 s cycle divides 3600 exactly, so an unshifted signal
    always changes phase precisely AT the boundary and never across it."""
    sig = _signal_at_2()
    sig["offset"] = {2: float(offset)}
    return sig


def scenario_hour_buckets():
    print("\nD) HOUR BUCKETS: the same seconds, filed by elapsed hour")
    n_steps, t0 = 30, 3585           # t = 3585..3614: all red, straddles 3600
    print(f"   One car held at a red from t={t0} to t={t0 + n_steps - 1} s, a window")
    print("   that straddles the 1 h boundary. Expect exactly 15 s in hour 0")
    print("   and 15 s in hour 1, and every bucket summing back to stuck_sum.")
    v0 = 50 * KPH

    def held_car():
        return {"id": 0, "route": [_edge(1, 2, 400.0, v0), _edge(2, 3, 600.0, v0)],
                "idx": 0, "pos": 398.0, "v": 0.0}

    ok = []
    # --- the hand-check, in "segments" mode (the richer of the two) ---
    stuck = {"stuck_sum": defaultdict(float), "hour_sum": defaultdict(float),
             "hour_seg": defaultdict(float)}
    _run([held_car()], _signal_at_2_offset(45), n_steps, t0=t0,
         stuck_stats=stuck, stuck_by_hour="segments")
    seg = (1, 2, 0)
    h0, h1 = stuck["hour_sum"][0], stuck["hour_sum"][1]
    ok.append(_check("the held car is stuck for the whole window",
                     stuck["stuck_sum"][seg] == n_steps * config.DT,
                     f"stuck_sum {stuck['stuck_sum'][seg]:.1f} s of "
                     f"{n_steps * config.DT:.1f} s held"))
    ok.append(_check("split exactly 15 s / 15 s across the hour boundary",
                     h0 == 15.0 and h1 == 15.0,
                     f"hour 0 = {h0:.1f} s, hour 1 = {h1:.1f} s"))
    ok.append(_check("no seconds filed outside those two hours",
                     set(stuck["hour_sum"]) == {0, 1},
                     f"hours present: {sorted(stuck['hour_sum'])}"))
    ok.append(_check("hour totals sum to the flat total",
                     sum(stuck["hour_sum"].values())
                     == sum(stuck["stuck_sum"].values()),
                     f"{sum(stuck['hour_sum'].values()):.1f} s vs "
                     f"{sum(stuck['stuck_sum'].values()):.1f} s"))
    per_seg = defaultdict(float)
    for (_h, e), secs in stuck["hour_seg"].items():
        per_seg[e] += secs
    ok.append(_check("per-segment buckets sum to that segment's stuck_sum",
                     all(abs(per_seg[e] - stuck["stuck_sum"][e]) < 1e-12
                         for e in stuck["stuck_sum"]),
                     f"segment {seg}: {per_seg[seg]:.1f} s vs "
                     f"{stuck['stuck_sum'][seg]:.1f} s"))

    # --- "network" mode files hours but no segments ---
    net = {"stuck_sum": defaultdict(float), "hour_sum": defaultdict(float)}
    _run([held_car()], _signal_at_2_offset(45), n_steps, t0=t0,
         stuck_stats=net, stuck_by_hour="network")
    ok.append(_check("network mode gives the same hours, no segment detail",
                     dict(net["hour_sum"]) == {0: 15.0, 1: 15.0}
                     and "hour_seg" not in net,
                     f"hour_sum {dict(net['hour_sum'])}, "
                     f"hour_seg {'absent' if 'hour_seg' not in net else 'PRESENT'}"))

    # --- inertness: bucketing changes no trajectory ---
    def queued():
        route = [_edge(1, 2, 400.0, v0), _edge(2, 3, 600.0, v0)]
        return [{"id": j, "route": list(route), "idx": 0,
                 "pos": 398.0 - 7.0 * j, "v": 0.0} for j in range(20)]

    runs = {}
    for label, mode in (("off", None), ("segments", "segments")):
        vehs = queued()
        st = {"stuck_sum": defaultdict(float), "hour_sum": defaultdict(float),
              "hour_seg": defaultdict(float)} if mode else None
        # 40 steps: the 30 s red (queued, filling both hour buckets) plus 10 s
        # of discharge. Deliberately short of the ~600 m the lead car needs to
        # finish its route -- these cars have dummy G/nodes and cannot respawn.
        _run(vehs, _signal_at_2_offset(45), 40, t0=t0, stuck_stats=st,
             stuck_by_hour=mode)
        runs[label] = np.array([(v["idx"], v["pos"], v["v"]) for v in vehs])
    same = np.array_equal(runs["off"], runs["segments"])
    ok.append(_check("bucketing leaves trajectories bitwise identical", same,
                     "bitwise equal" if same else
                     f"max abs diff {np.abs(runs['off'] - runs['segments']).max():.3g}"))
    return all(ok)


if __name__ == "__main__":
    print("Stuck-time accumulator scenarios  (real kernel, hand-checkable)")
    print("=" * 66)
    results = {"red_light": scenario_red_light(),
               "threshold": scenario_threshold(),
               "inertness": scenario_inertness(),
               "hour_buckets": scenario_hour_buckets()}
    print("\n" + "=" * 66)
    for name, okay in results.items():
        print(f"   {PASS if okay else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} stuck scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
