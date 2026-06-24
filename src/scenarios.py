"""Validation test-bench for the ABM (Christof, Jun 24).

Christof's guidance: you do not have to understand every line the model is made
of, but you must be able to SHOW it works. So this script runs a handful of
small, hand-checkable scenarios through the real simulation kernel (the same
idm_acceleration and step_vehicles that generate.py uses, never a reimplementation)
and reports, for each, what the output MUST be and what it actually was.

The scenarios are exactly the ones Christof named:
  1. one car on an open road        -> accelerates to the limit and holds
  2. two cars, one behind the other -> the follower keeps a safe gap, no overlap
  3. one car at a red light         -> stops at the line, goes on green
  4. a saturated road (1,500 cars)  -> mean speed collapses, cars stop (congestion)

Run it with:  python src/scenarios.py
Each scenario prints PASS/FAIL checks you can verify by eye, and the controlled
ones (1-3) save a per-second trace to data/processed for the demo plots.
"""
import os
import sys
import random
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import emissions
from generate import (idm_acceleration, step_vehicles, make_vehicle,
                      prepare_network, prepare_signals, get_network)

KPH = 1.0 / 3.6
PASS, FAIL = "PASS", "FAIL"


# --- tiny helpers so the scenarios read like a checklist --------------------

def _check(label, ok, detail):
    """Print one expected-vs-actual line and return whether it passed."""
    print(f"   [{PASS if ok else FAIL}] {label}: {detail}")
    return bool(ok)


def _edge(u, v, length_m, v0_mps):
    """One route edge in the kernel's format: (u, v, key, length_m, v0_mps)."""
    return (u, v, 0, length_m, v0_mps)


def _no_signals():
    """A signals dict with no signalized nodes (open road, no lights)."""
    return {"nodes": set(), "offset": {}, "edge_phase": {},
            "cycle": config.SIGNAL_CYCLE_S, "green_split": config.SIGNAL_GREEN_SPLIT}


def _advance(vehicles, signals, n_steps, t0=0):
    """Step the real kernel n_steps and record each car's (t, pos, v, a) trace.
    G/nodes/rng are only touched when a car finishes its route and respawns; the
    controlled scenarios keep cars mid-route, so passing dummies here is safe."""
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox = defaultdict(float), defaultdict(float)
    trace = []
    for s in range(n_steps):
        prev_v = {veh["id"]: veh["v"] for veh in vehicles}
        step_vehicles(vehicles, config.DT, (t0 + s) * config.DT,
                      seg_tot, seg_nox, coeffs, None, [], random.Random(0), signals)
        for veh in vehicles:
            a = (veh["v"] - prev_v[veh["id"]]) / config.DT
            # cumulative distance along the whole route (so it stays monotonic across
            # segment crossings, unlike pos, which resets to 0 on each new segment)
            route_dist = sum(e[3] for e in veh["route"][:veh["idx"]]) + veh["pos"]
            trace.append({"t": t0 + s + 1, "id": veh["id"], "idx": veh["idx"],
                          "pos": veh["pos"], "route_dist": route_dist,
                          "v": veh["v"], "a": a})
    return pd.DataFrame(trace)


def _save_trace(df, name):
    path = os.path.join(config.PROCESSED_DIR, f"scenario_{name}.parquet")
    df.to_parquet(path, index=False)
    print(f"   trace -> {path}")


# --- scenario 1: one car on an open road ------------------------------------

def scenario_one_car():
    print("\n1) ONE CAR, OPEN ROAD")
    print("   Expect: starts from rest, accelerates near a_max, eases up to the")
    print("   speed limit, and never overshoots it.")
    v0 = 50 * KPH                                   # 50 km/h limit
    car = {"id": 0, "route": [_edge(1, 2, 2000.0, v0)], "idx": 0, "pos": 0.0, "v": 0.0}
    df = _advance([car], _no_signals(), 60)

    vs = df["v"].to_numpy()
    a0 = df["a"].iloc[0]
    ok = []
    ok.append(_check("first-step accel near a_max", abs(a0 - config.IDM_A_MAX) < 0.1,
                     f"a0 = {a0:.3f} m/s^2 (a_max = {config.IDM_A_MAX})"))
    ok.append(_check("speed never exceeds the limit", vs.max() <= v0 + 1e-6,
                     f"max speed {vs.max():.3f} <= v0 {v0:.3f} m/s"))
    ok.append(_check("speed only ever rises (no leader to brake for)",
                     bool(np.all(np.diff(vs) >= -1e-9)),
                     f"min step change {np.diff(vs).min():+.4f} m/s"))
    ok.append(_check("reaches ~the limit within 60 s", vs[-1] >= 0.95 * v0,
                     f"final speed {vs[-1]:.3f} = {100 * vs[-1] / v0:.1f}% of limit"))
    _save_trace(df, "one_car")
    return all(ok)


# --- scenario 2: two cars, car-following ------------------------------------

