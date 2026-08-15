"""Rose Quarter I-5 SB closure at peak and quiet demand (pre-registered arm
B2, PREREG_I5_ROSEQUARTER.md Appendix B).

The primary campaign (fwrq, Appendix A) runs one steady-state hour at the
flat average demand of 16,500 vehicles. PORTAL records hourly volumes, so the
real closure will show a time-of-day shape the flat run cannot predict. This
campaign runs the SAME frozen closure at two demand levels, the same two
hours the day experiment already uses (chosen there, long before this
campaign existed): hour 8 (peak) and hour 1 (quiet), with demand
round(16500 * profile[h] * 24) from the PORTAL-derived hourly profile.

Design, fixed before any task runs (the registration is Appendix B):
- Arms: open vs rosequarter-closed, paired by seed, the frozen 5-edge span
  with the same in-task guard as fwrq (a task refuses a mismatched graph).
- Seeds: the standing block-1 set (8). 2 levels x 2 arms x 8 seeds = 32.
- Stack: BASE (all realism flags off), mixed fleet, matching the primary
  fwrq campaign so the only new variable is the demand level.
- Bar: per level, unanimity AND |t| > 3 on paired relative differences.
- Citation rule: quiet-hour route bases are small, so grams lead and a
  percentage is never cited alone.

Files: rqpq_{level}_{arm}_s{seed}. One simulated hour per task.

    python src/rosequarter_peak_quiet.py --check
    python src/rosequarter_peak_quiet.py --count
    python src/rosequarter_peak_quiet.py --list
    python src/rosequarter_peak_quiet.py --task N
    python src/rosequarter_peak_quiet.py --readout
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import generate        # noqa: E402
import demand_data     # noqa: E402
import freeway_rosequarter as fwrq  # noqa: E402  (span guard, seeds, routes)
from freeway_runs import SCENARIOS  # noqa: E402

PREFIX = "rqpq"
LEVELS = {"peak": 8, "quiet": 1}   # hour of day; see the docstring
SEEDS = fwrq.SEEDS
ARMS = fwrq.ARMS                   # ("open", "rosequarter")


def level_demand(level):
    """The day machinery's own demand for that hour: the same PORTAL-profile
    formula run_day_experiment uses, so a level reproduces that hour of the
    day experiment exactly."""
    profile = demand_data.hourly_demand_profile()
    return max(1, round(config.N_VEHICLES * profile[LEVELS[level]] * 24))


def tasks():
    return [(level, arm, seed) for level in LEVELS
            for arm in ARMS for seed in SEEDS]


def run_name(level, arm, seed):
    return f"{PREFIX}_{level}_{arm}_s{seed}"


def summary_path(level, arm, seed):
    return os.path.join(config.PROCESSED_DIR,
                        f"{run_name(level, arm, seed)}_summary.json")


def run_task(idx):
    level, arm, seed = tasks()[idx]
    out = summary_path(level, arm, seed)
    if os.path.exists(out):
        print(f"task {idx} ({level}, {arm}, seed {seed}) already done -> {out}")
        return

    G = fwrq._load_metro_graph()
    n_veh = level_demand(level)
    config.RANDOM_SEED = seed
    config.RUN_NAME = run_name(level, arm, seed)

    # BASE stack, every flag explicitly False (fwrq's F6 rule), mixed fleet
    # for absolute grams: identical configuration to the primary campaign so
    # the demand level is the only new variable.
    for k in fwrq.REALISM_FLAGS:
        setattr(config, k, False)
    config.FLEET_MIXED = True

    removed = []
    if arm != "open":
        removed = fwrq._verify_span(G)   # the frozen-span guard, every task
        generate.apply_freeway_closure(G, SCENARIOS[arm])
        print(f"[{config.RUN_NAME}] removed {len(removed)} freeway edges")

    generate.set_seeds(seed)
    totals, nox, thru = generate.run_simulation(G, n_vehicles=n_veh,
                                                use_checkpoint=False)
    generate.save_results(totals, nox, thru)

    routes = {}
    for ref in fwrq.TRACK_ROUTES:
        keys = generate.freeway_mainline_edges(G, ref)
        if not keys:
            continue
        routes[ref] = {f"{u}_{v}_{k}": [float(nox.get((u, v, k), 0.0)),
                                        float(thru.get((u, v, k), 0.0))]
                       for u, v, k in keys}
    rec = {
        "arm": arm, "seed": seed, "level": level, "hour": LEVELS[level],
        "stack": "base", "fleet": "mixed",
        "n_vehicles": n_veh, "n_steps": config.N_STEPS,
        "removed": [[u, v, k] for u, v, k in removed],
        "network_nox_g": float(sum(nox.values())),
        "network_throughput": float(sum(thru.values())),
        "routes": routes,
    }
    with open(out, "w") as f:
        json.dump(rec, f)
    print(f"[{config.RUN_NAME}] summary -> {out}")


def check():
    ok = True
    for level in LEVELS:
        print(f"  ok       {level}: hour {LEVELS[level]}, "
              f"demand {level_demand(level):,}")
    # the profile silently falls back to a synthetic shape without the real
    # PORTAL csv; profiled runs refuse that (the fwpq harness's lesson)
    if demand_data.is_using_real_data():
        print("  ok       PORTAL profile is the real csv, not synthetic")
    else:
        print("  REFUSE   demand profile would fall back to synthetic")
        ok = False
    try:
        G = fwrq._load_metro_graph()
        removed = fwrq._verify_span(G)
        print(f"  ok       frozen span verified: {len(removed)} edges")
    except SystemExit as e:
        print(f"  REFUSE   {e}")
        ok = False
    print(f"\n{'READY' if ok else 'NOT READY'}: {len(tasks())} hour jobs")
    return ok


def _load_level(level):
    """Summaries for one level, keyed (arm, seed) the way fwrq._paired wants."""
    summaries = {}
    for lv, arm, seed in tasks():
        if lv != level:
            continue
        p = summary_path(level, arm, seed)
        if not os.path.exists(p):
            continue
        with open(p) as f:
            rec = json.load(f)
        if rec.get("stack") != "base" or rec.get("level") != level:
            raise SystemExit(f"{p} records stack={rec.get('stack')} "
                             f"level={rec.get('level')}; wrong file")
        summaries[(arm, seed)] = rec
    return summaries


def readout():
    added_g = {}
    for level in LEVELS:
        summaries = _load_level(level)
        have = {a: sum(1 for (arm, _) in summaries if arm == a) for a in ARMS}
        print(f"\n{'=' * 72}\n{level.upper()} (hour {LEVELS[level]}, demand "
              f"{level_demand(level):,}): paired per-seed differences, "
              + ", ".join(f"{a} {have[a]}/{len(SEEDS)}" for a in ARMS)
              + f"\n{'=' * 72}")
        if min(have.values()) < 2:
            print("  not enough paired seeds yet")
            continue
        print(f"{'route':>8s} {'n':>3s} {'mean %':>8s} {'sd %':>7s} "
              f"{'mean g':>9s} {'signs':>7s}  verdict")
        for ref in fwrq.TRACK_ROUTES:
            d, rel = fwrq._paired(summaries, ref, 0)
            if len(d) < 2:
                continue
            pos = int((d > 0).sum())
            unanimous = pos == len(d) or pos == 0
            t = abs(rel.mean()) / (rel.std(ddof=1) / np.sqrt(len(rel))) \
                if rel.std(ddof=1) > 0 else float("inf")
            verdict = ("SUPPORTED" if unanimous and t > 3
                       else "weak" if unanimous else "NOT SUPPORTED")
            print(f"{ref:>8s} {len(d):3d} {rel.mean():+8.2f} "
                  f"{rel.std(ddof=1):7.2f} {d.mean():+9.0f} "
                  f"{pos:3d}/{len(d):<3d}  {verdict} (t={t:.1f})")
            if ref == "I 405":
                added_g[level] = d.mean()
    if len(added_g) == 2:
        ratio_g = added_g["peak"] / added_g["quiet"] if added_g["quiet"] else float("nan")
        ratio_n = level_demand("peak") / level_demand("quiet")
        print(f"\nREGISTERED CONTRAST: added I-405 NOx {added_g['peak']:+.0f} g "
              f"(peak) vs {added_g['quiet']:+.0f} g (quiet), ratio {ratio_g:.2f}; "
              f"demand ratio {ratio_n:.2f}. Super-proportional if the grams "
              f"ratio exceeds the demand ratio; either answer is reported.")
    print("\nCITATION RULE: grams lead; quiet-hour percentages are never "
          "cited alone (small bases).")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--count", action="store_true")
    g.add_argument("--list", action="store_true")
    g.add_argument("--task", type=int)
    g.add_argument("--readout", action="store_true")
    args = ap.parse_args()

    if args.count:
        print(len(tasks()))
    elif args.list:
        for i, (level, arm, seed) in enumerate(tasks()):
            print(f"{i:3d}  {level:6s} {arm:12s} seed {seed:<6} "
                  f"{run_name(level, arm, seed)}")
    elif args.check:
        raise SystemExit(0 if check() else 1)
    elif args.readout:
        readout()
    else:
        run_task(args.task)


if __name__ == "__main__":
    main()
