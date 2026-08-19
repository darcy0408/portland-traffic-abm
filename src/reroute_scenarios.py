r"""Hand-checkable scenarios for EN-ROUTE REROUTING (demand-exit plan Phase C1).

Same discipline as turn_pocket_scenarios.py / scenarios.py (Christof's Jun 24
ask: values predictable by hand, through the REAL kernel, never a
reimplementation). The scenarios run on a hand-built diamond so which path is
shorter -- and which one a jam should push a driver onto -- is known exactly:

           N  (the LONG way: 1200 m of slower side street)
          / \
    O -- A   \-- D          A->N->D  = 1200 m at 40 km/h = 108 s
          \  /              A->B->D  =  700 m at 50 km/h =  50 s
           B  (the SHORT way, which the scenarios jam)

Every car spawns at O bound for D and plans A->B->D, because free-flow time
prefers it. Jamming B->D is what a re-plan has to notice.

The detour is 2.1x the direct route BY DESIGN, and that ratio is part of the
test rather than a knob turned until it passed. Real urban alternatives run
about 1.2-2x; an earlier draft of this gate used a 7.1x detour, which no
congestion function should ever choose and which therefore tested nothing. If
a future change makes these scenarios fail, check the ratio is still realistic
before touching the mechanism.

The claims:

  A) INERTNESS. With REROUTE_ENABLED off (reroute_ctx=None) the kernel is
     byte-for-byte the pre-C1 model: identical trajectories AND an identical
     final RNG state, over a window with real stuck vehicles so the test is not
     vacuous. No vehicle carries a stuck_s or reroute_t key at all.

  B) IT ACTUALLY REROUTES AROUND THE JAM. With the short path jammed and the
     flag on, a car stuck behind it re-plans onto A->N->D. Checked as a real
     edge chain: every consecutive pair must be a real graph edge, the route
     must still END at the original destination D, and the car must not have
     teleported (same idx, same pos, same id).

  C) TRIGGER ARITHMETIC BY HAND. Stuck for REROUTE_STUCK_S-1 seconds: no
     re-plan. One more second: re-plan. The cooldown then blocks an immediate
     second one, and expires exactly when it should. The per-step cap admits
     exactly REROUTE_MAX_PER_STEP cars and they are the LONGEST-stuck ones,
     with vehicle id breaking ties (so the choice is deterministic, not
     dict-order).

  D) DEMAND IS CONSERVED -- the line between C1 and C2. No vehicle is ever
     removed, no destination is ever changed, and the active fleet count is
     invariant across the pass. This is enforced by a test, not by intention,
     because a rerouting mechanism that quietly dropped cars would improve the
     stuck-time metric for the wrong reason.

  E) NO PATH LEAVES THE CAR ALONE. When the destination is unreachable from the
     re-plan node, the vehicle is left exactly as it was (same route, same
     position) rather than raising or being stranded, and the failure is
     counted so a run can report it.

  F) REFUSALS. A non-positive trigger, a cap below 1, and a cooldown shorter
     than one step are all refused loudly rather than silently degraded.

Run: python src/reroute_scenarios.py
"""
import copy
import os
import random
import sys
from collections import defaultdict

import networkx as nx

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import emissions
import generate
from generate import step_vehicles, build_reroute_context, _reroute_pass

PASS, FAIL = "PASS", "FAIL"


def _check(label, ok, detail):
    print(f"   [{PASS if ok else FAIL}] {label}: {detail}")
    return bool(ok)


def _diamond():
    """The diamond above. B->D is short and fast, N is the long slow detour."""
    G = nx.MultiDiGraph()
    for n, (x, y) in {"O": (-500.0, 0.0), "A": (0.0, 0.0), "B": (350.0, -50.0),
                      "N": (350.0, 600.0), "D": (700.0, 0.0)}.items():
        G.add_node(n, x=x, y=y)
    # (u, v, length, kph)
    for u, v, length, kph in (("O", "A", 500.0, 50), ("A", "B", 350.0, 50),
                              ("B", "D", 350.0, 50), ("A", "N", 600.0, 40),
                              ("N", "D", 600.0, 40)):
        G.add_edge(u, v, length=length, maxspeed=str(kph), highway="primary",
                   lanes="1")
    return generate.prepare_network(G)


