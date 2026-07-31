"""Hand-checkable scenarios for the HOURLY DEMAND PROFILE (real-demand upgrade
plan, Phase A1: respawn gating so the active fleet tracks an hour-of-day quota).

Same discipline as scenarios.py / stuck_scenarios.py (Christof's Jun 24 ask:
values predictable by hand, through the REAL kernel, never a reimplementation).
Unlike those gates, cars here must genuinely FINISH trips (parking happens only
at trip completion), so the scenarios run on a small real networkx ring with
uniform-random trips instead of hand-placed cars on dummy routes.

  A) INERTNESS. A FLAT profile (m(h) = 1 for every hour) quotas the full fleet
     every hour, so nothing ever parks, nothing ever releases, and not one
     extra RNG draw is consumed. The flag-on flat-profile run must match the
     base run BITWISE: every car's (idx, pos, v) at every sampled step AND the
     final state of the shared RNG stream (the strongest possible proof that
     the gating code consumed no draw). The run is only meaningful if trips
     actually finish, so the base arm also counts respawns and the gate demands
     plenty.

  B) CONSERVATION + THE SQUARE WAVE, BY HAND. A two-level profile alternating
     m = 1.0 (even hours) and m = 0.4 (odd hours) on a 40-car fleet gives
     quotas of exactly 40 and 16. Predictions, checked every step over 2.5
     simulated hours: parked + active == fleet ALWAYS; hour 0 holds active at
     40; in hour 1 the active fleet only ever FALLS (cars park at trip
     completion, never vanish mid-trip), reaches exactly 16 well inside the
     hour, and holds there; at the hour-2 boundary the parked pool releases and
     the active fleet is back at 40 within ONE step.

  C) THE QUOTA ARITHMETIC, BY HAND. build_profile_context and the start-hour
     offset are checked against hand-computed values: quotas are
     round(fleet * m/m_peak) (the PM shoulder of an asymmetric shape lands
     where it should), DEMAND_PROFILE_START_HOUR shifts which quota t=0 reads,
     profile_park_down parks a fresh fleet down to exactly hour zero's quota,
     and a malformed shape (wrong length) is refused loudly.

(kernel_regression.py additionally proves the surrounding edit changed no base
physics with the flag off.)

Run: python src/demand_profile_scenarios.py
"""
import os
import sys
import random
from collections import defaultdict

import numpy as np
import networkx as nx

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import emissions
from generate import (step_vehicles, make_vehicle, prepare_network,
                      build_profile_context, profile_park_down, _profile_quota)

PASS, FAIL = "PASS", "FAIL"


def _check(label, ok, detail):
    print(f"   [{PASS if ok else FAIL}] {label}: {detail}")
    return bool(ok)


def _no_signals():
    return {"nodes": set(), "offset": {}, "edge_phase": {},
            "cycle": 60.0, "green_split": 0.5}


def _ring_graph():
    """A 4-node, 8-directed-edge ring of 150 m residential streets: the
    smallest real graph on which uniform-random trips route, run, and finish
    in tens of seconds, so respawn/park events are frequent."""
    G = nx.MultiDiGraph()
    coords = {0: (0.0, 0.0), 1: (150.0, 0.0), 2: (150.0, 150.0), 3: (0.0, 150.0)}
    for n, (x, y) in coords.items():
        G.add_node(n, x=x, y=y)
    for u, v in ((0, 1), (1, 2), (2, 3), (3, 0)):
        for a, b in ((u, v), (v, u)):
            G.add_edge(a, b, length=150.0, maxspeed="50", highway="residential")
    return prepare_network(G)


def _spawn(G, nodes, rng, n):
    """Spawn a fleet the same way run_simulation does (uniform-random trips)."""
    vehicles = []
    for vid in range(n):
        veh = make_vehicle(G, nodes, rng, vid)   # demand/through None: uniform
        if veh is not None:
            vehicles.append(veh)
    return vehicles


def _profile_config(shape, start_hour=0):
    """Set the demand-profile config knobs; returns the old values."""
    old = (config.DEMAND_PROFILE_ENABLED, config.DEMAND_PROFILE,
           config.DEMAND_PROFILE_START_HOUR)
    config.DEMAND_PROFILE_ENABLED = True
    config.DEMAND_PROFILE = shape
    config.DEMAND_PROFILE_START_HOUR = start_hour
    return old


def _restore_config(old):
    (config.DEMAND_PROFILE_ENABLED, config.DEMAND_PROFILE,
     config.DEMAND_PROFILE_START_HOUR) = old


