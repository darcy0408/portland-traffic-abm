"""Hand-checkable scenarios for green-wave signal coordination (Phase 4,
increment 2b).

src/webster_network_scenarios.py gates per-node Webster timing (2a). This gates
the coordination layer on top of it: a chain of signals on one named street
sharing a common cycle and travel-time offsets, so a platoon released at the
first signal's green rides successive greens down the corridor. Built as a
synthetic arterial -- three signalized intersections (I1, I2, I3) joined by
several-hundred-metre edges along "SE Powell Blvd" (deliberately mixed-case
and, at one edge, a LIST 'name' tag, to exercise the case-insensitive /
list-handling of the street match), plus one ordinary, unrelated signalized
4-way ("Foster Rd") that must never be touched by coordination. The corridor
also JOGS 90 degrees between I2 and I3 -- I1 and I2 see the chain street as an
east-west (phase 0) movement, I3 sees it as north-south (phase 1) -- so the
per-node phase lookup is exercised for real, not assumed constant.

Three checks, all through the REAL kernel (prepare_signals + apply_greenwave +
step_vehicles + is_green):

  A) PROGRESSION. A platoon released exactly at I1's green, riding the
     coordinated wave, crosses I1, I2 and I3 with zero stops. The SAME platoon
     under deliberately adversarial (not just "off") offsets at I2 and I3 --
     each one placed at the exact midpoint of that node's OWN red window, so
     the miss is guaranteed rather than a matter of random-offset luck --
     stops at both.

  B) INERTNESS. WEBSTER_GREENWAVE_ENABLED=False reproduces 2a's plan bitwise
     (cycles, splits, offsets all identical, chain nodes included). Greenwave
     ON with a street name matching NOTHING (no edge contains it) is equally
     inert -- a clear warning is printed and nothing in the plan changes. A
     street name matching exactly ONE signalized node ("Foster Rd", which the
     Webster/Foster intersection alone carries) is likewise inert -- one node
     is not a chain. And, so the inertness checks are not vacuous, greenwave ON
     with the real "Powell" chain DOES change the plan (cycle and offsets
     diverge from 2a) -- this is the "gate can fail" proof.

  C) STRUCTURE. Direct assertions on the plan itself: the three member nodes
     share one common cycle equal to the MAX of their own (independently
     recomputed) Webster cycles; each member's green SPLIT is exactly its own
     pre-coordination Webster split; the non-member ("Foster") node's cycle,
     split and offset are untouched; and each member's offset equals the
     cumulative free-flow travel time at the progression speed, verified
     against an INDEPENDENTLY written formula in this file (not by calling
     generate.apply_greenwave's own arithmetic back at itself).

Run: python src/greenwave_scenarios.py
"""
import os
import sys
import random
from collections import defaultdict

import networkx as nx

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import emissions
import generate
from generate import (step_vehicles, prepare_signals, is_green,
                       build_webster_plans, find_signal_chain, apply_greenwave,
                       _approach_phase, _chain_phase_at_node, _chain_travel_time_s)
import webster

KPH = 1.0 / 3.6
PASS, FAIL = "PASS", "FAIL"
STOP_EPS_MPS = 0.5   # speed below this counts as "stopped", not just slowed


def _check(label, ok, detail):
    print(f"   [{PASS if ok else FAIL}] {label}: {detail}")
    return bool(ok)


# --- the synthetic corridor --------------------------------------------------
# W0 -> I1 -> I2 -> I3 -> E3 is "SE Powell Blvd" (mixed case, one edge tagged
# with a list of names). I1 and I2 sit on a straight east-west run; the
# corridor then turns 90 degrees, so I2->I3 (and I3->E3) run north-south --
# I3's own chain movement is therefore phase 1 (NS) while I1 and I2's is phase
# 0 (EW). A second, unrelated signalized 4-way ("Foster Rd" x "SE 82nd Ave")
# sits far away and must never be touched by coordination.
W0, I1, I2, I3, E3 = 1, 2, 3, 4, 5
FW, FC, FE, FS, FN = 10, 11, 12, 13, 14