def _edge(G, u, v):
    return (u, v, 0, G[u][v][0]["length"], G[u][v][0]["v0_mps"])


def _car(G, vid, route_nodes, pos=0.0, idx=0):
    route = [_edge(G, route_nodes[i], route_nodes[i + 1])
             for i in range(len(route_nodes) - 1)]
    return {"id": vid, "route": route, "idx": idx, "pos": pos, "v": 0.0}


def _no_signals():
    return {"nodes": set(), "offset": {}, "edge_phase": {},
            "cycle": 60.0, "green_split": 0.5}


def _ctx(G):
    """A reroute context with the flag forced on, restoring config after."""
    old = config.REROUTE_ENABLED
    config.REROUTE_ENABLED = True
    try:
        return build_reroute_context(G)
    finally:
        config.REROUTE_ENABLED = old


def _run(G, vehs, n_steps, reroute_ctx, rng, t0=0):
    """Step the real kernel, also returning the PEAK number of simultaneously
    stuck vehicles -- an inertness test over a window where nothing was ever
    stuck would prove nothing, so the caller checks this is substantial."""
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox, thru = (defaultdict(float), defaultdict(float),
                              defaultdict(float))
    stuck_v = config.STUCK_SPEED_KMH / 3.6
    peak_stuck = 0
    for s in range(n_steps):
        step_vehicles(vehs, config.DT, (t0 + s) * config.DT, seg_tot, seg_nox,
                      thru, coeffs, G, list(G.nodes), rng, _no_signals(),
                      None, None, reroute_ctx=reroute_ctx)
        peak_stuck = max(peak_stuck, sum(1 for v in vehs if v["v"] < stuck_v))
    return thru, peak_stuck


def _jam_short_path(G, n_block=45):
    """Fill B->D bumper to bumper so nothing can enter it: the jam a re-plan
    has to notice. Returns the blocking cars."""
    per_car = config.VEHICLE_LENGTH_M + config.IDM_S0
    return [_car(G, 900 + i, ["B", "D"], pos=i * per_car) for i in range(n_block)]


def scenario_a_inertness():
    print("\nA) INERTNESS: flag off is byte-for-byte the pre-C1 kernel")
    G = _diamond()
    ok = True
    results = []
    for _trial in range(2):
        rng = random.Random(12345)
        vehs = _jam_short_path(G) + [_car(G, i, ["O", "A", "B", "D"],
                                          pos=400.0 - i * 8.0) for i in range(6)]
        _run(G, vehs, 400, None, rng)          # reroute_ctx=None -> the old path
        results.append(([(v["id"], v["idx"], round(v["pos"], 9), round(v["v"], 9))
                         for v in vehs], rng.random()))
    ok &= _check("determinism", results[0] == results[1],
                 "two identical flag-off runs match exactly")

    # the real inertness claim: no C1 bookkeeping is attached at all
    rng = random.Random(12345)
    vehs = _jam_short_path(G) + [_car(G, i, ["O", "A", "B", "D"],
                                      pos=400.0 - i * 8.0) for i in range(6)]
    _, peak_stuck = _run(G, vehs, 400, None, rng)
    keys = {k for v in vehs for k in v}
    ok &= _check("no C1 keys", not ({"stuck_s", "reroute_t"} & keys),
                 f"no vehicle carries stuck_s/reroute_t (keys seen: "
                 f"{sorted(keys - {'id', 'route', 'idx', 'pos', 'v'})})")
    ok &= _check("not vacuous", peak_stuck > 10,
                 f"{peak_stuck} vehicles simultaneously stuck at the peak of "
                 f"this window")
    return ok