def scenario_two_cars():
    print("\n2) TWO CARS, ONE FOLLOWING THE OTHER")
    print("   A slow leader (desired 5 m/s) ahead of a faster follower (desired")
    print("   13.9 m/s). Expect: the follower slows, never overlaps the leader, and")
    print("   settles to the IDM desired gap ( s0 + v*T = 2 + 5*1.5 = 9.5 m ).")
    lead = {"id": 0, "route": [_edge(1, 2, 2000.0, 5.0)], "idx": 0, "pos": 100.0, "v": 5.0}
    foll = {"id": 1, "route": [_edge(1, 2, 2000.0, 50 * KPH)], "idx": 0, "pos": 0.0, "v": 0.0}
    df = _advance([lead, foll], _no_signals(), 180)

    L = config.VEHICLE_LENGTH_M
    lead_t = df[df["id"] == 0].reset_index(drop=True)
    foll_t = df[df["id"] == 1].reset_index(drop=True)
    gap = lead_t["pos"].to_numpy() - L - foll_t["pos"].to_numpy()   # clear gap, IDM sense
    want_gap = config.IDM_S0 + foll_t["v"].iloc[-1] * config.IDM_T

    ok = []
    ok.append(_check("no overlap ever (gap stays positive)", gap.min() > 0,
                     f"smallest clear gap {gap.min():.3f} m"))
    ok.append(_check("follower speed converges to the leader's",
                     abs(foll_t["v"].iloc[-1] - lead_t["v"].iloc[-1]) < 0.3,
                     f"follower {foll_t['v'].iloc[-1]:.2f} vs leader "
                     f"{lead_t['v'].iloc[-1]:.2f} m/s"))
    ok.append(_check("settles near the desired headway", abs(gap[-1] - want_gap) < 2.0,
                     f"final gap {gap[-1]:.2f} m vs desired {want_gap:.2f} m"))
    _save_trace(df, "two_cars")
    return all(ok)


# --- scenario 3: one car at a red light -------------------------------------

def scenario_red_light():
    print("\n3) ONE CAR AT A RED LIGHT")
    print("   Light is RED for t < 30 s, GREEN after. Expect: the car brakes, waits")
    print("   just short of the stop line (never runs the red), then departs on green.")
    v0 = 50 * KPH
    node = 2                                        # signal sits at the end of edge A
    car = {"id": 0,
           "route": [_edge(1, node, 150.0, v0), _edge(node, 3, 500.0, v0)],
           "idx": 0, "pos": 0.0, "v": 0.0}
    # offset 30 with a 60 s cycle and 0.5 split makes phase 0 red on [0,30), green on [30,60)
    signals = {"nodes": {node}, "offset": {node: 30.0}, "edge_phase": {(1, node, 0): 0},
               "cycle": 60.0, "green_split": 0.5}
    df = _advance([car], signals, 55)

    red = df[df["t"] <= 30]
    grn = df[df["t"] > 30]
    stop_line = 150.0
    # while red and still on edge A (idx 0), the car must never pass the stop line
    red_on_A = red[red["idx"] == 0]
    waited = red_on_A["pos"].max()
    # the red light is a stopped virtual car AT the line, so a correct driver halts
    # one standstill gap (s0) short of it, i.e. near stop_line - s0, not on the line
    halt_target = stop_line - config.IDM_S0
    ok = []
    ok.append(_check("never runs the red (stays at/behind the line)",
                     waited <= stop_line + 1e-6,
                     f"furthest point while red {waited:.3f} m (line at {stop_line:.0f} m)"))
    ok.append(_check("comes to a full stop just short of the line (by ~s0)",
                     bool(red_on_A["v"].min() < 0.1 and waited >= halt_target - 0.5),
                     f"halts at {waited:.2f} m = {stop_line - waited:.2f} m short of the "
                     f"line (s0 = {config.IDM_S0:.0f} m); min speed "
                     f"{red_on_A['v'].min():.4f} m/s"))
    ok.append(_check("departs on green (crosses onto the next segment)",
                     bool((grn["idx"] == 1).any()),
                     f"reached segment idx {int(grn['idx'].max())} after green"))
    _save_trace(df, "red_light")
    return all(ok)


# --- scenario 4: saturation -------------------------------------------------

def _run_on_network(G, n_vehicles, n_steps):
    """Build n_vehicles real trips on G, step them, return their final speeds.
    Uses the real kernel so the congestion we measure is the model's own."""
    nodes = list(G.nodes)
    rng = random.Random(config.RANDOM_SEED)
    signals = prepare_signals(G)
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox = defaultdict(float), defaultdict(float)
    vehicles = []
    for vid in range(n_vehicles):
        veh = make_vehicle(G, nodes, rng, vid)
        if veh is not None:
            vehicles.append(veh)
    for s in range(n_steps):
        step_vehicles(vehicles, config.DT, s * config.DT,
                      seg_tot, seg_nox, coeffs, G, nodes, rng, signals)
    return np.array([veh["v"] for veh in vehicles])


def scenario_saturation(G):
    print("\n4) SATURATION (Christof's 'place a thousand cars')")
    print("   Same network, light load vs heavy load. Expect: under heavy load the")
    print("   mean speed collapses and many cars are stopped. Congestion is an")
    print("   emergent result of the interaction, not something coded in by hand.")
    light = _run_on_network(G, 15, 300)
    heavy = _run_on_network(G, 1500, 300)
    light_mean, heavy_mean = light.mean(), heavy.mean()
    light_stop = float((light < 0.5).mean())
    heavy_stop = float((heavy < 0.5).mean())

    ok = []
    ok.append(_check("heavy-load mean speed is far below light-load",
                     heavy_mean < 0.6 * light_mean,
                     f"light {light_mean:.2f} m/s -> heavy {heavy_mean:.2f} m/s"))
    ok.append(_check("heavy load leaves many cars stopped",
                     heavy_stop > 2 * light_stop + 0.05,
                     f"stopped fraction: light {light_stop:.0%} -> heavy {heavy_stop:.0%}"))
    return all(ok)


if __name__ == "__main__":
    print("ABM validation test-bench  (real kernel, hand-checkable scenarios)")
    print("=" * 66)
    results = {
        "one car": scenario_one_car(),
        "two cars": scenario_two_cars(),
        "red light": scenario_red_light(),
    }
    G = prepare_network(get_network())
    results["saturation"] = scenario_saturation(G)

    print("\n" + "=" * 66)
    n_pass = sum(results.values())
    for name, ok in results.items():
        print(f"   {PASS if ok else FAIL}  {name}")
    print(f"\n{n_pass}/{len(results)} scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