def scenario_inertness():
    print("\nA) INERTNESS: a flat profile is bitwise the base model, RNG included")
    print("   Two identically seeded 600 s runs on the ring, one with the flag")
    print("   off, one with the flag ON and m(h)=1 for every hour. Same cars,")
    print("   same trajectories, same RNG state after -- and the base arm must")
    print("   prove trips really finished (a run with no respawns proves nothing).")
    n_steps, fleet_size = 600, 30
    G = _ring_graph()
    nodes = list(G.nodes)
    coeffs = emissions.active_coeffs()
    signals = _no_signals()

    def run(profile_on):
        rng = random.Random(7)
        vehs = _spawn(G, nodes, rng, fleet_size)
        ctx = None
        if profile_on:
            old = _profile_config([1.0] * 24)
            try:
                ctx = build_profile_context(len(vehs))
                profile_park_down(ctx, vehs)
            finally:
                _restore_config(old)
        # count respawns via route-object identity: veh.update(fresh) swaps in a
        # brand-new route list, so a changed id() marks a completed trip
        route_ids = {v["id"]: id(v["route"]) for v in vehs}
        respawns = 0
        seg_tot, seg_nox, seg_thru = (defaultdict(float), defaultdict(float),
                                      defaultdict(float))
        for s in range(n_steps):
            step_vehicles(vehs, config.DT, s * config.DT, seg_tot, seg_nox,
                          seg_thru, coeffs, G, nodes, rng, signals, None, None,
                          profile_ctx=ctx)
            for v in vehs:
                if id(v["route"]) != route_ids.get(v["id"]):
                    respawns += 1
                    route_ids[v["id"]] = id(v["route"])
        traj = np.array(sorted((v["id"], v["idx"], v["pos"], v["v"]) for v in vehs))
        return traj, rng.getstate(), respawns, ctx

    base_traj, base_rng, respawns, _ = run(profile_on=False)
    flat_traj, flat_rng, _, ctx = run(profile_on=True)

    ok = []
    ok.append(_check("the base arm exercises the respawn path hard",
                     respawns >= 50, f"{respawns} completed trips in {n_steps} s"))
    ok.append(_check("flat profile parks nobody, start to finish",
                     ctx is not None and len(ctx["parked"]) == 0,
                     f"parked pool holds {len(ctx['parked'])} ids"))
    same = base_traj.shape == flat_traj.shape and np.array_equal(base_traj, flat_traj)
    ok.append(_check("trajectories bitwise identical (id, idx, pos, v)", same,
                     "bitwise equal" if same else
                     f"max abs diff {np.abs(base_traj - flat_traj).max():.3g}"))
    ok.append(_check("shared RNG stream consumed identically",
                     base_rng == flat_rng,
                     "final getstate() equal" if base_rng == flat_rng
                     else "RNG states DIVERGED -- the gating consumed a draw"))
    return all(ok)


def scenario_square_wave():
    print("\nB) CONSERVATION + SQUARE WAVE: quotas 40/16, checked every step")
    print("   m alternates 1.0 (even hours) / 0.4 (odd hours) on a 40-car fleet.")
    print("   parked + active == fleet always; hour 0 holds 40; hour 1 decays")
    print("   monotonically to exactly 16 and holds; hour 2 refills in ONE step.")
    fleet_size = 40
    n_steps = 9000                     # 2.5 h: peak hour, ebb hour, refill edge
    G = _ring_graph()
    nodes = list(G.nodes)
    coeffs = emissions.active_coeffs()
    signals = _no_signals()

    rng = random.Random(11)
    vehs = _spawn(G, nodes, rng, fleet_size)
    fleet = len(vehs)                  # should be 40; quotas hand-derived from it
    shape = [1.0 if h % 2 == 0 else 0.4 for h in range(24)]
    old = _profile_config(shape)
    try:
        ctx = build_profile_context(fleet)
        profile_park_down(ctx, vehs)   # hour 0 quota == fleet: parks nobody
        active = []
        conserve_bad = 0
        seg_tot, seg_nox, seg_thru = (defaultdict(float), defaultdict(float),
                                      defaultdict(float))
        for s in range(n_steps):
            step_vehicles(vehs, config.DT, s * config.DT, seg_tot, seg_nox,
                          seg_thru, coeffs, G, nodes, rng, signals, None, None,
                          profile_ctx=ctx)
            active.append(len(vehs))
            if len(vehs) + len(ctx["parked"]) != fleet:
                conserve_bad += 1
    finally:
        _restore_config(old)

    active = np.array(active)
    hour0, hour1, hour2 = active[:3600], active[3600:7200], active[7200:]
    q_hi, q_lo = fleet, round(fleet * 0.4)
    ok = []
    ok.append(_check("hand-derived quotas from the shape",
                     ctx["quota"][:3] == [q_hi, q_lo, q_hi],
                     f"quota[0:3] = {ctx['quota'][:3]} (want [{q_hi}, {q_lo}, {q_hi}])"))
    ok.append(_check("conservation: parked + active == fleet at EVERY step",
                     conserve_bad == 0,
                     f"{conserve_bad} of {n_steps} steps violated"
                     if conserve_bad else f"held for all {n_steps} steps"))
    ok.append(_check("hour 0 (m=1.0) holds the full fleet",
                     (hour0 == q_hi).all(),
                     f"active range {hour0.min()}-{hour0.max()} (want {q_hi})"))
    decay = hour1[hour1 > q_lo]        # the ebb: every step until quota reached
    mono = (np.diff(hour1) <= 0).all() or (len(decay) < len(hour1)
                                           and (np.diff(decay) <= 0).all()
                                           and (hour1[len(decay):] == q_lo).all())
    ok.append(_check("hour 1 (m=0.4) only ever ebbs, then holds the quota",
                     mono and hour1[-1] == q_lo,
                     f"decayed {q_hi}->{q_lo} in {len(decay)} s, "
                     f"held {len(hour1) - len(decay)} s"))
    ok.append(_check("cars only leave at trip completion (no cliff)",
                     len(decay) > 10,
                     f"the ebb took {len(decay)} s, not one step"))
    ok.append(_check("hour 2 boundary: parked pool refills the fleet in ONE step",
                     hour2[0] == q_hi and (hour2 == q_hi).all(),
                     f"active {hour2[0]} on the first step of hour 2 (want {q_hi})"))
    return all(ok)


