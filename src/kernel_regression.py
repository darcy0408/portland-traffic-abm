"""Pinned known-good trajectories for the car-following kernel.

WHY THIS EXISTS (audit item 7, AUDIT_FINDINGS_JUL23.md)
-------------------------------------------------------
The equivalence gates in lanes_scenarios.py and driver_scenarios.py compare the
kernel against ITSELF (lanes=None vs all-ones; flag-off vs all-sigma-0). That
proves a feature is inert, but a refactor that changed the physics for BOTH arms
equally would pass every one of them. This module closes that hole the only way
it can be closed: it stores literal trajectories captured from a known-good
kernel and asserts the current kernel still reproduces them EXACTLY.

The reference was captured at commit dfbd147 (the Jul 23 audit fixes, with every
experimental flag off), immediately before Phase 3 increment 2 restructured
neighbour finding. Three scenarios cover the paths that restructure touches:

  base_queue_cycle  20 cars queued at a red, one full signal cycle: the leader
                    lookup, the red-light virtual leader, and queue discharge.
  virtual_lanes_2   the same queue with 2 virtual lanes: the follow-N-ahead
                    leader lookup and N-abreast discharge (Phase 1).
  spillback         a full downstream segment: the cross-intersection leader and
                    the segment-entry hold, including a car held at the line.

Run `python src/kernel_regression.py` to check, `--write` to re-pin. RE-PINNING
IS A DELIBERATE ACT: it declares that a change to the kernel's numbers is
intended. Never re-pin to make a red gate go green without understanding which
number moved and why.
"""
import argparse
import json
import os
import random
import sys
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import emissions
from generate import step_vehicles

KPH = 1.0 / 3.6
PASS, FAIL = "PASS", "FAIL"
REFERENCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "kernel_reference.json")


def _edge(u, v, length_m, v0_mps):
    return (u, v, 0, length_m, v0_mps)


def _no_signals():
    return {"nodes": set(), "offset": {}, "edge_phase": {},
            "cycle": 60.0, "green_split": 0.5}


def _signal_at_2():
    """One signalized node (2), zero offset: phase 0 green [0,30), red [30,60)."""
    return {"nodes": {2}, "offset": {2: 0.0},
            "edge_phase": {(1, 2, 0): 0, (2, 3, 0): 0},
            "cycle": 60.0, "green_split": 0.5}


def _run(vehs, signals, n_steps, t0=0, **kw):
    """Step the real kernel. No car finishes its route in these scenarios, so the
    G/nodes/rng respawn arguments are dummies (the scenarios.py shortcut)."""
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox, seg_thru = (defaultdict(float), defaultdict(float),
                                  defaultdict(float))
    for s in range(n_steps):
        step_vehicles(vehs, config.DT, (t0 + s) * config.DT, seg_tot, seg_nox,
                      seg_thru, coeffs, None, [], random.Random(0), signals,
                      None, None, **kw)
    return seg_thru


def _state(vehs):
    """The captured quantity: every car's (route index, position, speed), in the
    vehicle order the scenario built, at full float precision."""
    return [[v["idx"], v["pos"], v["v"]] for v in vehs]


# --- the scenarios ---------------------------------------------------------

def _queue(n):
    """n cars stopped single file at the stop line of a 400 m edge, at the IDM
    equilibrium spacing (L + s0 = 7 m), front car 2 m short of the line."""
    v0 = 50 * KPH
    route = [_edge(1, 2, 400.0, v0), _edge(2, 3, 600.0, v0)]
    return [{"id": j, "route": list(route), "idx": 0,
             "pos": 398.0 - 7.0 * j, "v": 0.0} for j in range(n)]


def case_base_queue_cycle():
    vehs = _queue(20)
    _run(vehs, _signal_at_2(), 60, t0=30)
    return _state(vehs)


def case_virtual_lanes_2():
    vehs = _queue(20)
    _run(vehs, _signal_at_2(), 60, t0=30,
         lanes={(1, 2, 0): 2, (2, 3, 0): 2})
    return _state(vehs)