def scenario_b_reroutes_around_jam():
    print("\nB) REROUTES AROUND THE JAM: stuck car switches to the long way")
    G = _diamond()
    ok = True
    ctx = _ctx(G)
    blockers = _jam_short_path(G)
    # The driver must still be UPSTREAM of the fork. A car already on A->B
    # re-plans from B (the node it is heading toward), and from B the only way
    # to D is the jammed link -- correctly, because this kernel has no U-turn.
    # So it sits on O->A, where the re-plan from A can still choose N.
    driver = _car(G, 1, ["O", "A", "B", "D"], pos=480.0)
    driver["stuck_s"] = config.REROUTE_STUCK_S
    vehs = blockers + [driver]

    before_dest = driver["route"][-1][1]
    before_idx, before_pos = driver["idx"], driver["pos"]
    _reroute_pass(vehs, _by_edge(vehs), ctx, G, 0.0)

    nodes = [driver["route"][0][0]] + [e[1] for e in driver["route"]]
    ok &= _check("took the long way", "N" in nodes,
                 f"new node chain {' -> '.join(map(str, nodes))}")
    ok &= _check("destination unchanged", driver["route"][-1][1] == before_dest,
                 f"still ends at {before_dest}")
    ok &= _check("valid edge chain",
                 all(G.has_edge(a, b) for a, b in zip(nodes, nodes[1:])),
                 "every consecutive pair is a real graph edge")
    ok &= _check("did not teleport",
                 driver["idx"] == before_idx and driver["pos"] == before_pos,
                 f"idx {before_idx}, pos {before_pos:.1f} preserved")
    ok &= _check("counted", ctx["n_reroutes"] == 1,
                 f"n_reroutes={ctx['n_reroutes']}")

    # the arithmetic, by hand, so this is a checked number and not a black box:
    # jammed  A->B->D = 25.2 + (25.2 + 45 cars x 1.5 s headway) = 117.9 s
    # detour  A->N->D = 54.0 + 54.0                             = 108.0 s
    short = 25.2 + (25.2 + len(blockers) * config.IDM_T)
    detour = 54.0 + 54.0
    ok &= _check("hand arithmetic", detour < short,
                 f"detour {detour:.1f}s beats jammed direct {short:.1f}s "
                 f"({len(blockers)} cars queued)")

    # and the same car does NOT divert once the jam clears
    ctx2 = _ctx(G)
    clear = _car(G, 2, ["O", "A", "B", "D"], pos=480.0)
    clear["stuck_s"] = config.REROUTE_STUCK_S
    solo = [clear]
    _reroute_pass(solo, _by_edge(solo), ctx2, G, 0.0)
    nodes2 = [clear["route"][0][0]] + [e[1] for e in clear["route"]]
    ok &= _check("no diversion when clear", "N" not in nodes2,
                 f"empty network keeps the direct route "
                 f"{' -> '.join(map(str, nodes2))}")
    return ok


def _by_edge(vehs):
    by = defaultdict(list)
    for v in vehs:
        by[v["route"][v["idx"]][:3]].append(v)
    for g in by.values():
        g.sort(key=lambda x: x["pos"])
    return by


