"""Paired multi-seed Rose Quarter I-5 SB closure campaign (pre-registered).

Models the real ODOT closure (project 19071): I-5 SOUTHBOUND shuts completely
for up to 5 weeks starting Sept 11 2026, between the I-405 and I-84
interchanges, signed detour I-405 SB, regional traffic directed to I-205. The
campaign design, metrics, and verdict rules are frozen in
PREREG_I5_ROSEQUARTER.md BEFORE any task runs; the whole point is a prediction
banked before the real closure produces data, so nothing here is tuned after
results are seen.

Same instrument as the fwms campaign (src/freeway_multiseed.py): for each seed
run the same demand open and closed, difference per seed, and make claims only
about the distribution of paired differences across seeds. 2 arms x 8 block-1
seeds = 16 tasks, one per SLURM array index, each writing its own files;
finished tasks skip on their summary, so resubmission is safe.

    python src/freeway_rosequarter.py --check        # verify the frozen span
    python src/freeway_rosequarter.py --list         # show the task table
    python src/freeway_rosequarter.py --task 7       # run one task
    python src/freeway_rosequarter.py --readout      # analyze saved summaries

The open arm is recomputed under this campaign's prefix rather than reusing
the fwms open summaries, because this campaign tracks I-405 (the signed
detour) and the fwms summaries never recorded it.
"""
import argparse
import json
import os
import random
import sys

import numpy as np
import osmnx as ox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import generate        # noqa: E402
from freeway_runs import SCENARIOS  # noqa: E402  (the verified closure specs)
import metro_calibrated_experiment as mce  # noqa: E402  (the realism stack)

# the project's pinned block-1 seed set (same as every freeway campaign)
SEEDS = (42, 7, 13, 99, 314, 777, 2024, 8)
ARMS = ("open", "rosequarter")
PREFIX = "fwrq"          # base campaign; --realism switches this to "fwrqr"

# The frozen closed span, verified edge-for-edge against the Aug 12 metro-graph
# probe and the Aug 13 dry run: 3 SB mainline edges (1,628 m) plus 2 stranded
# SB ramps, northbound untouched. A task refuses to run if the graph it loads
# selects anything else: a silently different span would invalidate the
# pre-registration, so this fails loudly instead.
EXPECTED_SB = {(40382443, 40397036, 0), (40397036, 40413533, 0),
               (40413533, 3427976322, 0)}
EXPECTED_REMOVED_N = 5

REALISM_FLAGS = dict(mce.ARMS["realism"])
STACK_REALISM = False    # set by --realism in main(), before any dispatch
STACK_NONWORK = False    # set by --nonwork in main(): the demand-variant arm
                         # (prefix fwrqn) registered in prereg Appendix E
STACK_IMPROVED = False   # set by --improved in main(): the PORTAL-validated
                         # stack (realism + corrected real lanes on the
                         # lane-tagged graph), prefix fwrqi, prereg Appendix K
STACK_ACCESS = False     # set by --accesslane in main(): the closure-geometry
                         # arm (prefix fwrqa, prereg Appendix O). Same stack
                         # as fwrqi; only the closed-arm graph surgery differs
                         # (ODOT keeps one local-access lane to Broadway/
                         # Weidler, which the other arms model as fully shut).
STACK_COMPLIANCE = False  # set by --compliance in main(): the signed-detour
                          # compliance arm (prefix fwrqc). The fwrqi stack and
                          # the FULL closure verbatim; the only change is that
                          # each through trip follows ODOT's official I-405
                          # detour with a registered probability instead of
                          # picking its own fastest route (config.DETOUR_*,
                          # generate.build_detour_context). Every other arm
                          # models drivers who all ignore the signage; this
                          # one models the plan.
STACK_REROUTE = False    # set by --reroute in main(): the en-route rerouting
                         # arm (prefix fwrqe, prereg Appendix T). The fwrqi
                         # stack and the FULL closure verbatim; the only
                         # mechanism change is config.REROUTE_ENABLED on the
                         # "on" cells. DISCLOSED: the C1 mechanism FAILED its
                         # registered acceptance gate (ledger RR35.1, Burnside
                         # 1.88x vs the 2x bar, replicated in the combined
                         # arm), so this arm is exploratory, never the citable
                         # model, and every fwrqe citation carries that
                         # disclosure. Four cells (off/on x open/closed): the
                         # OFF pair reruns fwrqi with measurement-only stuck
                         # instrumentation and must reproduce the banked fwrqi
                         # summaries EXACTLY (registered identity check),
                         # because the fwrq/fwrqi campaigns never saved the
                         # stuck_sum column the mechanism's headline metric
                         # (stuck vehicle-hours) needs.

# The registered compliance levels. The share has no data behind it, so three
# a-priori levels bracket it rather than one guess carrying the arm; the open
# arm is share-independent (compliance touches only closed-arm routing), so
# ONE shared set of open tasks serves all three levels. 8 + 3 x 8 = 32 tasks.
COMPLIANCE_SHARES = (0.25, 0.50, 0.75)

