"""Hand-checkable scenarios for Webster signal timing wired into the network
(Phase 4, increment 2).

src/webster_scenarios.py gates the DECISION in isolation (given approach flows,
what cycle and split does Webster return?). This gates that decision INSIDE the
real kernel: per-node cycle/split from measured flows, the yellow+all-red
clearance interval, and the actual queueing/discharge at a signalized node in
generate.step_vehicles. Three checks, all through a single synthetic four-way
intersection C (EW approach W->C, NS approach S->C, exits C->E and C->N), built
as a real graph so prepare_signals + webster + is_green run end to end:

  A) ASYMMETRIC DEMAND -> HEAVY APPROACH GETS MORE GREEN (through the real
     kernel). With a heavy EW flow and a light NS flow, Webster gives EW a green
     split > 0.5, and two equal saturated platoons then discharge UNEVENLY: more
     EW cars clear C than NS cars. The control is the same two platoons under the
     uniform 50/50 base signal, where by symmetry they clear EQUALLY -- so the
     imbalance is Webster's timing, not the geometry.

  B) INERTNESS. With WEBSTER off the signal takes the byte-for-byte original
     uniform code path: is_green's flag-off branch equals the exact original
     ((t+offset)%cycle)/cycle < split formula across a time sweep, and a queue
     through a cycle is deterministic. The same node under a Webster plan gives a
     DIFFERENT trajectory (so the machinery is live and the gate can fail). The
     pinned kernel_regression covers the full bitwise proof of the base kernel.

  C) CLEARANCE. During the yellow+all-red at the end of each phase, is_green
     returns False for BOTH phases (nobody has green), while the active phase is
     green at its start; and in the real kernel a saturated approach discharges
     STRICTLY FEWER cars with the clearance interval than without it -- the lost
     green is real, not just a display flag.

Run: python src/webster_network_scenarios.py
"""
import copy
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
from generate import step_vehicles, prepare_signals, is_green

KPH = 1.0 / 3.6
PASS, FAIL = "PASS", "FAIL"

# The synthetic intersection's nodes. Coordinates are chosen so that _approach_phase
# reads W->C and C->E as east-west (phase 0) and S->C and C->N as north-south
# (phase 1); C is the signalized node.
W, C, E, S, N = 1, 2, 3, 4, 5


def _check(label, ok, detail):
    print(f"   [{PASS if ok else FAIL}] {label}: {detail}")
    return bool(ok)


def _intersection_graph():
    """A four-way intersection C with an EW approach (W->C, exit C->E) and an NS
    approach (S->C, exit C->N). C is tagged signalized so prepare_signals picks it
    up. Every edge defaults to one lane. Node coordinates set each approach's phase
    via the same bearing rule the real network uses."""
    G = nx.MultiDiGraph()
    G.add_node(W, x=-1.0, y=0.0)
    G.add_node(E, x=1.0, y=0.0)
    G.add_node(S, x=0.0, y=-1.0)
    G.add_node(N, x=0.0, y=1.0)
    G.add_node(C, x=0.0, y=0.0, highway="traffic_signals")
    for u, v in ((W, C), (C, E), (S, C), (C, N)):
        G.add_edge(u, v, key=0, length=200.0, oneway=True)
    return G


def _webster_signals(G, flows, offset_C=0.0):
    """prepare_signals on the Webster path (flag forced on for this call only),
    with C's offset pinned so the phase alignment is hand-predictable."""
    saved = config.WEBSTER_ENABLED
    config.WEBSTER_ENABLED = True
    try:
        sig = prepare_signals(G, flows=flows)
    finally:
        config.WEBSTER_ENABLED = saved
    sig["offset"][C] = offset_C
    return sig


def _base_signals(G, offset_C=0.0):
    """prepare_signals on the uniform base path (flag off): node_cycle stays None."""
    sig = prepare_signals(G)              # WEBSTER_ENABLED is False by default here
    sig["offset"][C] = offset_C
    return sig


def _run(vehs, signals, n_steps):
    """Step the real kernel with no respawn (long exit edges keep every car on its
    route), so the G/nodes/rng arguments are dummies, as in the other gates."""
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox, seg_thru = (defaultdict(float), defaultdict(float),
                                  defaultdict(float))
    for s in range(n_steps):
        step_vehicles(vehs, config.DT, s * config.DT, seg_tot, seg_nox, seg_thru,
                      coeffs, None, [], random.Random(0), signals, None, None)


def _platoon(u, v, exit_v, n, v0):
    """n cars queued from rest on the approach u->v (200 m), nose near the stop
    line and 7 m apart, each routed onto a long exit edge v->exit_v so nobody
    finishes and triggers a respawn during the window."""
    approach = (u, v, 0, 200.0, v0)
    exit_edge = (v, exit_v, 0, 5000.0, v0)
    return [{"id": f"{u}{v}_{j}", "route": [approach, exit_edge], "idx": 0,
             "pos": 198.0 - 7.0 * j, "v": 0.0} for j in range(n)]