def scenario_quota_arithmetic():
    print("\nC) QUOTA ARITHMETIC: context values against hand-computed numbers")
    print("   round(fleet * m/m_peak) quotas, the start-hour offset, park-down")
    print("   to hour zero's quota, and a loud refusal of a malformed shape.")
    ok = []
    # an asymmetric hand-made shape: peak 0.8 at hour 8, PM shoulder 0.6 at 17,
    # overnight 0.1 -- quotas for fleet 50 are round(50*m/0.8) by hand
    shape = [0.1] * 24
    shape[8], shape[17] = 0.8, 0.6
    old = _profile_config(shape, start_hour=17)
    try:
        ctx = build_profile_context(50)
        want = {8: 50, 17: round(50 * 0.6 / 0.8), 3: round(50 * 0.1 / 0.8)}
        got = {h: ctx["quota"][h] for h in want}
        ok.append(_check("quotas are round(fleet * m/m_peak)",
                         got == want, f"hours {sorted(want)}: {got} (want {want})"))
        # start_hour=17: t=0 reads hour 17's quota, one sim-hour later hour 18's
        ok.append(_check("START_HOUR offsets the clock (t=0 is hour 17)",
                         _profile_quota(ctx, 0.0) == want[17]
                         and _profile_quota(ctx, 3600.0) == ctx["quota"][18],
                         f"t=0 -> {_profile_quota(ctx, 0.0)} (want {want[17]}), "
                         f"t=3600 -> {_profile_quota(ctx, 3600.0)} "
                         f"(want {ctx['quota'][18]})"))
        # park-down: a 50-car fresh fleet parks down to hour 17's quota
        fake_fleet = [{"id": i} for i in range(50)]
        profile_park_down(ctx, fake_fleet)
        ok.append(_check("park-down leaves exactly hour zero's quota active",
                         len(fake_fleet) == want[17]
                         and len(ctx["parked"]) == 50 - want[17],
                         f"{len(fake_fleet)} active + {len(ctx['parked'])} parked"))
    finally:
        _restore_config(old)
    # malformed shape: 23 values must be refused, not silently accepted
    old = _profile_config([1.0] * 23)
    try:
        build_profile_context(50)
        refused = False
    except ValueError:
        refused = True
    finally:
        _restore_config(old)
    ok.append(_check("a 23-value shape is refused loudly", refused,
                     "ValueError raised" if refused else "accepted silently!"))
    return all(ok)


if __name__ == "__main__":
    print("Hourly demand-profile scenarios  (real kernel, hand-checkable)")
    print("=" * 66)
    results = {"inertness": scenario_inertness(),
               "square_wave": scenario_square_wave(),
               "quota_arithmetic": scenario_quota_arithmetic()}
    print("\n" + "=" * 66)
    for name, okay in results.items():
        print(f"   {PASS if okay else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} demand-profile scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