# The access-lane partial closure, frozen (Appendix O). ODOT's announced plan
# keeps ONE southbound lane open from the I-405 junction to the Broadway/
# Weidler exit (302A) for local access; everything south of 302A closes. On
# this graph that is: keep the first mainline edge clamped to 1 lane, keep the
# 302A off-ramp, and remove the other 3 of the full closure's 5 edges. After
# the removal, node 40397036 (exit 302A) has the off-ramp as its ONLY outgoing
# edge, so through traffic is structurally forced off at Broadway/Weidler,
# which is what ODOT's signage does. The kept edge's tagged maxspeed is NOT
# changed: the arm models the capacity cut only, not a work-zone speed limit.
ACCESS_KEEP_MAINLINE = (40382443, 40397036, 0)   # I-405 jct -> exit 302A
ACCESS_KEEP_RAMP = (40397036, 1343610044, 0)     # the 302A off-ramp itself
ACCESS_ORIG_LANES = "4"    # what the lane-tagged graph must say before the
                           # clamp; anything else means a different graph and
                           # the task refuses to run (same spirit as the span
                           # guard: fail loudly, never adapt silently)
ACCESS_OPEN_LANES = "1"    # ODOT keeps one lane
ACCESS_EXPECTED_REMOVED_N = 3   # 2 southern mainline edges + 1 stranded ramp

# routes whose per-edge mainline values are stored per run. I 405 is the signed
# detour (the pre-registered "up"); I 205 the regional detour ("up"); I 5 the
# closed route; the rest are the surface alternates, kept identical to fwms so
# the two campaigns' readouts stay comparable.
TRACK_ROUTES = ("I 5", "I 405", "I 205", "OR 213", "OR 99E", "US 26")


def tasks():
    # every entry is (arm, seed, extra); extra is a compliance share (float,
    # fwrqc closed tasks), a rerouting cell ("off"/"on", every fwrqe task),
    # or None. The compliance table is one flat 32-task array (8 open + 8 per
    # level) so the three levels never race to write the same open summary
    # from concurrent SLURM arrays.
    if STACK_COMPLIANCE:
        t = [("open", seed, None) for seed in SEEDS]
        for share in COMPLIANCE_SHARES:
            t += [("rosequarter", seed, share) for seed in SEEDS]
        return t
    if STACK_REROUTE:
        # four cells (prereg Appendix T), one flat 32-task array. The OFF
        # pair runs first (tasks 0-15) so its registered identity check
        # against the banked fwrqi summaries can run as soon as the first
        # half of the array lands.
        t = []
        for cell in ("off", "on"):
            t += [(arm, seed, cell) for arm in ARMS for seed in SEEDS]
        return t
    return [(arm, seed, None) for arm in ARMS for seed in SEEDS]


def run_name(arm, seed, extra=None):
    # `extra` is the task tuple's third slot: a compliance share (float), a
    # rerouting cell ("off"/"on"), or None
    if STACK_REROUTE:
        # the ON pair carries the plain prefix (fwrqe_*); the OFF pair, the
        # instrumented fwrqi reruns, is fwrqeoff_* so the two cells can never
        # collide on filenames
        return f"{PREFIX}{'off' if extra == 'off' else ''}_{arm}_s{seed}"
    if extra is not None:
        # closed compliance task: the level is part of the run identity
        # (fwrqc25 / fwrqc50 / fwrqc75); the shared open arm stays fwrqc_open
        return f"{PREFIX}{int(round(extra * 100)):02d}_{arm}_s{seed}"
    return f"{PREFIX}_{arm}_s{seed}"


def summary_path(arm, seed, extra=None):
    return os.path.join(config.PROCESSED_DIR,
                        f"{run_name(arm, seed, extra)}_summary.json")


def _load_metro_graph():
    # the improved arm runs on the lane-tagged re-download (the graph the
    # 91-station PORTAL validation used), and the access-lane arm reuses it
    # (its lane clamp needs the real lane tags); every other arm keeps the
    # original cache so the earlier registered arms stay exactly reproducible
    name = ("graph_metro20k_lanes.graphml"
            if (STACK_IMPROVED or STACK_ACCESS or STACK_COMPLIANCE
                or STACK_REROUTE)
            else "graph.graphml")
    graph_file = os.path.join(config.NETWORK_DIR, name)
    if not os.path.exists(graph_file):
        raise SystemExit(f"no cached graph at {graph_file}; refusing to "
                         f"download mid-experiment")
    G = ox.load_graphml(graph_file)
    # metro guard: a corridor-sized cache here would silently run the wrong
    # experiment under the right file names
    if G.number_of_edges() < 100_000:
        raise SystemExit(f"graph has {G.number_of_edges():,} edges; this is a "
                         f"metro campaign and refuses a corridor-sized graph")
    return G


def _verify_span(G):
    """The frozen-span guard: the spec must select exactly the pre-registered
    edges on this graph. Returns the removed list on success."""
    removed = generate.closed_freeway_edges(G, SCENARIOS["rosequarter"])
    got_sb = {e for e in removed if e in EXPECTED_SB}
    if got_sb != EXPECTED_SB or len(removed) != EXPECTED_REMOVED_N:
        raise SystemExit(
            f"frozen-span mismatch: selected {len(removed)} edges "
            f"({sorted(removed)}), pre-registered {EXPECTED_REMOVED_N} with SB "
            f"mainline {sorted(EXPECTED_SB)}. The graph differs from the one "
            f"the span was verified on; do NOT run, re-verify first.")
    return removed