CHAIN_STREET = "Powell"
FLOWS = {(W0, I1, 0): 500.0, (I1, I2, 0): 1200.0, (I2, I3, 0): 300.0,
         (FW, FC, 0): 600.0}


def _corridor_graph():
    G = nx.MultiDiGraph()
    G.add_node(W0, x=-1.0, y=0.0)
    G.add_node(I1, x=0.0, y=0.0, highway="traffic_signals")
    G.add_node(I2, x=1.0, y=0.0, highway="traffic_signals")
    G.add_node(I3, x=1.0, y=1.0, highway="traffic_signals")   # the jog: north of I2
    G.add_node(E3, x=1.0, y=2.0)
    G.add_edge(W0, I1, key=0, length=200.0, name="SE Powell Blvd")
    G.add_edge(I1, I2, key=0, length=400.0, name="SE POWELL BLVD")
    G.add_edge(I2, I3, key=0, length=350.0, name=["SE Powell Blvd", "US 26"])
    G.add_edge(I3, E3, key=0, length=5000.0, name="se powell blvd")

    # An ordinary, unrelated signalized 4-way, far from the corridor and never
    # named "Powell" -- this must be invisible to every greenwave check.
    G.add_node(FW, x=-11.0, y=10.0)
    G.add_node(FC, x=-10.0, y=10.0, highway="traffic_signals")
    G.add_node(FE, x=-9.0, y=10.0)
    G.add_node(FS, x=-10.0, y=9.0)
    G.add_node(FN, x=-10.0, y=11.0)
    G.add_edge(FW, FC, key=0, length=200.0, name="Foster Rd")
    G.add_edge(FC, FE, key=0, length=200.0, name="Foster Rd")
    G.add_edge(FS, FC, key=0, length=200.0, name="SE 82nd Ave")
    G.add_edge(FC, FN, key=0, length=200.0, name="SE 82nd Ave")
    return G


def _signal_nodes_and_phase(G):
    signal_nodes = {n for n, d in G.nodes(data=True)
                    if "traffic_signals" in str(d.get("highway", ""))}
    edge_phase = {(u, v, k): _approach_phase(G, u, v) for u, v, k in G.edges(keys=True)}
    return signal_nodes, edge_phase


def _base_plan(G, signal_nodes, edge_phase):
    """The three members' + Foster's OWN Webster (cycle, split), independent of
    any coordination -- the "before" state every structure/inertness check
    compares against."""
    return build_webster_plans(G, signal_nodes, edge_phase, FLOWS)


def _greenwave_signals(G, signal_nodes, edge_phase, street=CHAIN_STREET, pin_release_at_zero=True):
    """prepare_signals on the full WEBSTER_ENABLED + WEBSTER_GREENWAVE_ENABLED
    path (the real integration, not a hand-assembled dict), with the flags and
    street name set for just this call. If a chain is found and
    pin_release_at_zero, every member's offset is shifted by the SAME constant
    (mod its own new cycle) so member 0 releases exactly at t=0 -- a linear
    shift preserves the coordination (see apply_greenwave's docstring: offset_i
    is affine in offset_0), so this only makes the schedule hand-predictable,
    it does not change what is being tested."""
    saved = (config.WEBSTER_ENABLED, config.WEBSTER_GREENWAVE_ENABLED,
             config.WEBSTER_GREENWAVE_STREET)
    config.WEBSTER_ENABLED = True
    config.WEBSTER_GREENWAVE_ENABLED = True
    config.WEBSTER_GREENWAVE_STREET = street
    try:
        sig = prepare_signals(G, flows=FLOWS)
    finally:
        (config.WEBSTER_ENABLED, config.WEBSTER_GREENWAVE_ENABLED,
         config.WEBSTER_GREENWAVE_STREET) = saved
    chain = sig["greenwave_chain"]
    if chain and pin_release_at_zero:
        delta = -sig["offset"][chain[0]]
        for n in chain:
            sig["offset"][n] = (sig["offset"][n] + delta) % sig["node_cycle"][n]
    return sig