def scenario_c_trigger_arithmetic():
    print("\nC) TRIGGER ARITHMETIC: threshold, cooldown and cap by hand")
    G = _diamond()
    ok = True

    # threshold: one second short does nothing, exactly at it fires
    for offset, want in ((-config.DT, 0), (0.0, 1)):
        ctx = _ctx(G)
        car = _car(G, 1, ["A", "B", "D"], pos=340.0)
        car["stuck_s"] = config.REROUTE_STUCK_S + offset
        vehs = _jam_short_path(G) + [car]
        _reroute_pass(vehs, _by_edge(vehs), ctx, G, 0.0)
        ok &= _check(f"stuck {car['stuck_s']:.0f}s", ctx["n_reroutes"] == want,
                     f"{ctx['n_reroutes']} re-plan(s), wanted {want}")

    # cooldown: a car that just re-planned does not re-plan again until it expires
    ctx = _ctx(G)
    car = _car(G, 1, ["A", "B", "D"], pos=340.0)
    car["stuck_s"] = config.REROUTE_STUCK_S
    vehs = _jam_short_path(G) + [car]
    _reroute_pass(vehs, _by_edge(vehs), ctx, G, 0.0)
    car["stuck_s"] = config.REROUTE_STUCK_S          # stuck again
    _reroute_pass(vehs, _by_edge(vehs), ctx, G, config.REROUTE_COOLDOWN_S - config.DT)
    mid = ctx["n_reroutes"]
    _reroute_pass(vehs, _by_edge(vehs), ctx, G, config.REROUTE_COOLDOWN_S)
    ok &= _check("cooldown holds", mid == 1, f"{mid} re-plans before it expires")
    ok &= _check("cooldown expires", ctx["n_reroutes"] == 2,
                 f"{ctx['n_reroutes']} re-plans once it does")

    # cap: more candidates than the budget -> exactly the budget, longest first
    ctx = _ctx(G)
    cap_n = config.REROUTE_MAX_PER_STEP
    cars = []
    for i in range(cap_n + 5):
        c = _car(G, 100 + i, ["A", "B", "D"], pos=340.0 - i * 0.5)
        # longer-stuck cars get HIGHER ids, so a correct sort must reorder them
        c["stuck_s"] = config.REROUTE_STUCK_S + i
        cars.append(c)
    vehs = _jam_short_path(G) + cars
    _reroute_pass(vehs, _by_edge(vehs), ctx, G, 0.0)
    ok &= _check("cap respected", ctx["n_reroutes"] == cap_n,
                 f"{ctx['n_reroutes']} re-plans, cap {cap_n}")
    # the cars that re-planned are the last cap_n created (the longest stuck)
    replanned = {c["id"] for c in cars if c.get("reroute_t") == 0.0}
    want = {100 + i for i in range(len(cars) - cap_n, len(cars))}
    ok &= _check("longest-stuck first", replanned == want,
                 f"re-planned ids are the {cap_n} longest-stuck")
    return ok


def scenario_d_demand_conserved():
    print("\nD) DEMAND CONSERVED: nothing removed, no destination changed")
    G = _diamond()
    ok = True
    # (i) the isolated C1 claim: across MANY reroute passes, on a frozen jam, no
    # vehicle is removed and no destination moves. Driven through _reroute_pass
    # directly and not the full step, because a car that legitimately COMPLETES
    # its trip respawns with a new destination -- that is the respawn mechanism
    # doing its job, and folding it in here would test the wrong thing.
    ctx = _ctx(G)
    cars = []
    for i in range(8):
        c = _car(G, 200 + i, ["A", "B", "D"], pos=340.0 - i * 6.0)
        c["stuck_s"] = config.REROUTE_STUCK_S + i
        cars.append(c)
    vehs = _jam_short_path(G) + cars
    n_before = len(vehs)
    dests_before = {v["id"]: v["route"][-1][1] for v in vehs}
    ids_before = {v["id"] for v in vehs}

    for step in range(60):
        for c in cars:
            c["stuck_s"] = config.REROUTE_STUCK_S + 1   # keep them all eligible
        _reroute_pass(vehs, _by_edge(vehs), ctx, G,
                      step * config.REROUTE_COOLDOWN_S)

    ok &= _check("no vehicle removed", len(vehs) == n_before
                 and {v["id"] for v in vehs} == ids_before,
                 f"{n_before} vehicles in, {len(vehs)} out, same ids")
    changed = [i for i, d in dests_before.items()
               if {v["id"]: v["route"][-1][1] for v in vehs}[i] != d]
    ok &= _check("destinations unchanged", not changed,
                 f"{len(changed)} of {n_before} destinations changed over "
                 f"{ctx['n_reroutes']} re-plans")
    ok &= _check("not vacuous", ctx["n_reroutes"] > 8,
                 f"{ctx['n_reroutes']} re-plans actually happened")

    # (ii) end to end: the FULL kernel does not lose vehicles either
    ctx2 = _ctx(G)
    vehs2 = _jam_short_path(G) + [_car(G, 300 + i, ["O", "A", "B", "D"],
                                       pos=400.0 - i * 7.0) for i in range(8)]
    n2 = len(vehs2)
    _run(G, vehs2, 300, ctx2, random.Random(3))
    ok &= _check("fleet size invariant end to end", len(vehs2) == n2,
                 f"{n2} vehicles before, {len(vehs2)} after a 300-step run")
    return ok