def _apply_access_closure(G):
    """The Appendix O partial closure. Verifies the frozen FULL-closure spec
    still selects its 5 edges first (the graph-identity anchor), then keeps
    the access-lane pair, clamps the kept mainline to one lane, and removes
    the rest. Mutates G; returns the removed list."""
    full = _verify_span(G)
    keep = {ACCESS_KEEP_MAINLINE, ACCESS_KEEP_RAMP}
    if not keep <= set(full):
        raise SystemExit(f"access-lane spec mismatch: kept edges {sorted(keep)} "
                         f"are not inside the verified full closure "
                         f"{sorted(full)}; do NOT run, re-verify first.")
    to_remove = [e for e in full if e not in keep]
    if len(to_remove) != ACCESS_EXPECTED_REMOVED_N:
        raise SystemExit(f"access-lane spec mismatch: would remove "
                         f"{len(to_remove)} edges ({sorted(to_remove)}), "
                         f"pre-registered {ACCESS_EXPECTED_REMOVED_N}.")
    d = G.edges[ACCESS_KEEP_MAINLINE]
    if str(d.get("lanes")) != ACCESS_ORIG_LANES:
        raise SystemExit(f"access-lane guard: kept mainline tags lanes="
                         f"{d.get('lanes')!r}, pre-registered "
                         f"{ACCESS_ORIG_LANES!r}. Different graph; refusing.")
    # clamp to ODOT's single open lane. The plain 'lanes' tag is rewritten and
    # the directional variants dropped so lanes_real rule A cannot resurrect
    # the original count from a lanes:forward tag.
    d["lanes"] = ACCESS_OPEN_LANES
    for tag in ("lanes:forward", "lanes:backward", "lanes:both_ways"):
        d.pop(tag, None)
    G.remove_edges_from(to_remove)
    return to_remove


def check():
    G = _load_metro_graph()
    removed = _verify_span(G)
    print(f"graph: {G.number_of_nodes():,} nodes / {G.number_of_edges():,} edges")
    print(f"frozen span OK: {len(removed)} edges "
          f"({len(EXPECTED_SB)} SB mainline + "
          f"{len(removed) - len(EXPECTED_SB)} stranded ramps)")
    if STACK_COMPLIANCE:
        # Compliance variant: apply the FULL closure to this loaded graph, set
        # the flags exactly as run_task sets them for a closed task, and run
        # every detour guard end to end (fresh open-graph load, marker edge
        # present there and absent here, via node on the I-405 mainline).
        generate.apply_freeway_closure(G, SCENARIOS["rosequarter"])
        for k in REALISM_FLAGS:
            setattr(config, k, True)
        config.LANES_REAL = True
        config.LANES_ENABLED = False
        config.DETOUR_COMPLIANCE_ENABLED = True
        ctx = generate.build_detour_context(G)
        print(f"detour guards OK: via {ctx['via']} on the I-405 mainline, "
              f"marker edge {ctx['marker']}, registered shares "
              f"{COMPLIANCE_SHARES}")
        return
    if STACK_REROUTE:
        # Reroute variant: build the reroute context under the exact flags
        # run_task sets for an "on" cell (prepare_network first: the
        # context's queue-discharge headway needs the resolved n_lanes), so
        # a broken graph or constant fails here, before 32 tasks are queued.
        for k in REALISM_FLAGS:
            setattr(config, k, True)
        config.LANES_REAL = True
        config.LANES_ENABLED = False
        config.REROUTE_ENABLED = True
        config.REROUTE_STUCK_S = 120.0
        config.REROUTE_COOLDOWN_S = 300.0
        config.REROUTE_MAX_PER_STEP = 20
        generate.prepare_network(G)
        ctx = generate.build_reroute_context(G)
        print(f"reroute context OK: {len(ctx['t0']):,} edges weighted; "
              f"registered constants stuck 120 s / cooldown 300 s / cap 20 "
              f"per step")
        return
    if not STACK_ACCESS:
        return
    # Access-lane variant: apply the partial closure to this loaded graph and
    # verify it end to end, through the same lane machinery the sim will use.
    removed = _apply_access_closure(G)
    print(f"access closure OK: removed {len(removed)} edges, kept "
          f"{ACCESS_KEEP_MAINLINE} (clamped {ACCESS_ORIG_LANES}->"
          f"{ACCESS_OPEN_LANES} lanes) and the 302A off-ramp")
    succ = {v for _u, v, _k in G.out_edges(ACCESS_KEEP_MAINLINE[1], keys=True)}
    if succ != {ACCESS_KEEP_RAMP[1]}:
        raise SystemExit(f"forced-exit check FAILED: node "
                         f"{ACCESS_KEEP_MAINLINE[1]} exits to {sorted(succ)}, "
                         f"expected only the 302A off-ramp")
    print(f"forced exit OK: node {ACCESS_KEEP_MAINLINE[1]}'s only outgoing "
          f"edge is the 302A off-ramp")
    # run prepare_network under the exact flags run_task sets for this arm and
    # confirm the clamp survives the real-lanes path (lanes_real, not
    # _parse_lanes, resolves counts on the improved stack)
    for k in REALISM_FLAGS:
        setattr(config, k, True)
    config.LANES_REAL = True
    config.LANES_ENABLED = False
    generate.prepare_network(G)
    n = G.edges[ACCESS_KEEP_MAINLINE].get("n_lanes")
    if n != int(ACCESS_OPEN_LANES):
        raise SystemExit(f"lane-clamp check FAILED: prepare_network resolved "
                         f"n_lanes={n} on the kept mainline, expected "
                         f"{ACCESS_OPEN_LANES}")
    print(f"lane clamp OK: prepare_network resolves the kept mainline to "
          f"n_lanes={n}")