def _red_at_3():
    """Node 3 permanently red for phase 0: green_split 0 makes phase 1 the green
    one at every t, and our edges are phase 0. Used to hold a jam in place."""
    return {"nodes": {3}, "offset": {3: 0.0},
            "edge_phase": {(1, 2, 0): 0, (2, 3, 0): 0},
            "cycle": 60.0, "green_split": 0.0}


def case_spillback():
    """A SHORT downstream segment (60 m) held permanently red at its far end, so
    nine cars jam it end to end and its entrance stays blocked. Four more cars
    approach from upstream at 11 m/s. This exercises all three braking paths at
    once: the red-light virtual leader for the jammed cars, the leader seen
    ACROSS the intersection by the approaching cars, and the segment-entry hold
    that stops the first of them at the stop line (verified to fire: without the
    red the jam dissolves before anyone arrives and the hold never triggers)."""
    v0 = 50 * KPH
    up, down = _edge(1, 2, 120.0, v0), _edge(2, 3, 60.0, v0)
    tail = _edge(3, 4, 5000.0, v0)          # long, so nobody finishes the route
    # The two holds are SAFETY NETS: they only fire when a car would overshoot a
    # boundary within one step (ordinary IDM braking stops cars short of it), so
    # the front car of each group starts close to its boundary AT SPEED to
    # exercise them. Rearmost jam car at 3 m leaves the entrance blocked (< L+s0).
    jammed = ([{"id": 0, "route": [down, tail], "idx": 0, "pos": 59.0, "v": 8.0}]
              + [{"id": j, "route": [down, tail], "idx": 0,
                  "pos": 59.0 - 7.0 * j, "v": 0.0} for j in range(1, 9)])
    approaching = ([{"id": 100, "route": [up, down, tail], "idx": 0,
                     "pos": 119.0, "v": 11.0}]
                   + [{"id": 100 + j, "route": [up, down, tail], "idx": 0,
                       "pos": 119.0 - 12.0 * j, "v": 11.0} for j in range(1, 4)])
    vehs = jammed + approaching
    _run(vehs, _red_at_3(), 80)
    return _state(vehs)


CASES = {
    "base_queue_cycle": case_base_queue_cycle,
    "virtual_lanes_2": case_virtual_lanes_2,
    "spillback": case_spillback,
}


def capture():
    return {name: fn() for name, fn in CASES.items()}


def check(reference):
    """Compare the live kernel against the pinned reference, exactly. Returns True
    only if every car in every scenario matches bit for bit."""
    live = capture()
    all_ok = True
    for name in CASES:
        want, got = reference.get(name), live[name]
        if want is None:
            print(f"   [{FAIL}] {name}: no reference pinned")
            all_ok = False
            continue
        if len(want) != len(got):
            print(f"   [{FAIL}] {name}: {len(got)} cars vs {len(want)} pinned")
            all_ok = False
            continue
        # exact equality: any drift at all is a change in the kernel's numbers
        worst, worst_i = 0.0, -1
        for i, (w, g) in enumerate(zip(want, got)):
            for a, b in zip(w, g):
                if a != b and abs(a - b) > worst:
                    worst, worst_i = abs(a - b), i
        ok = worst_i == -1
        all_ok &= ok
        detail = ("all %d cars bit-identical to the pinned kernel" % len(got)
                  if ok else
                  "car %d differs, largest deviation %.3g" % (worst_i, worst))
        print(f"   [{PASS if ok else FAIL}] {name}: {detail}")
    return all_ok


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="re-pin the reference to the CURRENT kernel (deliberate)")
    args = ap.parse_args()

    if args.write:
        with open(REFERENCE_FILE, "w", encoding="utf-8") as f:
            json.dump(capture(), f, indent=1)
        print(f"re-pinned {len(CASES)} scenarios to {REFERENCE_FILE}")
        return 0

    print("Kernel regression: current kernel vs the pinned known-good trajectories")
    print("=" * 70)
    if not os.path.exists(REFERENCE_FILE):
        print(f"   [{FAIL}] no reference file at {REFERENCE_FILE} (run --write)")
        return 1
    with open(REFERENCE_FILE, encoding="utf-8") as f:
        reference = json.load(f)
    ok = check(reference)
    print("\n" + "=" * 70)
    print("kernel unchanged." if ok else
          "KERNEL CHANGED. Understand which number moved before re-pinning.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
