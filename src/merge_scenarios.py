"""Merge-discharge test-bench: measure the junction throttle, then the fix.

The blackspot trace (src/blackspot_trace.py) showed 4 of the 5 too-hard freeway
jams are queues discharging ~1,000 veh/hr per contested lane through a merge or
diverge into a downstream edge that is running FREE, so the junction entry rule
itself, not road capacity, is the bottleneck. This bench reproduces that
mechanism on a toy network THROUGH THE REAL KERNEL (the same step_vehicles
generate.py uses, in the same explicit-MOBIL lane mode as the validated
lcap_realism_reallanes arm) and measures queue discharge with the legacy entry
rule and with config.MERGE_ENTRY_IMPROVED, side by side.

Scenarios (all: standing queues on the feeders, downstream initially empty and
long enough that nothing exits during the window):

  control  one 1-lane feeder -> 1-lane road. No competition; both rules should
           discharge close to the kernel's plain queue-discharge rate, so this
           is the yardstick the merges are judged against, and the improved
           rule must NOT inflate it (that would be new physics, not a fix).
  zipper   two 1-lane feeders -> one 1-lane road: pure merge competition.
           Expect legacy to serialize (well under control's rate); improved
           should approach control's single-lane rate, split between feeders.
  ramp2    two 1-lane feeders -> 2-lane road. Room for both streams; legacy
           explicit lane-keeping sends both into lane 0 and wastes lane 1 at
           the entrance. Improved should approach 2x the control rate.
  i205     2-lane mainline + 1-lane ramp -> 3-lane road, the I-205-to-I-84
           blackspot's shape. Improved should approach 3x the control rate.

Discharge = vehicles fully crossing a feeder's end per hour (the kernel's own
segment_throughput), measured after a warmup, feeders kept saturated by the
preloaded queue. Physicality guard: per-downstream-lane discharge above
~2,400 veh/hr (the IDM headway ceiling) would mean overlap artifacts, printed
as a WARNING.

Usage:  python src/merge_scenarios.py
"""
import os
import random
import sys
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import emissions
import mobil
from generate import step_vehicles

V0 = 26.8              # m/s, ~60 mph freeway limit (discharge is v0-insensitive)
FEEDER_M = 4000.0      # long enough that the queue never exhausts in the window
DOWN_M = 25000.0       # long enough that no car finishes its route (no respawn)
WARMUP_S = 120
WINDOW_S = 600
JAM_SPACING = config.VEHICLE_LENGTH_M + config.IDM_S0   # bumper-to-bumper queue
LANE_CEILING_VPH = 2400.0    # IDM headway ceiling; above this = overlap artifact


def _no_signals():
    return {"nodes": set(), "offset": {}, "edge_phase": {},
            "cycle": config.SIGNAL_CYCLE_S, "green_split": config.SIGNAL_GREEN_SPLIT}


def build(feeders, n_down):
    """Vehicles + mobil_ctx for one scenario.

    feeders: list of (node_id, n_lanes). Every feeder ends at node 9; the
    downstream edge (9 -> 3) has n_down lanes. Each feeder is preloaded with a
    standing queue at jam spacing in every lane, head at the stop line.
    """
    down = (9, 3, 0, DOWN_M, V0)
    lanes = {down[:3]: n_down}
    vehicles, vid = [], 0
    for node, n_lanes in feeders:
        fed = (node, 9, 0, FEEDER_M, V0)
        lanes[fed[:3]] = n_lanes
        per_lane = int((FEEDER_M - JAM_SPACING) / JAM_SPACING)
        for lane in range(n_lanes):
            for i in range(per_lane):
                vehicles.append({
                    "id": vid, "route": [fed, down], "idx": 0,
                    "pos": FEEDER_M - i * JAM_SPACING, "v": 0.0, "lane": lane})
                vid += 1
    ctx = {"params": mobil.params_from_config(config), "lanes": lanes}
    return vehicles, ctx


def run(feeders, n_down, improved):
    """One scenario under one entry rule; returns per-feeder discharge (veh/h)."""
    config.MERGE_ENTRY_IMPROVED = improved
    vehicles, ctx = build(feeders, n_down)
    signals = _no_signals()
    coeffs = emissions.active_coeffs()
    thru = defaultdict(float)
    baseline = {}
    for s in range(WARMUP_S + WINDOW_S):
        if s == WARMUP_S:
            baseline = {k: v for k, v in thru.items()}
        step_vehicles(vehicles, config.DT, s * config.DT, defaultdict(float),
                      defaultdict(float), thru, coeffs, None, [],
                      random.Random(0), signals, mobil_ctx=ctx)
    out = {}
    for node, _ in feeders:
        key = (node, 9, 0)
        out[node] = (thru[key] - baseline.get(key, 0.0)) * 3600.0 / WINDOW_S
    return out


def main():
    scenarios = [
        ("control", [(1, 1)], 1),
        ("zipper",  [(1, 1), (2, 1)], 1),
        ("ramp2",   [(1, 1), (2, 1)], 2),
        ("i205",    [(1, 2), (2, 1)], 3),
    ]
    print("merge-discharge bench: real kernel, explicit MOBIL lanes, "
          f"{WINDOW_S} s window after {WARMUP_S} s warmup")
    print(f"{'scenario':<9}{'lanes in->out':>14}{'rule':>10}"
          f"{'total/h':>9}{'per feeder':>22}{'per dn lane':>12}")
    results = {}
    for name, feeders, n_down in scenarios:
        n_in = "+".join(str(n) for _, n in feeders)
        for improved in (False, True):
            per = run(feeders, n_down, improved)
            total = sum(per.values())
            split = " / ".join(f"{per[n]:,.0f}" for n, _ in feeders)
            lane_rate = total / n_down
            warn = "  WARNING > IDM ceiling" if lane_rate > LANE_CEILING_VPH else ""
            rule = "improved" if improved else "legacy"
            print(f"{name:<9}{n_in + ' -> ' + str(n_down):>14}{rule:>10}"
                  f"{total:>9,.0f}{split:>22}{lane_rate:>12,.0f}{warn}")
            results[(name, improved)] = total
    config.MERGE_ENTRY_IMPROVED = False        # leave the module as configured

    ctrl_legacy = results[("control", False)]
    ctrl_improved = results[("control", True)]
    print(f"\ncontrol drift (improved vs legacy, must stay small): "
          f"{100 * (ctrl_improved / ctrl_legacy - 1):+.1f}%")
    for name, _, n_down in scenarios[1:]:
        print(f"{name}: legacy reaches {100 * results[(name, False)] / (n_down * ctrl_legacy):.0f}% "
              f"of {n_down}x control, improved {100 * results[(name, True)] / (n_down * ctrl_improved):.0f}%")


if __name__ == "__main__":
    main()