def selftest():
    """Spawn-level verification of the compliance machinery, no simulation.

    Three properties, registered with the arm: (1) share 0 is the IDENTITY,
    routes and the trip RNG stream byte-identical to spawning with the
    machinery off, so fwrqc reduces to fwrqi when nobody complies; (2)
    eligibility is share-independent, the same trips are eligible at every
    level; (3) at share 1 every compliant trip's route runs via the I-405
    mainline and the accounting closes (eligible = compliant + fallback).
    Uses uniform random ODs, so it needs no land-use data, on the real
    lane-tagged graph with the real closure applied."""
    for k in REALISM_FLAGS:
        setattr(config, k, True)
    config.LANES_REAL = True
    config.LANES_ENABLED = False
    config.MERGE_ENTRY_IMPROVED = False
    config.REROUTE_ENABLED = False
    config.RANDOM_SEED = SEEDS[0]

    G = _load_metro_graph()
    _verify_span(G)
    generate.apply_freeway_closure(G, SCENARIOS["rosequarter"])
    generate.prepare_network(G)
    i405 = {(u, v) for u, v, _k
            in generate.freeway_mainline_edges(G, "I 405")}
    nodes = list(G.nodes)
    K = 2000

    def spawn(ctx):
        rng = random.Random(config.RANDOM_SEED)
        vehs = []
        for vid in range(K):
            veh = generate.make_vehicle(G, nodes, rng, vid, detour_ctx=ctx)
            if veh is not None:
                vehs.append(veh)
        # the tail probe: where the trip stream ended up. Any compliance leak
        # into this stream shifts every draw after it, so one value suffices.
        return vehs, rng.random()

    print(f"spawning {K} uniform-OD vehicles x3 (off / share 0 / share 1)...")
    off_vehs, off_tail = spawn(None)

    config.DETOUR_COMPLIANCE_ENABLED = True
    config.DETOUR_COMPLIANCE_SHARE = 0.0
    ctx0 = generate.build_detour_context(G)
    z_vehs, z_tail = spawn(ctx0)
    if len(z_vehs) != len(off_vehs) or z_tail != off_tail:
        raise SystemExit("selftest FAILED: share 0 changed the spawn count "
                         "or the trip RNG stream")
    for a, b in zip(off_vehs, z_vehs):
        if a["route"] != b["route"]:
            raise SystemExit(f"selftest FAILED: share 0 changed vehicle "
                             f"{a['id']}'s route; not an identity")
    print(f"share 0 identity OK: {len(z_vehs)} spawns, every route and the "
          f"trip RNG stream byte-identical to the machinery off "
          f"({ctx0['n_eligible']} trips eligible, none complied)")

    # share 1: reuse the already-loaded open graph with a fresh stream and
    # counters; apart from skipping the reload this is exactly what
    # build_detour_context would return
    ctx1 = dict(ctx0, share=1.0,
                rng=random.Random(config.RANDOM_SEED + 4),
                n_eligible=0, n_compliant=0, n_fallback=0)
    one_vehs, one_tail = spawn(ctx1)
    if one_tail != off_tail:
        raise SystemExit("selftest FAILED: share 1 perturbed the trip RNG "
                         "stream")
    if ctx1["n_eligible"] != ctx0["n_eligible"]:
        raise SystemExit(f"selftest FAILED: eligibility depends on the share "
                         f"({ctx0['n_eligible']} at 0 vs "
                         f"{ctx1['n_eligible']} at 1)")
    if ctx1["n_eligible"] < 5:
        raise SystemExit(f"selftest FAILED: only {ctx1['n_eligible']} "
                         f"eligible trips in {K}; too few to exercise the "
                         f"machinery")
    if ctx1["n_compliant"] + ctx1["n_fallback"] != ctx1["n_eligible"]:
        raise SystemExit("selftest FAILED: eligible != compliant + fallback "
                         "at share 1")
    detoured = [v for v in one_vehs if v.get("detour")]
    if len(detoured) != ctx1["n_compliant"]:
        raise SystemExit("selftest FAILED: detour flags disagree with the "
                         "compliant count")
    for veh in detoured:
        if not any((u, v) in i405 for u, v, *_rest in veh["route"]):
            raise SystemExit(f"selftest FAILED: compliant vehicle "
                             f"{veh['id']}'s route never touches the I-405 "
                             f"mainline")
    print(f"share 1 OK: {ctx1['n_eligible']} eligible, "
          f"{ctx1['n_compliant']} complied, {ctx1['n_fallback']} fell back; "
          f"every compliant route runs via the I-405 mainline; trip stream "
          f"untouched")
    print("SELFTEST PASSED")