def _2a_signals(G):
    """prepare_signals on the plain 2a path (Webster on, greenwave off)."""
    saved = (config.WEBSTER_ENABLED, config.WEBSTER_GREENWAVE_ENABLED)
    config.WEBSTER_ENABLED = True
    config.WEBSTER_GREENWAVE_ENABLED = False
    try:
        sig = prepare_signals(G, flows=FLOWS)
    finally:
        config.WEBSTER_ENABLED, config.WEBSTER_GREENWAVE_ENABLED = saved
    return sig


def _platoon(u, v, exit_v, n, v0):
    """n cars queued from rest on u->v, nose at the line, 7 m apart, routed onto
    the full corridor (through I1, I2, I3 and out the long exit edge), so
    nobody finishes and respawns during the window. Mirrors the 2a gate's
    `_platoon` helper exactly."""
    route = [(u, v, 0, 200.0, v0), (I1, I2, 0, 400.0, v0),
             (I2, I3, 0, 350.0, v0), (I3, exit_v, 0, 5000.0, v0)]
    return [{"id": f"plt{j}", "route": route, "idx": 0,
             "pos": 198.0 - 7.0 * j, "v": 0.0} for j in range(n)]


def _run_and_track(vehs, signals, n_steps, watch_edges):
    """Step the real kernel; record, per vehicle and per watched (u, v, k) edge,
    the MINIMUM speed it had while its route pointer sat on that edge. A
    genuine stop at a red pins a car's speed near zero for many consecutive
    steps -- ordinary car-following speed dips from spacing never do, so a low
    STOP_EPS_MPS threshold on the minimum cleanly separates the two."""
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox, seg_thru = (defaultdict(float), defaultdict(float),
                                  defaultdict(float))
    min_v = {veh["id"]: {e: float("inf") for e in watch_edges} for veh in vehs}
    for s in range(n_steps):
        step_vehicles(vehs, config.DT, s * config.DT, seg_tot, seg_nox, seg_thru,
                      coeffs, None, [], random.Random(0), signals, None, None)
        for veh in vehs:
            key = veh["route"][veh["idx"]][:3]
            if key in watch_edges:
                d = min_v[veh["id"]]
                if veh["v"] < d[key]:
                    d[key] = veh["v"]
    return min_v


def _count_stops(min_v, watch_edges):
    """Total (vehicle, edge) pairs where the vehicle's speed on that edge ever
    fell below STOP_EPS_MPS -- i.e. how many times, across the whole platoon,
    someone had to stop at one of the watched signals."""
    return sum(1 for d in min_v.values() for e in watch_edges if d[e] < STOP_EPS_MPS)


# --- A) progression: the wave vs a guaranteed miss --------------------------

def _adversarial_offsets(G, signal_nodes, edge_phase, base_2a):
    """Deliberately adversarial 2a-style offsets for I2 and I3: I1 is pinned to
    release at t=0 exactly as in the coordinated run (so the comparison isolates
    the offset choice, not the release time), and each of I2/I3 is placed at
    the exact MIDPOINT of its own opposing (red) phase window on ITS OWN
    (independent, uncoordinated) cycle -- guaranteed red on arrival, not a
    matter of the random 2a draw's luck. This is the "anti-phased" control the
    brief calls for, made deterministic."""
    matched = generate._matched_edges(G, CHAIN_STREET)
    phase = {n: _chain_phase_at_node(n, edge_phase, matched) for n in (I1, I2, I3)}
    prog_mps = config.WEBSTER_PROGRESSION_SPEED_KPH / 3.6

    sig = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base_2a.items()}
    sig["offset"][I1] = 0.0
    for n in (I2, I3):
        cycle_n = sig["node_cycle"][n]
        split_n = sig["node_split"][n]
        t_arrival = _chain_travel_time_s(G, I1, n, prog_mps)   # I1 releases at t=0
        # midpoint of the OPPOSING phase's window: guaranteed red for this node's
        # own chain movement, well clear of any clearance-interval edge case.
        if phase[n] == 0:
            red_mid = cycle_n * (split_n + 1.0) / 2.0
        else:
            red_mid = split_n * cycle_n / 2.0
        sig["offset"][n] = (red_mid - t_arrival) % cycle_n
    return sig