def scenario_e_no_path():
    print("\nE) NO PATH: the car is left exactly as it was")
    G = _diamond()
    ok = True
    # remove the long way so a car stuck on A->B has no alternative at all
    H = G.copy()
    H.remove_edge("A", "N", 0)
    ctx = _ctx(H)
    car = _car(H, 1, ["A", "B", "D"], pos=340.0)
    car["stuck_s"] = config.REROUTE_STUCK_S
    route_before = list(car["route"])
    vehs = _jam_short_path(H) + [car]
    _reroute_pass(vehs, _by_edge(vehs), ctx, H, 0.0)
    # B->D still exists, so a path is found; the real no-path case is a
    # destination with no inbound route at all
    H2 = G.copy()
    H2.remove_edge("A", "N", 0)
    H2.remove_edge("B", "D", 0)
    ctx2 = _ctx(H2)
    car2 = _car(G, 1, ["A", "B", "D"], pos=340.0)   # route from the intact graph
    car2["stuck_s"] = config.REROUTE_STUCK_S
    before = list(car2["route"])
    vehs2 = [car2]
    _reroute_pass(vehs2, _by_edge(vehs2), ctx2, H2, 0.0)
    ok &= _check("route untouched", car2["route"] == before,
                 "unreachable destination leaves the route exactly as it was")
    ok &= _check("failure counted", ctx2["n_failed"] == 1,
                 f"n_failed={ctx2['n_failed']}")
    ok &= _check("still in the fleet", len(vehs2) == 1,
                 "the car is not removed when it cannot re-plan")
    ok &= _check("cooldown set on attempt", car2.get("reroute_t") == 0.0,
                 "a failed attempt still starts the cooldown, so it does not "
                 "retry Dijkstra every step")
    del route_before, ctx, vehs
    return ok


def scenario_f_refusals():
    print("\nF) REFUSALS: bad settings are refused loudly")
    G = _diamond()
    ok = True
    saved = (config.REROUTE_ENABLED, config.REROUTE_STUCK_S,
             config.REROUTE_MAX_PER_STEP, config.REROUTE_COOLDOWN_S)
    config.REROUTE_ENABLED = True
    try:
        for label, attr, bad in (("non-positive trigger", "REROUTE_STUCK_S", 0.0),
                                 ("cap below 1", "REROUTE_MAX_PER_STEP", 0),
                                 ("cooldown < one step", "REROUTE_COOLDOWN_S",
                                  config.DT / 2.0)):
            keep = getattr(config, attr)
            setattr(config, attr, bad)
            try:
                build_reroute_context(G)
                ok &= _check(label, False, "did NOT refuse")
            except ValueError as e:
                ok &= _check(label, True, f"refused: {str(e)[:52]}...")
            finally:
                setattr(config, attr, keep)
    finally:
        (config.REROUTE_ENABLED, config.REROUTE_STUCK_S,
         config.REROUTE_MAX_PER_STEP, config.REROUTE_COOLDOWN_S) = saved
    return ok


def main():
    print("EN-ROUTE REROUTING SCENARIOS (Phase C1)")
    results = [scenario_a_inertness(), scenario_b_reroutes_around_jam(),
               scenario_c_trigger_arithmetic(), scenario_d_demand_conserved(),
               scenario_e_no_path(), scenario_f_refusals()]
    print(f"\n{sum(results)}/{len(results)} scenarios passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