def _crossed(vehs):
    """How many cars have cleared C (advanced onto their exit edge)."""
    return sum(1 for v in vehs if v["idx"] >= 1)


# --- A) asymmetric demand: heavy approach gets more green -------------------

def scenario_asymmetry():
    print("\nA) ASYMMETRIC DEMAND -> HEAVY APPROACH GETS MORE GREEN (real kernel)")
    G = _intersection_graph()
    v0 = 50 * KPH
    q_ew, q_ns = 1000.0, 150.0
    flows = {(W, C, 0): q_ew, (S, C, 0): q_ns}
    web = _webster_signals(G, flows)
    split = web["node_split"][C]
    cycle = web["node_cycle"][C]
    print(f"   EW flow {q_ew:.0f} veh/h vs NS flow {q_ns:.0f} veh/h -> Webster cycle "
          f"{cycle:.1f}s, EW split {split:.3f} (EW should get > half the cycle).")

    n, T = 16, 150
    ew = _platoon(W, C, E, n, v0)
    ns = _platoon(S, C, N, n, v0)
    _run(ew + ns, web, T)
    ew_web, ns_web = _crossed(ew), _crossed(ns)
    print(f"   Webster, {T}s: {ew_web} EW cars clear C vs {ns_web} NS cars.")

    # Control: the SAME two equal platoons under the uniform 50/50 base signal.
    base = _base_signals(G)
    ewb = _platoon(W, C, E, n, v0)
    nsb = _platoon(S, C, N, n, v0)
    _run(ewb + nsb, base, T)
    ew_uni, ns_uni = _crossed(ewb), _crossed(nsb)
    print(f"   Uniform 50/50, {T}s: {ew_uni} EW cars vs {ns_uni} NS cars "
          f"(symmetry control).")

    ok = [
        _check("Webster favors the heavy EW approach (split > 0.5)", split > 0.5,
               f"split_ew = {split:.4f}"),
        _check("Webster: more EW cars clear C than NS cars", ew_web > ns_web,
               f"{ew_web} EW vs {ns_web} NS"),
        _check("uniform control clears EW and NS about equally", abs(ew_uni - ns_uni) <= 1,
               f"{ew_uni} EW vs {ns_uni} NS (|diff| <= 1)"),
        _check("the imbalance is Webster's doing (its EW lead exceeds uniform's)",
               (ew_web - ns_web) > (ew_uni - ns_uni),
               f"Webster lead {ew_web - ns_web} vs uniform lead {ew_uni - ns_uni}"),
    ]
    return all(ok)


# --- B) inertness -----------------------------------------------------------

def scenario_inertness():
    print("\nB) INERTNESS: flag off == the original uniform signal, byte-for-byte")
    G = _intersection_graph()
    base = _base_signals(G, offset_C=17.3)   # arbitrary offset, exercised in the sweep

    # 1) is_green's flag-off branch must equal the EXACT original arithmetic. We
    #    recompute that formula here, independently, over a fine time sweep across
    #    several cycles and both phases, and demand bitwise agreement.
    mismatches = 0
    for i in range(0, 4000):
        t = i * 0.05
        frac = ((t + base["offset"][C]) % base["cycle"]) / base["cycle"]
        for phase in (0, 1):
            expected = phase == (0 if frac < base["green_split"] else 1)
            if is_green(base, C, phase, t) != expected:
                mismatches += 1
    print(f"   is_green flag-off branch vs the original formula over 8000 samples: "
          f"{mismatches} mismatches.")

    # 2) A signalized queue through a full cycle is deterministic on the base path,
    #    and DIFFERENT under a Webster plan (so this check can fail). We queue on
    #    the NS approach, which the heavy-EW Webster plan STARVES (a short NS green
    #    each cycle) relative to the uniform 50/50 base -- the same cars clear at a
    #    visibly different rate, so the two trajectories cannot coincide.
    v0 = 50 * KPH
    q1 = _platoon(S, C, N, 10, v0)
    _run(q1, _base_signals(G), 90)
    q2 = _platoon(S, C, N, 10, v0)
    _run(q2, _base_signals(G), 90)
    base_a = [(v["idx"], round(v["pos"], 9), round(v["v"], 9)) for v in q1]
    base_b = [(v["idx"], round(v["pos"], 9), round(v["v"], 9)) for v in q2]

    web = _webster_signals(G, {(W, C, 0): 1000.0, (S, C, 0): 150.0})
    q3 = _platoon(S, C, N, 10, v0)
    _run(q3, web, 90)
    web_traj = [(v["idx"], round(v["pos"], 9), round(v["v"], 9)) for v in q3]

    ok = [
        _check("is_green flag-off branch is the original formula, bitwise",
               mismatches == 0, f"{mismatches} mismatches over 8000 samples"),
        _check("base signal is deterministic (same queue -> same trajectory)",
               base_a == base_b, "two runs identical" if base_a == base_b
               else "runs differ"),
        _check("...but a Webster plan changes the trajectory (gate can fail)",
               web_traj != base_a,
               "Webster differs from base" if web_traj != base_a
               else "Webster identical to base (!)"),
    ]
    return all(ok)