def scenario_progression():
    print("\nA) PROGRESSION: coordinated wave vs a deliberately anti-phased miss")
    G = _corridor_graph()
    signal_nodes, edge_phase = _signal_nodes_and_phase(G)
    v0 = config.WEBSTER_PROGRESSION_SPEED_KPH * KPH
    n_cars, T = 5, 400

    gw = _greenwave_signals(G, signal_nodes, edge_phase)
    chain = gw["greenwave_chain"]
    print(f"   chain found: {chain} (expect [{I1}, {I2}, {I3}]); common cycle "
          f"{gw['node_cycle'][I1]:.1f}s for every member")

    # Watch the two edges the wave actually has to carry the platoon through
    # (into I2 and into I3). W0->I1 is deliberately excluded: the platoon
    # STARTS at rest there by construction (queued, released at I1's green),
    # so its min speed on that edge is trivially 0.0 regardless of coordination
    # and is not a "stop" in the sense this gate measures.
    watch = [(I1, I2, 0), (I2, I3, 0)]

    platoon_wave = _platoon(W0, I1, E3, n_cars, v0)
    min_v_wave = _run_and_track(platoon_wave, gw, T, watch)
    stops_wave = _count_stops(min_v_wave, watch)
    print(f"   coordinated: min speed per approach (m/s) -> "
          f"{ {e: round(min(d[e] for d in min_v_wave.values()), 2) for e in watch} }")
    print(f"   coordinated: {stops_wave} stop(s) across {n_cars} cars x {len(watch)} signals")

    base_2a = _2a_signals(G)
    adv = _adversarial_offsets(G, signal_nodes, edge_phase, base_2a)
    platoon_adv = _platoon(W0, I1, E3, n_cars, v0)
    min_v_adv = _run_and_track(platoon_adv, adv, T, watch)
    stops_adv = _count_stops(min_v_adv, watch)
    print(f"   anti-phased: min speed per approach (m/s) -> "
          f"{ {e: round(min(d[e] for d in min_v_adv.values()), 2) for e in watch} }")
    print(f"   anti-phased: {stops_adv} stop(s) across {n_cars} cars x {len(watch)} signals")

    ok = [
        _check("chain found in corridor order", chain == [I1, I2, I3], f"{chain}"),
        _check("coordinated platoon rides the wave: zero stops",
               stops_wave == 0, f"{stops_wave} stops"),
        _check("anti-phased platoon is stopped at >=1 downstream signal",
               stops_adv >= 1, f"{stops_adv} stops"),
    ]
    return all(ok)


# --- B) inertness ------------------------------------------------------------

def _reference_2a_plan(G, signal_nodes, edge_phase):
    """Independently reconstruct the flag-off (2a) plan by calling the same
    lower-level pieces prepare_signals itself calls on that path -- build_webster_
    plans, then the SAME seeded off_rng draw -- WITHOUT going through
    prepare_signals or apply_greenwave at all. This is the thing "greenwave off"
    is supposed to reproduce bitwise; comparing prepare_signals's own flag-off
    output against this catches any accidental change to the 2a path, not just
    a self-comparison of prepare_signals against itself."""
    node_cycle, node_split = build_webster_plans(G, signal_nodes, edge_phase, FLOWS)
    off_rng = random.Random(config.RANDOM_SEED + 1)
    offset = {n: off_rng.uniform(0.0, node_cycle[n]) for n in signal_nodes}
    return {"node_cycle": node_cycle, "node_split": node_split, "offset": offset}


