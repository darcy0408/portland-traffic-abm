"""Read the Phase A2 day runs and answer the day-scale question.

Analysis-only (CLAUDE.md single-source-of-truth): reads the four
`data/processed/metrocal_day{flat,prof}_{base,realism}_*_summary.json` files
that src/metro_calibrated_experiment.py wrote on Orca (array 117428). Never
runs a sim.

THE QUESTION A2 WAS BUILT TO ANSWER (from REAL_DEMAND_UPGRADE_PLAN.md): over a
24-hour run, does stuck time RECOVER after the morning peak or ratchet all day,
and do the base and realism arms differ? The stated success criterion for the
profiled arms was PM-peak stuck roughly equal to AM-peak stuck.

The arrays are indexed by ELAPSED hour, not wrapped clock hour, so a multi-day
run would show ratcheting rather than averaging it away. Hour 0 of the run is
`stuck_hour_start` on the clock (0 for all four of these runs, so elapsed hour
== clock hour here and the PORTAL curve lines up directly).

Four arms = {flat, profiled} demand x {base, realism stack}. The flat pair is
the control: it re-runs the Jul 29 configuration with hour bucketing on, so a
bit-level match against the Jul 29 whole-run totals proves the bucketing
perturbs nothing. That check runs first and is fatal if it fails.

Run: python src/day_readout.py
"""
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import demand_data

ARMS = ["dayflat_base", "dayflat_realism", "dayprof_base", "dayprof_realism"]
LABELS = {"dayflat_base": "flat/base", "dayflat_realism": "flat/realism",
          "dayprof_base": "prof/base", "dayprof_realism": "prof/realism"}
# The Jul 29 whole-run day pair, same config as the flat arms minus bucketing.
CONTROL = {"dayflat_base": "day_base", "dayflat_realism": "day_realism"}
# Whole-run totals that bucketing must not have moved. Floats compare exactly:
# the claim is bit-level identity, so a tolerance would hide the failure.
CONTROL_KEYS = ["busiest_powell_veh_hr", "powell_veh_h", "powell_stuck_veh_h",
                "network_stuck_veh_h", "powell_nox_g", "total_nox_g"]


def load(stem):
    path = os.path.join(config.PROCESSED_DIR,
                        f"metrocal_{stem}_n16500_s42_summary.json")
    with open(path) as f:
        return json.load(f)


def check_control(runs):
    """The flat arms must reproduce the Jul 29 day runs exactly."""
    print("CONTROL: flat arms vs the Jul 29 day runs (bucketing must be inert)")
    ok = True
    for stem, ctrl_stem in CONTROL.items():
        try:
            ctrl = load(ctrl_stem)
        except FileNotFoundError:
            print(f"  {LABELS[stem]:14s} SKIP  {ctrl_stem} not on disk")
            continue
        bad = [k for k in CONTROL_KEYS if runs[stem][k] != ctrl[k]]
        ok &= not bad
        print(f"  {LABELS[stem]:14s} "
              + ("MATCH (all %d totals bit-identical)" % len(CONTROL_KEYS)
                 if not bad else "DRIFT on " + ", ".join(bad)))
    if not ok:
        raise SystemExit("control drifted: hour bucketing changed a total, so "
                         "these hourly arrays describe a different run than "
                         "the Jul 29 pair. Stop and diagnose before reading on.")
    print()


def hourly_table(runs, key, title):
    print(title)
    print(f"{'h':>3} " + " ".join(f"{LABELS[a]:>13}" for a in ARMS))
    for h in range(24):
        print(f"{h:>3} " + " ".join(f"{runs[a][key][h]:13.1f}" for a in ARMS))
    print()


def _quota():
    m = list(demand_data.hourly_demand_profile())
    peak = max(m)
    return [round(config.N_VEHICLES * x / peak) for x in m]


def shape(runs):
    """Does stuck time recover after the morning peak?

    A raw PM/AM ratio is not enough to answer this and reading one alone would
    mislead in BOTH directions here. Under flat demand there is no morning peak
    to recover from - those arms are saturated from hour 0, so any ratio near 1
    means "uniformly jammed all day", not "recovered". Under the profile the
    fleet is SUPPOSED to shrink in the evening, so an absolute stuck count that
    merely stops rising can still be total gridlock relative to the handful of
    vehicles the curve asked for. So flat arms are judged on whether they were
    ever quiet, and profiled arms on stuck-per-quota-vehicle: the overnight
    value is the model's own free-flow reference, and recovery means returning
    to it.
    """
    quota = _quota()
    print("SHAPE: does stuck time recover after the morning peak?")
    print(f"{'arm':14} {'peak':>12} {'min after':>12} {'final hour':>12} "
          f"{'final/quota':>12} {'overnight':>10}  verdict")
    for a in ARMS:
        v = runs[a]["network_stuck_veh_h_by_hour"]
        flat = "flat" in a
        pk_h = max(range(24), key=lambda h: v[h])
        mid_h = min(range(min(pk_h + 1, 23), 24), key=lambda h: v[h])
        # Free-flow reference: stuck per active vehicle in the quiet small hours.
        overnight = min(v[h] / quota[h] for h in range(0, 4))
        final_q = v[23] / quota[23]
        if flat:
            # No peak exists under flat demand; the question is whether the
            # network was EVER uncongested. It is not, from hour 0 onward.
            verdict = ("saturated from h0" if v[0] / config.N_VEHICLES > 0.20
                       else "quiet start")
        else:
            verdict = ("recovers" if final_q <= overnight * 3 else
                       "no recovery - gridlocked")
        print(f"{LABELS[a]:14} {v[pk_h]:9.1f}@h{pk_h:<2} {v[mid_h]:9.1f}@h{mid_h:<2} "
              f"{v[23]:12.1f} {final_q:11.2f}x {overnight:10.2f}x  {verdict}")
    print()