# --- C) clearance -----------------------------------------------------------

def scenario_clearance():
    print("\nC) CLEARANCE: yellow+all-red is red for BOTH phases, and it costs")
    print("   real green in the kernel")
    G = _intersection_graph()
    # Symmetric flow -> split exactly 0.5 and (with these constants) the cycle
    # clamps to WEBSTER_CYCLE_MIN_S = 30 s. EW owns [0,15), NS owns [15,30).
    web = _webster_signals(G, {(W, C, 0): 400.0, (S, C, 0): 400.0})
    cycle = web["node_cycle"][C]
    split = web["node_split"][C]
    clr = web["clearance"]
    ew_end = split * cycle
    print(f"   cycle {cycle:.1f}s, split {split:.3f} -> EW green [0,{ew_end:.1f}), "
          f"NS green [{ew_end:.1f},{cycle:.1f}); clearance {clr:.1f}s/phase.")

    # A sample inside the EW clearance (just before EW's window ends) and inside the
    # NS clearance (just before the cycle ends): both phases must read red.
    t_ew_clear = ew_end - clr / 2.0     # e.g. 12.5 s, inside [10,15)
    t_ns_clear = cycle - clr / 2.0      # e.g. 27.5 s, inside [25,30)
    green_state = {
        "EW start t=0": (is_green(web, C, 0, 0.0), is_green(web, C, 1, 0.0)),
        f"EW clearance t={t_ew_clear:.1f}":
            (is_green(web, C, 0, t_ew_clear), is_green(web, C, 1, t_ew_clear)),
        f"NS start t={ew_end:.1f}":
            (is_green(web, C, 0, ew_end), is_green(web, C, 1, ew_end)),
        f"NS clearance t={t_ns_clear:.1f}":
            (is_green(web, C, 0, t_ns_clear), is_green(web, C, 1, t_ns_clear)),
    }
    for label, (g0, g1) in green_state.items():
        print(f"     {label}: EW green={g0}, NS green={g1}")

    # Kernel effect: the SAME saturated EW platoon and Webster plan, run once with
    # the clearance interval and once with it zeroed, must clear FEWER cars with
    # clearance (the lost green is real, not a cosmetic flag).
    v0 = 50 * KPH
    T = 150
    with_clr = _platoon(W, C, E, 16, v0)
    _run(with_clr, web, T)
    n_with = _crossed(with_clr)

    web_noclr = copy.deepcopy(web)
    web_noclr["clearance"] = 0.0
    no_clr = _platoon(W, C, E, 16, v0)
    _run(no_clr, web_noclr, T)
    n_without = _crossed(no_clr)
    print(f"   EW cars cleared in {T}s: {n_with} with clearance, {n_without} without.")

    ok = [
        _check("EW phase is green at its start", green_state["EW start t=0"] == (True, False),
               f"{green_state['EW start t=0']}"),
        _check("EW clearance: neither phase green",
               green_state[f"EW clearance t={t_ew_clear:.1f}"] == (False, False),
               f"{green_state[f'EW clearance t={t_ew_clear:.1f}']}"),
        _check("NS phase is green at its start",
               green_state[f"NS start t={ew_end:.1f}"] == (False, True),
               f"{green_state[f'NS start t={ew_end:.1f}']}"),
        _check("NS clearance: neither phase green",
               green_state[f"NS clearance t={t_ns_clear:.1f}"] == (False, False),
               f"{green_state[f'NS clearance t={t_ns_clear:.1f}']}"),
        _check("clearance costs real green: fewer cars clear C with it than without",
               n_with < n_without, f"{n_with} with vs {n_without} without"),
    ]
    return all(ok)


if __name__ == "__main__":
    print("Webster network scenarios  (real kernel, hand-checkable)")
    print("=" * 70)
    results = {"asymmetry": scenario_asymmetry(),
               "inertness": scenario_inertness(),
               "clearance": scenario_clearance()}
    print("\n" + "=" * 70)
    for name, okay in results.items():
        print(f"   {PASS if okay else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} Webster network scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
