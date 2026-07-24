"""Hand-checkable scenarios for the DRIVER-HETEROGENEITY experiment (Phase 2).

Same discipline as scenarios.py / lanes_scenarios.py (Christof's Jun 24 ask: show
it works with values predictable by hand, through the REAL kernel, never a
reimplementation). Three checks:

  A) INERTNESS. With every driver sigma 0, the heterogeneity machinery must
     reproduce the single-parameter base kernel EXACTLY, position for position:
     drawing all-zero-sigma factors yields the config defaults, so a car carrying
     that "idm" set must behave byte-for-byte like a car with none. This proves
     turning the flag off (or to zero dispersion) gives back the committed model.

  B) DISPERSION. Release drivers with heterogeneous DESIRED SPEEDS onto open road,
     each alone on its own segment so there is no car-following to confound the
     test (the base model has no lane changing, so on a shared lane a fast driver
     stuck behind a slow one could not pass, and a compressed start adds a spurious
     head-start transient). Each free car then settles to exactly its OWN desired
     speed, v0 * its drawn factor, so the per-car speeds fan out and the front
     runner pulls away from the tail: after a fixed run the fastest and slowest
     drivers are ~(factor spread) * v0 * t apart. With every sigma 0 all cars share
     one desired speed and there is no spread at all. Predicted speeds are read
     straight from the drawn factors, so every number is checkable by hand.

  C) OWN s0 AT SEGMENT ENTRY. The per-vehicle parameters must be applied
     CONSISTENTLY: the segment-entry (spillback) hold has its own gap test, and it
     must use the same s0 the car's acceleration uses, not the config constant.
     A driver with a shorter jam distance therefore enters a gap the default
     driver is held out of, with the flag-off path unchanged. (Added Jul 23 with
     the fix for audit item 6, which found the two places disagreeing.)

Run: python src/driver_scenarios.py
"""
import os
import sys
import random
from collections import defaultdict

import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import drivers
import emissions
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


def _signal_at_2():
    """One signalized node (2), zero offset: phase 0 green on [0,30), red [30,60)."""
    return {"nodes": {2}, "offset": {2: 0.0},
            "edge_phase": {(1, 2, 0): 0, (2, 3, 0): 0},
            "cycle": 60.0, "green_split": 0.5}


def _run(vehs, signals, n_steps, t0=0, lanes=None):
    """Step the real kernel n_steps, mutating vehs in place. Cars never finish
    their route in these scenarios, so the G/nodes/rng respawn args are dummies
    (same shortcut as lanes_scenarios.py)."""
    coeffs = emissions.active_coeffs()
    seg_tot, seg_nox, seg_thru = defaultdict(float), defaultdict(float), defaultdict(float)
    for s in range(n_steps):
        step_vehicles(vehs, config.DT, (t0 + s) * config.DT, seg_tot, seg_nox,
                      seg_thru, coeffs, None, [], random.Random(0), signals,
                      None, None, lanes=lanes)


def _queued(n, idm_list=None):
    """n cars in a single-file queue at the stop line of a 400 m edge, at the IDM
    equilibrium spacing (L + s0 = 7 m). Optionally attach a per-vehicle idm set."""
    v0 = 50 * KPH
    route = [_edge(1, 2, 400.0, v0), _edge(2, 3, 600.0, v0)]
    vehs = [{"id": j, "route": list(route), "idx": 0,
             "pos": 398.0 - 7.0 * j, "v": 0.0} for j in range(n)]
    if idm_list is not None:
        for veh, idm in zip(vehs, idm_list):
            veh["idm"] = idm
    return vehs