def run_task(idx):
    arm, seed, extra = tasks()[idx]
    out = summary_path(arm, seed, extra)
    if os.path.exists(out):
        print(f"task {idx} ({arm}, seed {seed}, extra {extra}) already done "
              f"-> {out}")
        return

    G = _load_metro_graph()

    # the seed is what this experiment varies, so set it before anything draws
    config.RANDOM_SEED = seed
    config.RUN_NAME = run_name(arm, seed, extra)

    # every stack flag EXPLICITLY True or False (the F6 rule): a task must
    # never inherit these from a config default or a reused interpreter.
    # The improved arm includes the full realism stack; the access-lane arm
    # (Appendix O) runs the improved stack verbatim, so the two arms differ
    # ONLY in the closed-arm graph surgery.
    for k in REALISM_FLAGS:
        setattr(config, k, STACK_REALISM or STACK_IMPROVED or STACK_ACCESS
                or STACK_COMPLIANCE or STACK_REROUTE)
    # absolute grams are cited under the mixed fleet (the live setting, gate
    # G2); explicit for the same reason as the stack flags
    config.FLEET_MIXED = True
    # the Appendix E demand-variant arm: non-work trips ON for fwrqn tasks,
    # explicitly OFF otherwise (the F6 rule), so no task can inherit the flag
    config.DEMAND_NONWORK_ENABLED = STACK_NONWORK
    # the Appendix K improved arm: corrected real lanes ON only there and on
    # the Appendix O access-lane arm that reuses its stack (this branch's
    # config defaults it True, so the OTHER arms must pin it False to
    # reproduce their registrations); the frictionless virtual-lane model
    # and the two mentor-ungated mechanisms are explicitly OFF everywhere
    config.LANES_REAL = (STACK_IMPROVED or STACK_ACCESS or STACK_COMPLIANCE
                         or STACK_REROUTE)
    config.LANES_ENABLED = False
    config.MERGE_ENTRY_IMPROVED = False
    # en-route rerouting: ON only for the fwrqe "on" cells (prereg Appendix
    # T), pinned explicitly False everywhere else (the F6 rule). Constants
    # pinned to the registered values whenever the fwrqe stack runs, so a
    # drifted config default can never change the arm's identity; they are
    # inert on the "off" cells (flag off skips the pass entirely, the
    # gate-verified bitwise identity).
    config.REROUTE_ENABLED = bool(STACK_REROUTE and extra == "on")
    if STACK_REROUTE:
        config.REROUTE_STUCK_S = 120.0
        config.REROUTE_COOLDOWN_S = 300.0
        config.REROUTE_MAX_PER_STEP = 20
    # signed-detour compliance: ON only for the fwrqc CLOSED tasks, and pinned
    # explicitly False for every other task (the F6 rule), so no arm can
    # inherit it. The open arm runs with it off, which is what makes the
    # fwrqc open summaries a registered per-seed identity check against
    # fwrqi's open summaries.
    config.DETOUR_COMPLIANCE_ENABLED = bool(STACK_COMPLIANCE
                                            and arm != "open")
    if config.DETOUR_COMPLIANCE_ENABLED:
        config.DETOUR_COMPLIANCE_SHARE = extra

    removed = []
    if arm != "open":
        if STACK_ACCESS:
            removed = _apply_access_closure(G)
            print(f"[{config.RUN_NAME}] removed {len(removed)} freeway edges "
                  f"(access-lane partial closure; kept mainline clamped to "
                  f"{ACCESS_OPEN_LANES} lane)")
        else:
            removed = _verify_span(G)
            generate.apply_freeway_closure(G, SCENARIOS[arm])
            print(f"[{config.RUN_NAME}] removed {len(removed)} freeway edges")

    generate.set_seeds(seed)
    # opt-in compliance counts (generate.run_simulation contract): filled for
    # fwrqc closed tasks so the saved summary, not just the task log, records
    # the realized share (single-source-of-truth rule)
    dstats = {} if config.DETOUR_COMPLIANCE_ENABLED else None
    # fwrqe instrumentation (all 32 tasks): stuck_stats so the saved parquet
    # carries the per-segment stuck_sum column (the fwrq/fwrqi campaigns
    # never opted in, which is why the arm's "off" cells exist at all), and
    # reroute_stats on the "on" cells so the promised re-plan counts land in
    # the saved summary (the RR35 lesson), not only in the task log
    sstats = {} if STACK_REROUTE else None
    rstats = {} if config.REROUTE_ENABLED else None
    totals, nox, thru = generate.run_simulation(G, use_checkpoint=False,
                                                detour_stats=dstats,
                                                stuck_stats=sstats,
                                                reroute_stats=rstats)
    generate.save_results(totals, nox, thru, stuck_stats=sstats)

    # Compact summary so the readout needs only these files, not the parquets.
    # Per-edge values for the tracked mainlines let the readout do span-level
    # and paired per-segment tests, not just route totals.
    routes = {}
    for ref in TRACK_ROUTES:
        keys = generate.freeway_mainline_edges(G, ref)
        if not keys:
            continue
        routes[ref] = {f"{u}_{v}_{k}": [float(nox.get((u, v, k), 0.0)),
                                        float(thru.get((u, v, k), 0.0))]
                       for u, v, k in keys}
    rec = {
        "arm": arm, "seed": seed,
        "stack": ("reroute" if STACK_REROUTE else
                  "compliance" if STACK_COMPLIANCE else
                  "access" if STACK_ACCESS else
                  "improved" if STACK_IMPROVED else
                  "realism" if STACK_REALISM else "base"),
        "nonwork": STACK_NONWORK,
        # compliance arm only: the registered level this closed task ran at
        # (None on the shared open arm) and the realized whole-run counts
        "share": (extra if STACK_COMPLIANCE else None),
        "detour_stats": dstats or {},
        "fleet": "mixed",
        "n_vehicles": config.N_VEHICLES, "n_steps": config.N_STEPS,
        "removed": [[u, v, k] for u, v, k in removed],
        # access-lane arm only: the kept, clamped mainline edge, so the file
        # says what its closure actually was rather than relying on the prefix
        "access_kept": ([list(ACCESS_KEEP_MAINLINE), list(ACCESS_KEEP_RAMP)]
                        if (STACK_ACCESS and arm != "open") else []),
        "network_nox_g": float(sum(nox.values())),
        "network_throughput": float(sum(thru.values())),
        "routes": routes,
    }
    if STACK_REROUTE:
        # cell identity plus the instrumented network stuck total, so the
        # readout and the Appendix T stuck-time grading need only these
        # summaries, never the parquets (compact-summary rule above)
        rec["reroute_on"] = (extra == "on")
        rec["reroute_stats"] = rstats or {}
        rec["stuck_veh_h"] = sum(sstats["stuck_sum"].values()) / 3600.0
    with open(out, "w") as f:
        json.dump(rec, f)
    print(f"[{config.RUN_NAME}] summary -> {out}")


