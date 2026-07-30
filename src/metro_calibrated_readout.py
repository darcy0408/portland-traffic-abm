"""Read the metro calibrated-experiment runs and print the Phase 3 table.

Analysis-only (CLAUDE.md single-source-of-truth): reads the per-run
`data/processed/metrocal_*_summary.json` headline files that
src/metro_calibrated_experiment.py wrote (each computed from the graph that
run actually used, so no graph is needed here). Never runs a sim.

What it answers, per arm x demand, mean +/- SD over seeds:
  - VALIDATION, said plainly: busiest Powell segment veh/hr vs the real
    1,400-1,745 peak band (the corridor model never carried it; does metro?)
  - cars on the corridor: Powell vehicle-hours
  - cars stuck: vehicle-hours below 5 km/h (MEASURED by stuck_stats), Powell
    and network-wide
  - pollution: NOx grams, Powell and network total

Day runs (metrocal_day_*) are listed separately, per-run (no seed spread).
Smoke runs are excluded.

Run: python src/metro_calibrated_readout.py
"""
import glob
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

import config

REAL_BAND = (1400, 1745)   # Powell's real peak-hour band, veh/hr (PBOT counts)


def load_summaries():
    hour, day = [], []
    for path in sorted(glob.glob(os.path.join(config.PROCESSED_DIR,
                                              "metrocal_*_summary.json"))):
        with open(path) as f:
            s = json.load(f)
        if "smoke" in s["name"]:
            continue
        (day if s["name"].startswith("metrocal_day_") else hour).append(s)
    return hour, day


def _fmt(vals, unit="", width=8, prec=0):
    """mean +/- SD over seeds, or the single value when there is one run."""
    a = np.asarray(vals, dtype=float)
    if len(a) == 1:
        return f"{a[0]:{width}.{prec}f}{unit}"
    return f"{a.mean():{width}.{prec}f} +/- {a.std(ddof=1):.{prec}f}{unit}"


def hour_table(hour):
    if not hour:
        print("no hour-run summaries on disk yet.")
        return
    arms = sorted({s["arm"] for s in hour})
    demands = sorted({s["n_veh"] for s in hour})
    lo, hi = REAL_BAND
    print(f"=== hour runs: mean +/- SD over seeds "
          f"(real Powell peak band {lo:,}-{hi:,} veh/hr) ===")
    for arm in arms:
        for n in demands:
            grp = [s for s in hour if s["arm"] == arm and s["n_veh"] == n]
            if not grp:
                continue
            busiest = [s["busiest_powell_veh_hr"] for s in grp]
            mean_busiest = float(np.mean(busiest))
            verdict = ("IN the real band" if lo <= mean_busiest <= hi else
                       f"{'below' if mean_busiest < lo else 'above'} the real band")
            print(f"\n{arm:8s} n={n:,}  ({len(grp)} seeds)")
            print(f"   busiest Powell   {_fmt(busiest)} veh/hr  -> {verdict}")
            print(f"   Powell veh-h     {_fmt([s['powell_veh_h'] for s in grp], prec=1)}"
                  f"   (stuck {_fmt([s['powell_stuck_veh_h'] for s in grp], prec=1)})")
            print(f"   network stuck    {_fmt([s['network_stuck_veh_h'] for s in grp], prec=1)} veh-h")
            print(f"   NOx Powell       {_fmt([s['powell_nox_g'] for s in grp])} g"
                  f"   / total {_fmt([s['total_nox_g'] for s in grp])} g")


def day_table(day):
    if not day:
        return
    print("\n=== day runs (24 simulated hours; flat commute-shaped demand -- caveat) ===")
    for s in day:
        print(f"\n{s['name']}")
        print(f"   busiest Powell (per-hr avg) {s['busiest_powell_veh_hr']:8.0f} veh/hr")
        print(f"   Powell veh-h  {s['powell_veh_h']:10.1f}   "
              f"(stuck {s['powell_stuck_veh_h']:.1f})")
        print(f"   network stuck {s['network_stuck_veh_h']:10.1f} veh-h")
        print(f"   NOx Powell    {s['powell_nox_g']:10.0f} g / total {s['total_nox_g']:.0f} g")


def main():
    hour, day = load_summaries()
    print(f"{len(hour)} hour-run + {len(day)} day-run summaries in "
          f"{config.PROCESSED_DIR}\n")
    hour_table(hour)
    day_table(day)


if __name__ == "__main__":
    main()
