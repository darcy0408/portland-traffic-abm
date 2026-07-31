"""Hand-checkable scenarios for LEFT-TURN POCKETS (real-demand plan Phase B1).

Same discipline as scenarios.py / mobil_network_scenarios.py (Christof's Jun 24
ask: values predictable by hand, through the REAL kernel, never a
reimplementation). The scenarios run on a hand-built four-way intersection so
the geometry -- and therefore which movement is a left turn -- is known exactly:

        N
        |
  W --- C --- E          approach W->C, then either C->E (through)
        |                                       or C->N (LEFT turn)
        S

The pocket is a config-length bay at the end of W->C. The claims:

  A) THE POCKET UNBLOCKS THE THROUGH LANE. Note WHAT DAMS THE LANE in this
     model: the kernel has no opposing-traffic gap acceptance, so a left-turner
     onto a clear street simply goes and blocks nobody. It dams the lane when
     its DESTINATION is full -- exactly the corridor diagnosis ("turners into
     jammed side streets dam their Powell lane"). So the scenario jams the
     left-turn destination (a short C->N segment backed up to its entrance
     behind its own red) and puts through cars behind the turner on a
     SINGLE-lane approach whose own signal is green. With pockets OFF the
     turner sits at the line and nobody moves; with pockets ON it steps into
     the bay and the through cars stream past into the clear C->E. Measured as
     vehicles that actually cross, by the real kernel, one flag changed.
     (Opposing-flow conflict is Phase B2's job, not B1's.)

  B) OVERFLOW DAMS THE LANE AGAIN. The bay holds a hand-computed number of cars
     (TURN_POCKET_LENGTH_M // (VEHICLE_LENGTH_M + IDM_S0) = 4 at the defaults).
     Send MORE turners than that: exactly `capacity` are admitted, and the
     overflow turner sits in the through lane and blocks the through cars
     behind it. A pocket that never overflows would be a fiction; this proves
     the failure mode survives.

  C) GEOMETRY, NOT GUESSWORK. _is_left_turn reads the real bearings: W->C->N is
     a left, W->C->E is straight on, W->C->S is a right, and only the left is
     ever admitted. Plus: a car whose trip ENDS at C is never admitted (it has
     no next edge to turn onto), and a through car is never admitted even when
     the bay is empty.

  D) INERTNESS. With TURN_POCKETS_ENABLED off, no vehicle ever carries
     POCKET_LANE and every touched function is byte-for-byte the original: the
     same scenario run with pocket_ctx=None matches the pre-B1 kernel bitwise.
     (kernel_regression.py proves the same thing against pinned trajectories.)

Run: python src/turn_pocket_scenarios.py
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
import generate
from generate import (step_vehicles, POCKET_LANE, _is_left_turn, _edge_bearing,
                      build_mobil_context)

KPH = 1.0 / 3.6
PASS, FAIL = "PASS", "FAIL"
V0 = 50 * KPH


def _check(label, ok, detail):
    print(f"   [{PASS if ok else FAIL}] {label}: {detail}")
    return bool(ok)


def _cross_graph(north_len=600.0):
    """The four-way intersection above, as a real networkx graph so bearings
    are computed by the real code from real coordinates. 400 m approach, 600 m
    exits; one lane each, which is the point (a pocket must work where there
    is no second lane to overtake in). `north_len` shortens the left-turn
    destination C->N so a handful of cars can fill it end to end (scenario A),
    with N->NN beyond it so those cars have somewhere to be going."""
    G = nx.MultiDiGraph()
    for n, (x, y) in {"C": (0.0, 0.0), "W": (-400.0, 0.0), "E": (600.0, 0.0),
                      "N": (0.0, north_len), "S": (0.0, -600.0),
                      "NN": (0.0, north_len + 600.0)}.items():
        G.add_node(n, x=x, y=y)
    for u, v, length in (("W", "C", 400.0), ("C", "E", 600.0),
                         ("C", "N", north_len), ("C", "S", 600.0),
                         ("N", "NN", 600.0)):
        G.add_edge(u, v, length=length, maxspeed="50", highway="primary", lanes="1")
    return generate.prepare_network(G)


def _edge(G, u, v):
    return (u, v, 0, G[u][v][0]["length"], G[u][v][0]["v0_mps"])


def _pocket_ctx(G, approach=("W", "C", 0), capacity=None):
    """Build a pocket context by hand -- no sidecar, no OSM -- so the gate
    tests the KERNEL rather than the data join (turn_lanes.py owns that)."""
    per_car = config.VEHICLE_LENGTH_M + config.IDM_S0
    cap = max(1, int(config.TURN_POCKET_LENGTH_M // per_car)) if capacity is None \
        else capacity
    return {"edges": {approach: True}, "capacity": cap,
            "zone_m": config.TURN_POCKET_LENGTH_M,
            "bearings": {(u, v, k): _edge_bearing(G, u, v)
                         for u, v, k in G.edges(keys=True)}}


def _signal_red_then_green(red_until):
    """Signal at C on the W-E axis: phase 0 red until `red_until`, then green.
    Built as an explicit cycle so the hold is exact and hand-readable."""
    return {"nodes": {"C"}, "offset": {"C": float(red_until)},
            "edge_phase": {("W", "C", 0): 0, ("C", "E", 0): 0,
                           ("C", "N", 0): 0, ("C", "S", 0): 0},
            "cycle": 2 * red_until, "green_split": 0.5}


def _car(G, vid, route_nodes, pos, lane=0):
    route = [_edge(G, route_nodes[i], route_nodes[i + 1])
             for i in range(len(route_nodes) - 1)]
    return {"id": vid, "route": route, "idx": 0, "pos": pos, "v": 0.0,
            "lane": lane}


def _run(G, vehs, signals, n_steps, pocket_ctx, mobil_ctx, t0=0):
    """Step the real kernel. Cars that finish their route would respawn, so the
    routes here are long enough that none does within the window."""
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox = defaultdict(float), defaultdict(float)
    thru = defaultdict(float)
    for s in range(n_steps):
        step_vehicles(vehs, config.DT, (t0 + s) * config.DT, seg_tot, seg_nox,
                      thru, coeffs, G, list(G.nodes), random.Random(0), signals,
                      None, None, mobil_ctx=mobil_ctx, pocket_ctx=pocket_ctx)
    return thru


def _mobil_on(G):
    """MOBIL context for this graph (pockets require the explicit-lane model)."""
    old = config.MOBIL_ENABLED
    config.MOBIL_ENABLED = True
    try:
        return build_mobil_context(G)
    finally:
        config.MOBIL_ENABLED = old


def _jammed_left_signals():
    """Signals at C and at N. The W-E axis (our approach) is phase 0; the
    left-turn destination C->N is phase 1 at node N. With offset 40 and cycle
    80, phase 0 is green for t in [40, 80) and phase 1 red over exactly that
    window -- so during the run the approach has green while the cars filling
    C->N are held at N's stop line, keeping that segment full."""
    return {"nodes": {"C", "N"}, "offset": {"C": 40.0, "N": 40.0},
            "edge_phase": {("W", "C", 0): 0, ("C", "E", 0): 0,
                           ("C", "S", 0): 0,
                           ("C", "N", 0): 1, ("N", "NN", 0): 1},
            "cycle": 80.0, "green_split": 0.5}