def _paired(summaries, ref, field):
    """Per-seed paired difference on route `ref`, closed minus open.
    field 0 = NOx grams, 1 = throughput."""
    diffs, rel = [], []
    for seed in SEEDS:
        o = summaries.get(("open", seed))
        c = summaries.get(("rosequarter", seed))
        if not o or not c or ref not in o["routes"] or ref not in c["routes"]:
            continue
        # the closed run is missing the removed edges; treat them as zero so
        # the route total is comparable rather than silently shorter
        ko = o["routes"][ref]
        kc = c["routes"][ref]
        so = sum(v[field] for v in ko.values())
        sc = sum(kc.get(key, [0.0, 0.0])[field] for key in ko)
        diffs.append(sc - so)
        rel.append(100.0 * (sc - so) / so if so else float("nan"))
    return np.array(diffs), np.array(rel)


def _print_route_table(summaries):
    """The campaign's standard verdict table: paired per-seed differences on
    every tracked route, unanimous sign AND |t|>3 as the registered bar."""
    print(f"{'route':>8s} {'n':>3s} {'mean %':>8s} {'sd %':>7s} "
          f"{'min %':>7s} {'max %':>7s} {'signs':>7s}  verdict")
    for ref in TRACK_ROUTES:
        d, rel = _paired(summaries, ref, 0)
        if len(d) < 2:
            continue
        pos = int((d > 0).sum())
        # the standing campaign bar: unanimous sign AND |t|>3 (with 8 seeds a
        # unanimous sign is p = 2^-8 = 0.004 under a fair-coin null)
        unanimous = pos == len(d) or pos == 0
        t = abs(rel.mean()) / (rel.std(ddof=1) / np.sqrt(len(rel))) \
            if rel.std(ddof=1) > 0 else float("inf")
        verdict = ("SUPPORTED" if unanimous and t > 3
                   else "weak" if unanimous else "NOT SUPPORTED")
        print(f"{ref:>8s} {len(d):3d} {rel.mean():+8.2f} {rel.std(ddof=1):7.2f} "
              f"{rel.min():+7.2f} {rel.max():+7.2f} {pos:3d}/{len(d):<3d} "
              f" {verdict} (t={t:.1f})")


def _readout_compliance():
    """Per-level paired readout for the fwrqc campaign, preceded by the
    registered per-seed identity check of its shared open arm against
    fwrqi's open arm (same stack, same flags, so the summaries must match
    exactly; a mismatch means environment drift and voids the contrast)."""
    opens = {}
    for seed in SEEDS:
        p = summary_path("open", seed)
        if os.path.exists(p):
            with open(p) as f:
                opens[seed] = json.load(f)
    print(f"stack: compliance\nopen summaries: {len(opens)}/{len(SEEDS)}")

    compared, mismatches = 0, 0
    for seed, rec in sorted(opens.items()):
        q = os.path.join(config.PROCESSED_DIR,
                         f"fwrqi_open_s{seed}_summary.json")
        if not os.path.exists(q):
            continue
        with open(q) as f:
            ref = json.load(f)
        compared += 1
        same = (rec["network_nox_g"] == ref["network_nox_g"]
                and rec["network_throughput"] == ref["network_throughput"]
                and rec["routes"] == ref["routes"])
        if not same:
            mismatches += 1
            print(f"  INTEGRITY FAIL seed {seed}: fwrqc_open differs from "
                  f"fwrqi_open")
    if compared:
        print(f"open-arm identity vs fwrqi: {compared - mismatches}/"
              f"{compared} seeds match exactly")
        if mismatches:
            raise SystemExit("registered integrity check FAILED; do not "
                             "cite this campaign until resolved")
    else:
        print("open-arm identity vs fwrqi: no fwrqi_open summaries in this "
              "PROCESSED_DIR, not checked here")

    for share in COMPLIANCE_SHARES:
        summaries = {("open", seed): rec for seed, rec in opens.items()}
        n_closed, realized = 0, []
        for seed in SEEDS:
            p = summary_path("rosequarter", seed, share)
            if not os.path.exists(p):
                continue
            with open(p) as f:
                rec = json.load(f)
            if rec.get("stack") != "compliance" or rec.get("share") != share:
                raise SystemExit(f"{p} records stack={rec.get('stack')!r} "
                                 f"share={rec.get('share')!r}; wrong file "
                                 f"for level {share}")
            summaries[("rosequarter", seed)] = rec
            n_closed += 1
            ds = rec.get("detour_stats") or {}
            if ds.get("n_eligible"):
                realized.append(100.0 * ds["n_compliant"] / ds["n_eligible"])
        head = (f"COMPLIANCE {share:.0%}: paired per-seed differences "
                f"(closed - open, same seed); {n_closed}/{len(SEEDS)} "
                f"closed summaries")
        if realized:
            head += f", realized compliance {np.mean(realized):.1f}%"
        print(f"\n{'=' * 72}\n{head}\n{'=' * 72}")
        if min(len(opens), n_closed) < 2:
            print("  fewer than 2 paired seeds at this level; skipping")
            continue
        _print_route_table(summaries)


