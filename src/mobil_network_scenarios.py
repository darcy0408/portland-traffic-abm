"""Hand-checkable scenarios for MOBIL wired into the network (Phase 3, increment 2).

src/mobil_scenarios.py gates the DECISION in isolation (given six accelerations,
does MOBIL say change?). This gates the decision INSIDE the real kernel: explicit
per-car lane identity, within-lane car following, and the lane-change pass in
generate.step_vehicles. Three checks:

  A) OVERTAKING EMERGES. A fast driver is released behind a slow one on a long
     segment. On TWO lanes it must end up AHEAD; on ONE lane, with everything else
     identical, it must end up behind, stuck. Nothing in the code says "overtake":
     the pass happens only because MOBIL finds the adjacent lane both safe and
     worth taking, and the IDM then lets the faster car pull away. This is the
     headline result of the whole phase, and the one-lane arm is the control that
     proves it is the lane change doing the work.

  B) INERTNESS. MOBIL on, but every segment one lane wide, must reproduce the base
     single-file kernel EXACTLY -- a car with nowhere to change behaves exactly as
     if the feature did not exist. Checked bitwise against the same scenario run
     with the feature off entirely.

  C) LANE CLAMPING ON A NARROWING ROAD. A car in lane 2 crossing into a 1-lane
     segment must end up in lane 0, not keep an index its new road does not have.

The Phase 1 virtual-lane gate (lanes_scenarios.py) and the pinned kernel
regression (kernel_regression.py) cover the other half of the contract: the two
older lane modes are untouched by any of this.

Run: python src/mobil_network_scenarios.py
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
import mobil
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


def _ctx(lane_counts):
    """A MOBIL context with the config parameters and the given per-segment lane
    counts, built without touching config.MOBIL_ENABLED (these scenarios drive
    step_vehicles directly, exactly as the kernel would when the flag is on)."""
    return {"params": mobil.params_from_config(config), "lanes": dict(lane_counts)}


def _run(vehs, signals, n_steps, **kw):
    """Step the real kernel. No car finishes its route here, so the G/nodes/rng
    respawn arguments are dummies (the scenarios.py shortcut)."""
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox, seg_thru = (defaultdict(float), defaultdict(float),
                                  defaultdict(float))
    for s in range(n_steps):
        step_vehicles(vehs, config.DT, s * config.DT, seg_tot, seg_nox, seg_thru,
                      coeffs, None, [], random.Random(0), signals, None, None, **kw)


# --- A) overtaking ---------------------------------------------------------

# A fast driver (desired speed 1.35x the limit) released 30 m behind a slow one
# (0.55x) on a 6 km segment. Both are heterogeneous cars, so this also exercises
# per-vehicle IDM parameters inside the MOBIL path.
FAST_FACTOR, SLOW_FACTOR = 1.35, 0.55
T_RUN = 240


def _idm(v0_factor):
    return {"v0_factor": v0_factor, "a_max": config.IDM_A_MAX,
            "b_comf": config.IDM_B_COMF, "T": config.IDM_T, "s0": config.IDM_S0}


def _overtake_run(n_lanes):
    """Slow car ahead, fast car behind, both starting from rest in lane 0 of one
    long segment. The segment is longer than the fast car's free-running distance
    so neither car finishes its route (no respawn to confound the comparison).
    Returns (fast_pos, slow_pos, fast_lane)."""
    v0 = 50 * KPH
    seg = _edge(1, 2, 6000.0, v0)
    slow = {"id": 0, "route": [seg], "idx": 0, "pos": 30.0, "v": 0.0,
            "lane": 0, "idm": _idm(SLOW_FACTOR)}
    fast = {"id": 1, "route": [seg], "idx": 0, "pos": 0.0, "v": 0.0,
            "lane": 0, "idm": _idm(FAST_FACTOR)}
    vehs = [slow, fast]
    _run(vehs, _no_signals(), T_RUN, mobil_ctx=_ctx({(1, 2, 0): n_lanes}))
    return fast["pos"], slow["pos"], fast["lane"]


def scenario_overtaking():
    print("\nA) OVERTAKING EMERGES ON TWO LANES AND CANNOT ON ONE")
    v0 = 50 * KPH
    print(f"   A fast driver (desired {FAST_FACTOR}x limit = "
          f"{v0*FAST_FACTOR:.1f} m/s) starts 30 m behind a slow one "
          f"({SLOW_FACTOR}x = {v0*SLOW_FACTOR:.1f} m/s) on a 6 km segment.")
    print(f"   Free-running for {T_RUN} s the fast car would cover "
          f"~{v0*FAST_FACTOR*T_RUN:.0f} m and the slow one ~{v0*SLOW_FACTOR*T_RUN:.0f} m;")
    print("   single file the fast car is trapped at the slow car's speed.")

    f2, s2, lane2 = _overtake_run(2)
    f1, s1, _ = _overtake_run(1)
    print(f"\n   2 lanes: fast at {f2:.0f} m (lane {lane2}), slow at {s2:.0f} m "
          f"-> fast is {f2-s2:+.0f} m relative")
    print(f"   1 lane:  fast at {f1:.0f} m, slow at {s1:.0f} m "
          f"-> fast is {f1-s1:+.0f} m relative")

    ok = []
    ok.append(_check("2 lanes: the fast car ends AHEAD of the slow one",
                     f2 > s2, f"{f2:.0f} m vs {s2:.0f} m, a {f2-s2:.0f} m lead"))
    ok.append(_check("1 lane: the fast car ends BEHIND, stuck",
                     f1 < s1, f"{f1:.0f} m vs {s1:.0f} m, {s1-f1:.0f} m behind"))
    # The overtaking car must actually have used the second lane, not squeezed
    # past inside lane 0 (which would mean the lane bookkeeping is broken).
    ok.append(_check("the overtake used the second lane", lane2 == 1,
                     f"fast car finishes in lane {lane2}"))
    # And it must be genuinely faster, near its own desired speed, not merely
    # ahead because the slow car stopped.
    ok.append(_check("blocked and free runs differ by roughly the speed gap",
                     f2 - f1 > 0.5 * (FAST_FACTOR - SLOW_FACTOR) * v0 * T_RUN,
                     f"fast car travels {f2-f1:.0f} m further with a lane to use"))
    return all(ok)


# --- B) inertness ----------------------------------------------------------

def _queue(n):
    """n cars in a single-file queue on a 400 m edge at the IDM equilibrium
    spacing, released from rest with a slow leader so the platoon interacts. The
    downstream edge is long enough that nobody finishes the route even after
    overtaking at full speed, so no respawn confounds the comparison."""
    v0 = 50 * KPH
    route = [_edge(1, 2, 400.0, v0), _edge(2, 3, 2000.0, v0)]
    vehs = [{"id": j, "route": list(route), "idx": 0,
             "pos": 100.0 - 7.0 * j, "v": 0.0} for j in range(n)]
    vehs[0]["idm"] = _idm(SLOW_FACTOR)      # a slow leader the others pile up behind
    return vehs


def scenario_inertness():
    print("\nB) INERTNESS: MOBIL on with 1-lane segments == the base kernel")
    print("   Twelve cars released behind a slow leader, run two ways: the feature")
    print("   off entirely, and MOBIL on with every segment one lane wide. A car")
    print("   with nowhere to change must behave exactly single-file.")
    runs = {}
    for label, kw in (("off", {}),
                      ("mobil_1lane",
                       {"mobil_ctx": _ctx({(1, 2, 0): 1, (2, 3, 0): 1})})):
        vehs = _queue(12)
        _run(vehs, _no_signals(), 120, **kw)
        runs[label] = np.array([(v["idx"], v["pos"], v["v"]) for v in vehs])
    same = np.array_equal(runs["off"], runs["mobil_1lane"])
    detail = ("bitwise equal" if same else
              f"max abs diff {np.abs(runs['off'] - runs['mobil_1lane']).max():.3g}")
    ok = [_check("trajectories identical (idx, pos, v for every car)", same, detail)]

    # The same cars on a 2-lane segment must NOT match, or the check above would
    # pass for a MOBIL that simply never does anything.
    vehs = _queue(12)
    _run(vehs, _no_signals(), 120,
         mobil_ctx=_ctx({(1, 2, 0): 2, (2, 3, 0): 2}))
    two = np.array([(v["idx"], v["pos"], v["v"]) for v in vehs])
    moved = not np.array_equal(runs["off"], two)
    lanes_used = sorted({v.get("lane", 0) for v in vehs})
    ok.append(_check("...but 2 lanes DOES change the outcome (the gate can fail)",
                     moved and lanes_used == [0, 1],
                     f"lanes occupied at the end: {lanes_used}"))
    return all(ok)


# --- C) clamping -----------------------------------------------------------

def scenario_clamping():
    print("\nC) LANE INDEX CLAMPS WHEN THE ROAD NARROWS")
    print("   A car in lane 2 of a 3-lane segment crosses into a 1-lane segment.")
    print("   It must land in lane 0: an index its new road does not have would")
    print("   silently put it in a lane of its own, invisible to every other car.")
    v0 = 50 * KPH
    wide, narrow = _edge(1, 2, 50.0, v0), _edge(2, 3, 2000.0, v0)
    car = {"id": 0, "route": [wide, narrow], "idx": 0, "pos": 20.0, "v": 12.0,
           "lane": 2}
    _run([car], _no_signals(), 20,
         mobil_ctx=_ctx({(1, 2, 0): 3, (2, 3, 0): 1}))
    ok = [_check("the car crossed into the narrow segment", car["idx"] == 1,
                 f"route index {car['idx']}, pos {car['pos']:.1f} m"),
          _check("its lane index clamped to the only lane there", car["lane"] == 0,
                 f"lane {car['lane']} (was 2 on the 3-lane segment)")]
    return all(ok)


if __name__ == "__main__":
    print("MOBIL network scenarios  (real kernel, hand-checkable)")
    print("=" * 70)
    results = {"overtaking": scenario_overtaking(),
               "inertness": scenario_inertness(),
               "clamping": scenario_clamping()}
    print("\n" + "=" * 70)
    for name, okay in results.items():
        print(f"   {PASS if okay else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} MOBIL network scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