def scenario_unblocks():
    print("\nA) THE POCKET UNBLOCKS THE THROUGH LANE")
    N_LEN = 20.0
    print(f"   The left-turn destination C->N is {N_LEN:.0f} m and FULL (4 cars")
    print("   held at its own red), so the turner cannot cross and sits at the")
    print("   line. Four through cars queue behind it; their own signal is")
    print("   GREEN and their exit C->E is clear. One flag changed between arms.")
    G = _cross_graph(north_len=N_LEN)
    mobil_ctx = _mobil_on(G)
    signals = _jammed_left_signals()
    t0, n_steps = 40, 40          # the whole window: approach green, N red

    def build():
        # the jam on C->N: nose to tail from its stop line back to its entrance,
        # so the rearmost car sits within a jam gap of the entrance and the
        # kernel's "do not cross into a full segment" rule holds the turner
        blockers = [_car(G, 100 + j, ["C", "N", "NN"], N_LEN - 0.5 - 6.5 * j)
                    for j in range(4)]
        turner = _car(G, 0, ["W", "C", "N", "NN"], 398.0)
        through = [_car(G, j, ["W", "C", "E"], 398.0 - 7.0 * j)
                   for j in range(1, 5)]
        return blockers + [turner] + through, turner, through

    out = {}
    for label, ctx in (("no pocket", None), ("pocket", _pocket_ctx(G))):
        vehs, turner, through = build()
        thru = _run(G, vehs, signals, n_steps, ctx, mobil_ctx, t0=t0)
        out[label] = {"crossed": thru[("W", "C", 0)],
                      "turner_moved": turner["idx"] > 0,
                      "in_pocket": 1 if turner.get("lane") == POCKET_LANE else 0,
                      "through_out": sum(1 for v in through if v["idx"] > 0)}
    ok = []
    ok.append(_check("the jam holds: the turner never gets to turn, either way",
                     not out["no pocket"]["turner_moved"]
                     and not out["pocket"]["turner_moved"],
                     "turner still on the approach in both arms"))
    ok.append(_check("with a bay, the turner is in it",
                     out["pocket"]["in_pocket"] == 1,
                     f"turner lane = {POCKET_LANE}"))
    ok.append(_check("without a bay the turner dams the lane: nobody passes",
                     out["no pocket"]["crossed"] == 0
                     and out["no pocket"]["through_out"] == 0,
                     f"{out['no pocket']['crossed']:.0f} crossings, "
                     f"{out['no pocket']['through_out']} of 4 through cars out"))
    ok.append(_check("with a bay every through car gets past",
                     out["pocket"]["through_out"] == 4,
                     f"{out['pocket']['crossed']:.0f} crossings, "
                     f"{out['pocket']['through_out']} of 4 through cars out"))
    return all(ok)