def _readout_reroute():
    """Four-cell readout for the fwrqe campaign (prereg Appendix T), led by
    the registered OFF-pair identity check: rerouting off plus measurement-
    only stuck instrumentation must reproduce the banked fwrqi summaries
    EXACTLY, per seed, on BOTH arms (network totals and every tracked
    route). A mismatch means the environment drifted since Appendix K and
    voids the campaign; this readout refuses to grade past it."""
    recs = {}
    for arm, seed, cell in tasks():
        p = summary_path(arm, seed, cell)
        if not os.path.exists(p):
            continue
        with open(p) as f:
            rec = json.load(f)
        if (rec.get("stack") != "reroute"
                or rec.get("reroute_on") != (cell == "on")):
            raise SystemExit(f"{p} records stack={rec.get('stack')!r} "
                             f"reroute_on={rec.get('reroute_on')!r}; wrong "
                             f"file for the {cell!r} cell")
        recs[(cell, arm, seed)] = rec
    have = {(cell, arm): sum(1 for (c, a, _s) in recs if (c, a) == (cell, arm))
            for cell in ("off", "on") for arm in ARMS}
    print("stack: reroute (fwrqe, prereg Appendix T; the C1 mechanism "
          "failed its registered\nacceptance gate, ledger RR35.1, and runs "
          "here as a disclosed exploratory arm)")
    print("summaries found: " +
          ", ".join(f"{cell}/{arm} {have[(cell, arm)]}/{len(SEEDS)}"
                    for cell in ("off", "on") for arm in ARMS))

    # Registered integrity check: OFF-pair identity with the banked fwrqi
    # summaries, both arms, per seed (same fields as the fwrqc open check).
    compared, mismatches = 0, 0
    for seed in SEEDS:
        for arm in ARMS:
            rec = recs.get(("off", arm, seed))
            q = os.path.join(config.PROCESSED_DIR,
                             f"fwrqi_{arm}_s{seed}_summary.json")
            if rec is None or not os.path.exists(q):
                continue
            with open(q) as f:
                ref = json.load(f)
            compared += 1
            same = (rec["network_nox_g"] == ref["network_nox_g"]
                    and rec["network_throughput"] == ref["network_throughput"]
                    and rec["routes"] == ref["routes"])
            if not same:
                mismatches += 1
                print(f"  INTEGRITY FAIL {arm} seed {seed}: fwrqeoff "
                      f"differs from fwrqi")
    if compared:
        print(f"off-pair identity vs fwrqi: {compared - mismatches}/"
              f"{compared} arm-seeds match exactly")
        if mismatches:
            raise SystemExit("registered integrity check FAILED; do not "
                             "cite this campaign until resolved")
    else:
        print("off-pair identity vs fwrqi: no fwrqi summaries in this "
              "PROCESSED_DIR, not checked here")

    # Re-plan accounting (registered reporting duty: the per-step cap is a
    # compute budget, not physics, so whether it bound is always reported).
    capped = 0
    for cell, arm, seed in sorted(recs):
        rs = recs[(cell, arm, seed)].get("reroute_stats") or {}
        if not rs:
            continue
        capped += 1 if rs.get("n_cap_steps") else 0
        print(f"  re-plans {arm} s{seed}: {rs['n_reroutes']:,} ok, "
              f"{rs['n_failed']:,} no-path, cap bound on "
              f"{rs['n_cap_steps']:,} step(s)")
    if capped:
        print(f"NOTE: the per-step compute budget bound in {capped} run(s); "
              f"this caveat travels with any cited fwrqe number")

    # Paired route tables, closed - open within each cell. The OFF table
    # should reproduce Appendix L's fwrqi numbers; the ON table is T3/T4.
    for cell, label in (("off", "OFF pair (instrumented fwrqi rerun)"),
                        ("on", "ON pair (en-route rerouting)")):
        summaries = {(arm, seed): recs[(cell, arm, seed)]
                     for arm in ARMS for seed in SEEDS
                     if (cell, arm, seed) in recs}
        n = {a: sum(1 for (arm, _s) in summaries if arm == a) for a in ARMS}
        print(f"\n{'=' * 72}\nREROUTE {label}: paired per-seed differences "
              f"(closed - open, same seed)\n{'=' * 72}")
        if not n or min(n.values()) < 2:
            print("  fewer than 2 paired seeds; skipping")
            continue
        _print_route_table(summaries)

    # Stuck vehicle-hours, rerouting ON minus OFF per seed and arm: the
    # Appendix T primary (T1, closed) and replication (T2, open), graded by
    # the standing bar with the registered direction DOWN.
    print(f"\n{'=' * 72}\nSTUCK VEHICLE-HOURS: paired per-seed differences "
          f"(rerouting on - off, same seed)\n{'=' * 72}")
    for arm, tag in (("rosequarter", "T1 closed-arm"),
                     ("open", "T2 open-arm")):
        rel = []
        for seed in SEEDS:
            a = recs.get(("on", arm, seed))
            b = recs.get(("off", arm, seed))
            if (not a or not b or a.get("stuck_veh_h") is None
                    or not b.get("stuck_veh_h")):
                continue
            rel.append(100.0 * (a["stuck_veh_h"] - b["stuck_veh_h"])
                       / b["stuck_veh_h"])
        if len(rel) < 2:
            print(f"{tag}: fewer than 2 paired seeds; skipping")
            continue
        r = np.array(rel)
        neg = int((r < 0).sum())
        down_unanimous = neg == len(r)
        t = (abs(r.mean()) / (r.std(ddof=1) / np.sqrt(len(r)))
             if r.std(ddof=1) > 0 else float("inf"))
        verdict = ("SUPPORTED" if down_unanimous and t > 3
                   else "weak" if down_unanimous else "NOT SUPPORTED")
        print(f"{tag}: mean {r.mean():+.2f}% sd {r.std(ddof=1):.2f} "
              f"(min {r.min():+.2f} max {r.max():+.2f}), "
              f"down {neg}/{len(r)}, t={t:.1f} -> {verdict} "
              f"(registered direction: DOWN)")