def crossover(runs):
    """Realism starts ahead and ends behind; find the hour it flips."""
    print("CROSSOVER: hour at which realism stops beating base")
    for flat in (True, False):
        b = runs["dayflat_base" if flat else "dayprof_base"]
        r = runs["dayflat_realism" if flat else "dayprof_realism"]
        bv = b["network_stuck_veh_h_by_hour"]
        rv = r["network_stuck_veh_h_by_hour"]
        flip = next((h for h in range(24) if rv[h] > bv[h]), None)
        tag = "flat" if flat else "profiled"
        if flip is None:
            print(f"  {tag:9} realism never exceeds base")
            continue
        print(f"  {tag:9} realism < base for h0-h{flip - 1}, > base from h{flip} on "
              f"| h0 {rv[0]:.0f} vs {bv[0]:.0f}, h23 {rv[23]:.0f} vs {bv[23]:.0f}")
    print()


def quota_freeze(runs):
    """The profile can only shed vehicles when trips COMPLETE (see A1's design).

    If the network gridlocks, nothing completes, so the fleet cannot park down
    to the falling evening quota. Comparing the frozen stuck count against the
    quota the PORTAL curve asked for measures how far the ebb mechanism failed.
    """
    m = list(demand_data.hourly_demand_profile())
    peak = max(m)
    quota = [round(config.N_VEHICLES * x / peak) for x in m]
    print("EBB FAILURE: profiled arms vs the fleet quota the PORTAL curve asked for")
    print(f"{'h':>3} {'quota':>7} " +
          " ".join(f"{LABELS[a]:>24}" for a in ARMS[2:]))
    for h in range(16, 24):
        cells = []
        for a in ARMS[2:]:
            v = runs[a]["network_stuck_veh_h_by_hour"][h]
            cells.append(f"{v:11.1f} ({v / quota[h]:4.1f}x quota)")
        print(f"{h:>3} {quota[h]:>7} " + " ".join(cells))
    print()


def powell_vs_network(runs):
    """Powell can be quiet because it is flowing or because it is starved."""
    print("POWELL vs NETWORK: is a quiet Powell flowing, or starved?")
    print(f"{'arm':14} {'Powell veh-h':>13} {'Powell stuck':>13} "
          f"{'stuck share':>12} {'net stuck':>11} {'last Powell h':>14}")
    for a in ARMS:
        s = runs[a]
        pv, ps = s["powell_veh_h"], s["powell_stuck_veh_h"]
        arr = s["powell_stuck_veh_h_by_hour"]
        last = next((h for h in range(23, -1, -1) if arr[h] > 0.05), None)
        print(f"{LABELS[a]:14} {pv:13.1f} {ps:13.1f} {ps / pv:11.1%} "
              f"{s['network_stuck_veh_h']:11.0f} "
              f"{('h' + str(last)) if last is not None else 'never':>14}")
    print()


def totals(runs):
    print("WHOLE-DAY TOTALS")
    print(f"{'arm':14} {'net stuck veh-h':>16} {'share of fleet-day':>19} "
          f"{'total NOx kg':>13}")
    fleet_day = config.N_VEHICLES * 24
    for a in ARMS:
        s = runs[a]
        print(f"{LABELS[a]:14} {s['network_stuck_veh_h']:16.0f} "
              f"{s['network_stuck_veh_h'] / fleet_day:18.1%} "
              f"{s['total_nox_g'] / 1000:13.1f}")
    print()


def main():
    runs = {a: load(a) for a in ARMS}
    for a in ARMS:
        assert runs[a]["stuck_hour_start"] == 0, "elapsed != clock hour here"
    print("Phase A2 day readout - metro 20 km, 16,500 veh, seed 42, 86,400 steps")
    print("Orca array 117428, 4/4 COMPLETED\n")
    check_control(runs)
    totals(runs)
    shape(runs)
    crossover(runs)
    quota_freeze(runs)
    powell_vs_network(runs)
    hourly_table(runs, "network_stuck_veh_h_by_hour",
                 "NETWORK stuck veh-h by elapsed hour")
    hourly_table(runs, "powell_stuck_veh_h_by_hour",
                 "POWELL stuck veh-h by elapsed hour")


if __name__ == "__main__":
    main()