def scenario_inertness():
    print("\nA) INERTNESS: all-sigma-0 heterogeneity must reproduce the base kernel")
    print("   First the draw itself: with every sigma 0, drivers.sample must return")
    print("   the config IDM defaults exactly (v0_factor 1.0, a/b/T/s0 unscaled).")
    zero = {p: 0.0 for p in drivers.PARAMS}
    got = drivers.sample(random.Random(999), zero)
    want = {"v0_factor": 1.0, "a_max": config.IDM_A_MAX, "b_comf": config.IDM_B_COMF,
            "T": config.IDM_T, "s0": config.IDM_S0}
    ok = [_check("all-sigma-0 draw equals the config defaults exactly",
                 got == want, f"{got}")]

    print("   Then the kernel: a 20-car queue + one full signal cycle, run two ways:")
    print("   no per-vehicle idm (base) vs every car carrying the all-sigma-0 set.")
    drng = random.Random(config.RANDOM_SEED + 3)
    het = [drivers.sample(drng, zero) for _ in range(20)]     # all identical to defaults
    runs = {}
    for label, idm_list in (("base", None), ("hetero_s0", het)):
        vehs = _queued(20, idm_list)
        _run(vehs, _signal_at_2(), 60, t0=30)
        runs[label] = np.array([(v["idx"], v["pos"], v["v"]) for v in vehs])
    same = np.array_equal(runs["base"], runs["hetero_s0"])
    ok.append(_check("trajectories identical (idx, pos, v for every car)", same,
                     "bitwise equal" if same else
                     f"max abs diff {np.abs(runs['base'] - runs['hetero_s0']).max():.3g}"))
    return all(ok)


T_RUN = 400   # seconds; long enough that a free IDM car sits on its desired speed


def _dispersion_run(sigma_v0):
    """Release 12 drivers (desired-speed spread sigma_v0, all other IDM params
    fixed) onto open road, each alone on its OWN segment so none follows another.
    Return the drawn drivers (sorted fastest-first) and their final speed/distance."""
    sig = {"v0": sigma_v0, "a_max": 0.0, "b_comf": 0.0, "T": 0.0, "s0": 0.0}
    drng = random.Random(2026)
    n = 12
    drv = sorted((drivers.sample(drng, sig) for _ in range(n)),
                 key=lambda d: d["v0_factor"], reverse=True)
    v0 = 50 * KPH                                    # 13.9 m/s limit
    # each car on a distinct edge (unique node pair) => its own by_edge group =>
    # no leader, no spillback: a genuinely free car that reaches exactly v0 * factor.
    vehs = [{"id": i, "route": [_edge(10 * i + 1, 10 * i + 2, 100_000.0, v0)],
             "idx": 0, "pos": 0.0, "v": 0.0, "idm": drv[i]} for i in range(n)]
    _run(vehs, _no_signals(), T_RUN)
    finals = np.array([veh["v"] for veh in vehs])       # final speed, fastest-first
    dists = np.array([veh["pos"] for veh in vehs])       # distance travelled (single edge)
    return drv, v0, finals, dists


def scenario_dispersion():
    print("\nB) DISPERSION: heterogeneous desired speeds fan the drivers out")
    print(f"   12 free drivers (desired-speed spread sigma_v0 = 0.12), released on")
    print(f"   open road for {T_RUN} s. Each must settle to v0 * its own drawn factor;")
    print("   predicted speeds are read from the draws, checkable by hand.")
    drv, v0, finals, dists = _dispersion_run(0.12)
    preds = np.array([v0 * d["v0_factor"] for d in drv])

    print(f"\n   {'rank':>4} {'v0 factor':>10} {'pred m/s':>9} {'actual m/s':>11} {'dist m':>9}")
    for i, d in enumerate(drv):
        print(f"   {i:>4} {d['v0_factor']:>10.4f} {preds[i]:>9.3f} "
              f"{finals[i]:>11.3f} {dists[i]:>9.0f}")

    max_err = float(np.abs(finals - preds).max())
    var_on = float(finals.var())
    span = float(dists.max() - dists.min())
    # hand-predicted separation: fastest and slowest differ by (Δfactor)*v0 in speed,
    # so after T_RUN s (bar an equal ~few-second warmup) they are ~that * T_RUN apart.
    span_pred = (drv[0]["v0_factor"] - drv[-1]["v0_factor"]) * v0 * T_RUN

    _, _, finals_off, dists_off = _dispersion_run(0.0)   # every factor 1.0
    var_off = float(finals_off.var())
    span_off = float(dists_off.max() - dists_off.min())

    ok = []
    ok.append(_check("each free driver reaches its predicted desired speed exactly",
                     max_err < 1e-6, f"largest speed error {max_err:.2e} m/s"))
    ok.append(_check("speeds fan out with heterogeneity (variance > 0)",
                     var_on > 0.5, f"final-speed variance {var_on:.3f} (m/s)^2"))
    ok.append(_check("final speeds are monotonic in the drawn factors",
                     bool(np.all(np.diff(finals) <= 1e-9)),
                     f"speeds fastest->slowest: {np.round(finals, 2).tolist()}"))
    ok.append(_check("fastest and slowest separate as hand-predicted",
                     abs(span - span_pred) < 0.03 * span_pred,
                     f"span {span:.0f} m vs predicted {span_pred:.0f} m "
                     f"({100*(span-span_pred)/span_pred:+.1f}%)"))
    ok.append(_check("zero dispersion leaves no spread (one speed, no separation)",
                     var_off < 1e-12 and span_off < 1e-6,
                     f"variance {var_off:.2e} (m/s)^2, span {span_off:.2e} m"))
    return all(ok)