def readout():
    if STACK_COMPLIANCE:
        return _readout_compliance()
    if STACK_REROUTE:
        return _readout_reroute()
    summaries = {}
    for arm, seed, share in tasks():
        p = summary_path(arm, seed, share)
        if os.path.exists(p):
            with open(p) as f:
                summaries[(arm, seed)] = json.load(f)
    want = ("access" if STACK_ACCESS else
            "improved" if STACK_IMPROVED else
            "realism" if STACK_REALISM else "base")
    for (arm, seed), s in summaries.items():
        got = s.get("stack", "base")
        if got != want:
            raise SystemExit(f"{summary_path(arm, seed)} records stack={got} "
                             f"but this readout is for {want}; wrong file")
        if bool(s.get("nonwork", False)) != STACK_NONWORK:
            raise SystemExit(f"{summary_path(arm, seed)} records "
                             f"nonwork={s.get('nonwork', False)} but this "
                             f"readout is for nonwork={STACK_NONWORK}; wrong file")
    have = {a: sum(1 for (arm, _) in summaries if arm == a) for a in ARMS}
    print("stack: " + want)
    print("summaries found: " +
          ", ".join(f"{a} {have[a]}/{len(SEEDS)}" for a in ARMS))
    if min(have.values()) < 2:
        raise SystemExit("need at least 2 paired seeds for a distribution")

    print(f"\n{'=' * 72}\nROSE QUARTER I-5 SB: paired per-seed differences "
          f"(closed - open, same seed)\n{'=' * 72}")
    _print_route_table(summaries)


def main():
    global STACK_REALISM, STACK_NONWORK, STACK_IMPROVED, STACK_ACCESS, \
        STACK_COMPLIANCE, STACK_REROUTE, PREFIX
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--list", action="store_true")
    g.add_argument("--count", action="store_true")
    g.add_argument("--task", type=int)
    g.add_argument("--readout", action="store_true")
    g.add_argument("--selftest", action="store_true",
                   help="spawn-level verification of the compliance "
                        "machinery (requires --compliance); no simulation")
    ap.add_argument("--realism", action="store_true",
                    help="run/readout the realism-stack secondary arm (fwrqr)")
    ap.add_argument("--nonwork", action="store_true",
                    help="run/readout the non-work demand-variant arm (fwrqn, "
                         "prereg Appendix E)")
    ap.add_argument("--improved", action="store_true",
                    help="run/readout the PORTAL-validated improved-model arm "
                         "(fwrqi, prereg Appendix K: realism stack + corrected "
                         "real lanes on the lane-tagged graph)")
    ap.add_argument("--accesslane", action="store_true",
                    help="run/readout the closure-geometry arm (fwrqa, prereg "
                         "Appendix O: the fwrqi stack verbatim, but the closed "
                         "arm keeps ODOT's one local-access lane to the "
                         "Broadway/Weidler exit instead of a full shutdown)")
    ap.add_argument("--compliance", action="store_true",
                    help="run/readout the signed-detour compliance arm "
                         "(fwrqc: the fwrqi stack and full closure verbatim, "
                         "but each through trip follows ODOT's official "
                         "I-405 detour with a registered probability, three "
                         "levels 25/50/75%%, shared open arm)")
    ap.add_argument("--reroute", action="store_true",
                    help="run/readout the en-route rerouting arm (fwrqe, "
                         "prereg Appendix T: the fwrqi stack and full "
                         "closure verbatim, four cells off/on x open/closed; "
                         "DISCLOSED exploratory arm, the C1 mechanism failed "
                         "its registered acceptance gate, ledger RR35.1)")
    args = ap.parse_args()

    if sum([args.realism, args.nonwork, args.improved, args.accesslane,
            args.compliance, args.reroute]) > 1:
        raise SystemExit("--realism / --nonwork / --improved / --accesslane "
                         "/ --compliance / --reroute are distinct registered "
                         "arms; pick one")
    if args.selftest and not args.compliance:
        raise SystemExit("--selftest verifies the compliance machinery; "
                         "add --compliance")
    if args.realism:
        STACK_REALISM = True
        PREFIX = "fwrqr"
    if args.nonwork:
        STACK_NONWORK = True
        PREFIX = "fwrqn"
    if args.improved:
        STACK_IMPROVED = True
        PREFIX = "fwrqi"
    if args.accesslane:
        STACK_ACCESS = True
        PREFIX = "fwrqa"
    if args.compliance:
        STACK_COMPLIANCE = True
        PREFIX = "fwrqc"
    if args.reroute:
        STACK_REROUTE = True
        PREFIX = "fwrqe"

    if args.check:
        check()
    elif args.selftest:
        selftest()
    elif args.list:
        for i, (arm, seed, extra) in enumerate(tasks()):
            lvl = ("" if extra is None else
                   f"  reroute {extra}" if isinstance(extra, str) else
                   f"  share {extra:.2f}")
            print(f"{i:3d}  {arm:>12s}  seed {seed}{lvl}")
    elif args.count:
        print(len(tasks()))
    elif args.task is not None:
        run_task(args.task)
    else:
        readout()


if __name__ == "__main__":
    main()