def scenario_inertness():
    print("\nB) INERTNESS: off, and a street matching nothing / one node, change nothing")
    G = _corridor_graph()
    signal_nodes, edge_phase = _signal_nodes_and_phase(G)

    reference = _reference_2a_plan(G, signal_nodes, edge_phase)   # independent, no generate.* plan code
    base_2a = _2a_signals(G)          # greenwave OFF, through the real prepare_signals
    gw_nothing = _greenwave_signals(G, signal_nodes, edge_phase,
                                    street="Nonexistent Blvd", pin_release_at_zero=False)
    gw_one_node = _greenwave_signals(G, signal_nodes, edge_phase,
                                     street="Foster", pin_release_at_zero=False)
    gw_on = _greenwave_signals(G, signal_nodes, edge_phase, pin_release_at_zero=False)

    def _plan_equal(a, b, nodes):
        for n in nodes:
            if a["node_cycle"][n] != b["node_cycle"][n]:
                return False
            if a["node_split"][n] != b["node_split"][n]:
                return False
            if a["offset"][n] != b["offset"][n]:
                return False
        return True

    all_nodes = signal_nodes
    off_matches = _plan_equal(reference, base_2a, all_nodes)
    nothing_matches = _plan_equal(base_2a, gw_nothing, all_nodes)
    one_node_matches = _plan_equal(base_2a, gw_one_node, all_nodes)
    on_diverges = not _plan_equal(base_2a, gw_on, {I1, I2, I3})
    foster_untouched_when_on = _plan_equal(base_2a, gw_on, {FC})

    print(f"   greenwave OFF vs the independently reconstructed 2a plan: "
          f"{'identical' if off_matches else 'DIFFERENT'}")
    print(f"   greenwave ON, street matching nothing: chain={gw_nothing['greenwave_chain']}, "
          f"plan {'identical' if nothing_matches else 'DIFFERENT'} to 2a")
    print(f"   greenwave ON, street matching one node ('Foster'): "
          f"chain={gw_one_node['greenwave_chain']}, plan "
          f"{'identical' if one_node_matches else 'DIFFERENT'} to 2a")
    print(f"   greenwave ON, real Powell chain: member plan "
          f"{'DIFFERENT from 2a (expected)' if on_diverges else 'identical to 2a (!)'}; "
          f"non-member Foster plan {'untouched' if foster_untouched_when_on else 'CHANGED (!)'}")

    ok = [
        _check("flag off == independently reconstructed 2a plan, bitwise",
               off_matches, "identical" if off_matches else "diverged"),
        _check("street matching nothing == 2a, bitwise (chain empty, warned)",
               nothing_matches and gw_nothing["greenwave_chain"] == [],
               f"chain={gw_nothing['greenwave_chain']}"),
        _check("street matching exactly one signal == 2a, bitwise (chain empty)",
               one_node_matches and gw_one_node["greenwave_chain"] == [],
               f"chain={gw_one_node['greenwave_chain']}"),
        _check("...but the REAL Powell chain does change the member plan (gate can fail)",
               on_diverges, "diverged from 2a" if on_diverges else "no change (!)"),
        _check("...and leaves the unrelated Foster signal untouched",
               foster_untouched_when_on, "untouched" if foster_untouched_when_on else "CHANGED"),
    ]
    return all(ok)


# --- C) structure -------------------------------------------------------------