def scenario_own_s0():
    print("\nC) THE CAR'S OWN s0 GOVERNS SEGMENT ENTRY")
    print("   A car crossing into a downstream segment holds at the stop line when")
    print("   the rearmost car there is closer than L + s0 (L = 5 m). That gap test")
    print("   must use the DRIVER'S OWN jam distance, the same s0 the acceleration")
    print("   pass gives it -- otherwise a short-headway driver is held out of a gap")
    print("   its own car-following would happily accept.")
    v0 = 50 * KPH
    # blocker sits at 6.8 m into the next segment: inside the default threshold
    # (5 + 2.0 = 7.0) but outside a short-headway driver's (5 + 1.6 = 6.6).
    blocker_pos = 6.8
    base_thr = config.VEHICLE_LENGTH_M + config.IDM_S0
    short_s0 = config.IDM_S0 * 0.8
    short_thr = config.VEHICLE_LENGTH_M + short_s0

    def crossed(idm):
        """One car at the very end of edge (1,2) with the blocker ahead on (2,3).
        Returns True if it entered the next segment this step."""
        mover = {"id": 0, "idx": 0, "pos": 399.9, "v": 5.0,
                 "route": [_edge(1, 2, 400.0, v0), _edge(2, 3, 600.0, v0)]}
        if idm is not None:
            mover["idm"] = idm
        blocker = {"id": 1, "idx": 0, "pos": blocker_pos, "v": 0.0,
                   "route": [_edge(2, 3, 600.0, v0)]}
        vehs = [mover, blocker]
        _run(vehs, _no_signals(), 1)
        return mover["idx"] == 1

    default_idm = {"v0_factor": 1.0, "a_max": config.IDM_A_MAX,
                   "b_comf": config.IDM_B_COMF, "T": config.IDM_T,
                   "s0": config.IDM_S0}
    print(f"\n   blocker at {blocker_pos} m; default threshold {base_thr:.1f} m, "
          f"short-headway (s0 {short_s0:.1f}) threshold {short_thr:.1f} m")
    ok = []
    ok.append(_check("flag-off car is held (unchanged base behavior)",
                     not crossed(None),
                     f"{blocker_pos} m < {base_thr:.1f} m, so it waits"))
    ok.append(_check("heterogeneous car with the DEFAULT s0 is held too",
                     not crossed(default_idm),
                     "same threshold, same outcome as the base kernel"))
    ok.append(_check("short-headway driver enters the gap the default refuses",
                     crossed(dict(default_idm, s0=short_s0)),
                     f"{blocker_pos} m > {short_thr:.1f} m, so it crosses"))
    return all(ok)


if __name__ == "__main__":
    print("Driver-heterogeneity scenarios  (real kernel, hand-checkable)")
    print("=" * 66)
    results = {"inertness": scenario_inertness(),
               "dispersion": scenario_dispersion(),
               "own_s0": scenario_own_s0()}
    print("\n" + "=" * 66)
    for name, okay in results.items():
        print(f"   {PASS if okay else FAIL}  {name}")
    n_pass = sum(results.values())
    print(f"\n{n_pass}/{len(results)} driver scenarios passed.")
    sys.exit(0 if n_pass == len(results) else 1)