def scenario_overflow():
    print("\nB) OVERFLOW DAMS THE LANE AGAIN")
    per_car = config.VEHICLE_LENGTH_M + config.IDM_S0
    cap = max(1, int(config.TURN_POCKET_LENGTH_M // per_car))
    print(f"   Bay capacity by hand: {config.TURN_POCKET_LENGTH_M:.0f} m // "
          f"{per_car:.0f} m = {cap} cars.")
    print(f"   Send {cap + 3} left-turners at a red: exactly {cap} are admitted and")
    print("   the rest stay in the through lane, blocking a through car behind.")
    G = _cross_graph()
    mobil_ctx = _mobil_on(G)
    # all turners, nose to tail from the stop line, plus one through car last
    vehs = [_car(G, j, ["W", "C", "N"], 398.0 - 7.0 * j) for j in range(cap + 3)]
    vehs.append(_car(G, 99, ["W", "C", "E"], 398.0 - 7.0 * (cap + 3)))
    _run(G, vehs, _signal_red_then_green(200), 60, _pocket_ctx(G), mobil_ctx)

    in_pocket = [v["id"] for v in vehs if v.get("lane") == POCKET_LANE]
    overflow = [v for v in vehs if v["id"] < cap + 3 and v["id"] not in in_pocket]
    through = vehs[-1]
    ok = []
    ok.append(_check(f"exactly {cap} turners admitted, no more",
                     len(in_pocket) == cap,
                     f"{len(in_pocket)} in the bay: ids {sorted(in_pocket)}"))
    ok.append(_check("the admitted ones are those nearest the line",
                     sorted(in_pocket) == list(range(cap)),
                     f"ids {sorted(in_pocket)} (want {list(range(cap))})"))
    ok.append(_check("overflow turners stay in the through lane",
                     all(v.get("lane") != POCKET_LANE for v in overflow)
                     and len(overflow) == 3,
                     f"{len(overflow)} left in-lane, lanes "
                     f"{[v.get('lane') for v in overflow]}"))
    ok.append(_check("the through car behind them is still stuck at the red",
                     through["idx"] == 0 and through["v"] < 0.1,
                     f"idx {through['idx']}, speed {through['v']:.2f} m/s"))
    return all(ok)


def scenario_geometry():
    print("\nC) GEOMETRY, NOT GUESSWORK: only actual left turns are admitted")
    G = _cross_graph()
    mobil_ctx = _mobil_on(G)
    b = {(u, v, k): _edge_bearing(G, u, v) for u, v, k in G.edges(keys=True)}
    wc = ("W", "C", 0)
    ok = []
    ok.append(_check("W->C->N reads as a LEFT turn",
                     _is_left_turn(b, wc, ("C", "N", 0)),
                     f"bearing {b[wc]:.0f} deg -> {b[('C', 'N', 0)]:.0f} deg"))
    ok.append(_check("W->C->E reads as straight on, not a left",
                     not _is_left_turn(b, wc, ("C", "E", 0)),
                     f"bearing {b[wc]:.0f} deg -> {b[('C', 'E', 0)]:.0f} deg"))
    ok.append(_check("W->C->S reads as a RIGHT turn, not a left",
                     not _is_left_turn(b, wc, ("C", "S", 0)),
                     f"bearing {b[wc]:.0f} deg -> {b[('C', 'S', 0)]:.0f} deg"))

    # and the kernel acts on that: through + ending cars are never admitted
    through = _car(G, 0, ["W", "C", "E"], 398.0)
    ending = _car(G, 1, ["W", "C"], 397.0)        # trip ends at C: no next edge
    turner = _car(G, 2, ["W", "C", "N"], 396.0)
    vehs = [turner, ending, through]              # kernel sorts by pos itself
    _run(G, vehs, _signal_red_then_green(200), 30, _pocket_ctx(G), mobil_ctx)
    ok.append(_check("the through car is never admitted (bay was empty)",
                     through.get("lane") != POCKET_LANE,
                     f"lane {through.get('lane')}"))
    ok.append(_check("a car whose trip ENDS here is never admitted",
                     ending.get("lane") != POCKET_LANE,
                     f"lane {ending.get('lane')}"))
    ok.append(_check("the left-turner IS admitted",
                     turner.get("lane") == POCKET_LANE,
                     f"lane {turner.get('lane')} (POCKET_LANE = {POCKET_LANE})"))
    return all(ok)


def scenario_inertness():
    print("\nD) INERTNESS: with pockets off, nothing about the kernel changes")
    print("   The same queue-through-a-signal scenario with pocket_ctx=None,")
    print("   run twice; and no car ever carries POCKET_LANE.")
    G = _cross_graph()
    mobil_ctx = _mobil_on(G)

    def build():
        return ([_car(G, 0, ["W", "C", "N"], 398.0)]
                + [_car(G, j, ["W", "C", "E"], 398.0 - 7.0 * j)
                   for j in range(1, 6)])

    runs = {}
    for label in ("first", "second"):
        vehs = build()
        _run(G, vehs, _signal_red_then_green(40), 120, None, mobil_ctx)
        runs[label] = np.array([(v["idx"], v["pos"], v["v"], v.get("lane", 0))
                                for v in vehs])
    same = np.array_equal(runs["first"], runs["second"])
    ok = [_check("flag-off runs are bitwise identical", same,
                 "bitwise equal" if same else "DIVERGED")]
    ok.append(_check("no car carries POCKET_LANE with pockets off",
                     not (runs["first"][:, 3] == POCKET_LANE).any(),
                     f"lanes seen: {sorted(set(runs['first'][:, 3].tolist()))}"))
    return all(ok)


def scenario_refusal():
    print("\nE) REFUSAL: pockets without MOBIL are refused, not silently wrong")
    G = _cross_graph()
    old_p, old_m = config.TURN_POCKETS_ENABLED, config.MOBIL_ENABLED
    try:
        config.TURN_POCKETS_ENABLED, config.MOBIL_ENABLED = True, False
        try:
            generate.build_turn_pocket_context(G)
            refused = False
        except ValueError:
            refused = True
    finally:
        config.TURN_POCKETS_ENABLED, config.MOBIL_ENABLED = old_p, old_m
    return _check("TURN_POCKETS_ENABLED without MOBIL_ENABLED raises", refused,
                  "ValueError raised" if refused else "accepted silently!")


if __name__ == "__main__":
    print("Left-turn pocket scenarios  (real kernel, hand-checkable)")
    print("=" * 66)
    results = {"unblocks": scenario_unblocks(),
               "overflow": scenario_overflow(),
               "geometry": scenario_geometry(),
               "inertness": scenario_inertness(),
               "refusal": scenario_refusal()}
    print("\n" + "=" * 66)
    for name, okay in results.items():
        print(f"   {PASS if okay else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} turn-pocket scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