def scenario_structure():
    print("\nC) STRUCTURE: common cycle, preserved splits, untouched non-members, offsets")
    G = _corridor_graph()
    signal_nodes, edge_phase = _signal_nodes_and_phase(G)

    own_cycle, own_split = _base_plan(G, signal_nodes, edge_phase)
    gw = _greenwave_signals(G, signal_nodes, edge_phase, pin_release_at_zero=False)
    chain = gw["greenwave_chain"]

    expected_common = max(own_cycle[n] for n in (I1, I2, I3))
    common_ok = all(gw["node_cycle"][n] == expected_common for n in (I1, I2, I3))
    print(f"   own cycles: I1={own_cycle[I1]:.3f} I2={own_cycle[I2]:.3f} "
          f"I3={own_cycle[I3]:.3f} -> expected common {expected_common:.3f}; "
          f"coordinated cycles {[gw['node_cycle'][n] for n in (I1, I2, I3)]}")

    split_ok = all(gw["node_split"][n] == own_split[n] for n in (I1, I2, I3))
    print(f"   own splits preserved: {[gw['node_split'][n] for n in (I1, I2, I3)]} "
          f"== {[own_split[n] for n in (I1, I2, I3)]}")

    foster_ok = (gw["node_cycle"][FC] == own_cycle[FC]
                 and gw["node_split"][FC] == own_split[FC])
    print(f"   Foster (non-member) cycle/split unchanged: "
          f"{gw['node_cycle'][FC]:.3f}s / {gw['node_split'][FC]:.4f}")

    # Independently hand-derived expected offsets: member i's offset should put
    # its window START at (member 0's window-start time) + (cumulative travel
    # time to i at the progression speed). Written out here from scratch, NOT
    # by calling generate.apply_greenwave's formula back at itself.
    matched = generate._matched_edges(G, CHAIN_STREET)
    phase = {n: _chain_phase_at_node(n, edge_phase, matched) for n in (I1, I2, I3)}
    prog_mps = config.WEBSTER_PROGRESSION_SPEED_KPH / 3.6
    C = expected_common
    g = {n: (0.0 if phase[n] == 0 else own_split[n] * C) for n in (I1, I2, I3)}
    offset0 = gw["offset"][I1]
    expected_offset = {I1: offset0}
    for n in (I2, I3):
        cum_travel = _chain_travel_time_s(G, I1, n, prog_mps)
        expected_offset[n] = (offset0 + (g[n] - g[I1]) - cum_travel) % C

    offsets_ok = all(abs(gw["offset"][n] - expected_offset[n]) < 1e-9 for n in (I1, I2, I3))
    print(f"   chain phase per node: I1={phase[I1]} I2={phase[I2]} I3={phase[I3]} "
          f"(expect 0, 0, 1 -- the jog flips I3 to NS)")
    print(f"   expected offsets {[round(expected_offset[n], 6) for n in (I1, I2, I3)]} "
          f"vs actual {[round(gw['offset'][n], 6) for n in (I1, I2, I3)]}")

    ok = [
        _check("chain ordered correctly", chain == [I1, I2, I3], f"{chain}"),
        _check("phase read per node, not assumed constant (I3 differs from I1/I2)",
               phase == {I1: 0, I2: 0, I3: 1}, f"{phase}"),
        _check("common cycle == max of members' own Webster cycles",
               common_ok, f"expected {expected_common:.3f}, got "
               f"{[gw['node_cycle'][n] for n in (I1, I2, I3)]}"),
        _check("each member's green split preserved exactly",
               split_ok, "preserved" if split_ok else "changed"),
        _check("non-member (Foster) cycle/split untouched",
               foster_ok, "untouched" if foster_ok else "CHANGED"),
        _check("offsets equal the independently hand-derived travel-time formula",
               offsets_ok, "match to 1e-9" if offsets_ok else "MISMATCH"),
    ]
    return all(ok)


if __name__ == "__main__":
    print("Green-wave scenarios  (real kernel, hand-checkable)")
    print("=" * 70)
    results = {"progression": scenario_progression(),
               "inertness": scenario_inertness(),
               "structure": scenario_structure()}
    print("\n" + "=" * 70)
    for name, okay in results.items():
        print(f"   {PASS if okay else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} green-wave scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
