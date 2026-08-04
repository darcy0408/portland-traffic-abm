"""Read a day-scale run set and answer the day-scale question.

Analysis-only (CLAUDE.md single-source-of-truth): reads the
`data/processed/*_summary.json` files that the experiment harnesses wrote on
Orca. Never runs a sim.

THE QUESTION (from REAL_DEMAND_UPGRADE_PLAN.md): over a 24-hour run, does stuck
time RECOVER after the morning peak or ratchet all day, and do the arms differ?
The stated success criterion for a profiled arm was PM-peak stuck roughly equal
to AM-peak stuck.

The arrays are indexed by ELAPSED hour, not wrapped clock hour, so a multi-day
run would show ratcheting rather than averaging it away. Hour 0 of the run is
`stuck_hour_start` on the clock (0 for every run read here, so elapsed hour ==
clock hour and the PORTAL curve lines up directly).

RUN SETS. This started life hardcoded to Phase A2's four arm names, which meant
Phase C1's day pair could not get the quota-aware verdict A2 was judged on. A
set is now DECLARED data, because the two things this readout needs to know
about a run -- whether its demand is profiled, and which other run it pairs
against -- cannot be sniffed safely from a file name.

    python src/day_readout.py                # Phase A2, the original four arms
    python src/day_readout.py --runs c1      # Phase C1, rerouting vs its control
    python src/day_readout.py --list         # what each set expects on disk

Adding a set is a literal entry in RUN_SETS below.
"""
import argparse
import collections
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import demand_data

# stem      full RUN_NAME, i.e. the summary file minus _summary.json
# group     runs that are variants of one another (flat vs prof, ctrl vs C1)
# stack     "base" or "realism"; crossover pairs these WITHIN a group
# profiled  demand follows the PORTAL hourly curve, so the fleet is meant to ebb
Run = collections.namedtuple("Run", "stem label group stack profiled")

SUF = "n16500_s42"       # every day run so far: 16,500 vehicles, the pinned seed

RUN_SETS = {
    "a2": {
        "title": ("Phase A2 day readout - metro 20 km, 16,500 veh, seed 42, "
                  "86,400 steps\nOrca array 117428, 4/4 COMPLETED"),
        "runs": [
            Run(f"metrocal_dayflat_base_{SUF}", "flat/base", "flat", "base", False),
            Run(f"metrocal_dayflat_realism_{SUF}", "flat/realism", "flat", "realism", False),
            Run(f"metrocal_dayprof_base_{SUF}", "prof/base", "profiled", "base", True),
            Run(f"metrocal_dayprof_realism_{SUF}", "prof/realism", "profiled", "realism", True),
        ],
        # the flat arms re-run the Jul 29 configuration with hour bucketing ON,
        # so a bit-level match proves the bucketing perturbs nothing
        "controls": {f"metrocal_dayflat_base_{SUF}": f"metrocal_day_base_{SUF}",
                     f"metrocal_dayflat_realism_{SUF}": f"metrocal_day_realism_{SUF}"},
        "pairs": [],
    },
    "c1": {
        "title": ("Phase C1 day readout - en-route rerouting vs the A2 profiled "
                  "pair\nmetro 20 km, 16,500 veh, seed 42, 86,400 steps; Orca "
                  "array 117851"),
        "runs": [
            Run(f"metrocal_dayprof_base_{SUF}", "ctrl/base", "control", "base", True),
            Run(f"metrocal_dayprof_realism_{SUF}", "ctrl/realism", "control", "realism", True),
            Run(f"c1_dayprof_base_reroute_{SUF}", "C1/base", "reroute", "base", True),
            Run(f"c1_dayprof_realism_reroute_{SUF}", "C1/realism", "reroute", "realism", True),
        ],
        # the controls ARE A2's profiled arms, already checked by the a2 set;
        # re-verifying the same files against themselves would prove nothing
        "controls": {},
        "pairs": [(f"metrocal_dayprof_base_{SUF}", f"c1_dayprof_base_reroute_{SUF}"),
                  (f"metrocal_dayprof_realism_{SUF}", f"c1_dayprof_realism_reroute_{SUF}")],
    },
    # REROUTE_STUCK_S sensitivity (src/metro_c1_sweep.py). The C1 day verdict --
    # freeze clears, stuck time down 84.7% -- currently rests on a 120 s driver-
    # patience constant with no direct source, so this asks whether the VERDICT is
    # stable across a plausible range or is an artifact of that one value. Every
    # arm is the realism stack with rerouting on; only the patience differs, so a
    # difference between rows cannot be anything else. The 120 s row is the
    # already-run C1 arm joined from disk, not a re-run.
    "c1sweep": {
        "title": ("C1 REROUTE_STUCK_S sweep - does the cleared freeze survive a "
                  "different\ndriver patience? metro 20 km, 16,500 veh, seed 42, "
                  "86,400 steps, realism stack"),
        "runs": [
            Run(f"metrocal_dayprof_realism_{SUF}", "ctrl/no-reroute", "control", "realism", True),
            Run(f"c1sw_dayprof_p30_{SUF}", "30 s", "p30", "realism", True),
            Run(f"c1sw_dayprof_p60_{SUF}", "60 s", "p60", "realism", True),
            Run(f"c1_dayprof_realism_reroute_{SUF}", "120 s (a-priori)", "p120", "realism", True),
            Run(f"c1sw_dayprof_p240_{SUF}", "240 s", "p240", "realism", True),
            Run(f"c1sw_dayprof_p480_{SUF}", "480 s", "p480", "realism", True),
        ],
        # same control files as the c1 set, already checked by the a2 set
        "controls": {},
        # every patience pairs against the SAME no-reroute control, so the rows
        # are directly comparable to one another as well as to the control
        "pairs": [(f"metrocal_dayprof_realism_{SUF}", f"c1sw_dayprof_p30_{SUF}"),
                  (f"metrocal_dayprof_realism_{SUF}", f"c1sw_dayprof_p60_{SUF}"),
                  (f"metrocal_dayprof_realism_{SUF}", f"c1_dayprof_realism_reroute_{SUF}"),
                  (f"metrocal_dayprof_realism_{SUF}", f"c1sw_dayprof_p240_{SUF}"),
                  (f"metrocal_dayprof_realism_{SUF}", f"c1sw_dayprof_p480_{SUF}")],
    },
}

# Whole-run totals that hour bucketing must not have moved. Floats compare
# exactly: the claim is bit-level identity, so a tolerance would hide a failure.
CONTROL_KEYS = ["busiest_powell_veh_hr", "powell_veh_h", "powell_stuck_veh_h",
                "network_stuck_veh_h", "powell_nox_g", "total_nox_g"]


def load(stem):
    """Summary for a full RUN_NAME, or None if that run is not on disk yet."""
    path = os.path.join(config.PROCESSED_DIR, f"{stem}_summary.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def check_control(runs, spec, lab):
    """Declared control runs must be reproduced exactly."""
    if not spec["controls"]:
        return
    print("CONTROL: bucketed arms vs their unbucketed originals "
          "(bucketing must be inert)")
    ok = True
    for stem, ctrl_stem in spec["controls"].items():
        ctrl = load(ctrl_stem)
        if ctrl is None:
            print(f"  {lab[stem]:14s} SKIP  {ctrl_stem} not on disk")
            continue
        bad = [k for k in CONTROL_KEYS if runs[stem][k] != ctrl[k]]
        ok &= not bad
        print(f"  {lab[stem]:14s} "
              + ("MATCH (all %d totals bit-identical)" % len(CONTROL_KEYS)
                 if not bad else "DRIFT on " + ", ".join(bad)))
    if not ok:
        raise SystemExit("control drifted: hour bucketing changed a total, so "
                         "these hourly arrays describe a different run than "
                         "the original. Stop and diagnose before reading on.")
    print()


def _quota(n_veh):
    """Active-fleet quota per hour that the PORTAL curve asks for (see A1).

    REFUSES if the real PORTAL sample is absent. `hourly_demand_profile()` falls
    back to a synthetic shape without saying so, and that fallback is close
    enough to look right while being wrong: it puts hour 23's quota at 2,829
    against the real curve's 2,876, so every "x quota" verdict below would shift
    by about 1.7% and silently stop matching the recorded A2 numbers. The file
    is gitignored, so a fresh worktree or clone never has it -- which is exactly
    how this was found. Same refusal the C1 harness's --check already makes.
    """
    if not os.path.exists(demand_data._DEFAULT_CSV):
        raise SystemExit(
            f"PORTAL sample missing at {demand_data._DEFAULT_CSV}\n"
            f"hourly_demand_profile() would fall back to a SYNTHETIC curve and "
            f"every quota\nverdict here would be quietly wrong. Copy it in:\n"
            f"  cp <other worktree>/data/portal_powell_sample.csv "
            f"{os.path.dirname(demand_data._DEFAULT_CSV)}/")
    m = list(demand_data.hourly_demand_profile())
    peak = max(m)
    return [round(n_veh * x / peak) for x in m]


def _deadlock_hours(v):
    """Hours whose stuck veh-h is an exact integer.

    A2's freeze showed up this way: when every active vehicle is stuck for all
    3,600 seconds of an hour, the vehicle-hour total lands on a whole number.
    A HEURISTIC flag, not proof -- a value can be integral by coincidence --
    so it is reported as a count to look at, never used as a verdict.
    """
    return [h for h in range(24) if abs(v[h] - round(v[h])) < 1e-6]


def hourly_table(runs, order, lab, key, title):
    print(title)
    print(f"{'h':>3} " + " ".join(f"{lab[s]:>13}" for s in order))
    for h in range(24):
        print(f"{h:>3} " + " ".join(f"{runs[s][key][h]:13.1f}" for s in order))
    print()


def shape(runs, spec, lab, quota, n_veh):
    """Does stuck time recover after the morning peak?

    A raw PM/AM ratio is not enough to answer this and reading one alone would
    mislead in BOTH directions. Under flat demand there is no morning peak to
    recover from - those arms are saturated from hour 0, so any ratio near 1
    means "uniformly jammed all day", not "recovered". Under the profile the
    fleet is SUPPOSED to shrink in the evening, so an absolute stuck count that
    merely stops rising can still be total gridlock relative to the handful of
    vehicles the curve asked for. So flat arms are judged on whether they were
    ever quiet, and profiled arms on stuck-per-quota-vehicle: the overnight
    value is the model's own free-flow reference, and recovery means returning
    to it.
    """
    print("SHAPE: does stuck time recover after the morning peak?")
    print(f"{'arm':14} {'peak':>12} {'min after':>12} {'final hour':>12} "
          f"{'final/quota':>12} {'overnight':>10}  verdict")
    for r in spec["runs"]:
        if r.stem not in runs:
            continue
        v = runs[r.stem]["network_stuck_veh_h_by_hour"]
        pk_h = max(range(24), key=lambda h: v[h])
        mid_h = min(range(min(pk_h + 1, 23), 24), key=lambda h: v[h])
        # Free-flow reference: stuck per active vehicle in the quiet small hours.
        overnight = min(v[h] / quota[h] for h in range(0, 4))
        final_q = v[23] / quota[23]
        if not r.profiled:
            # No peak exists under flat demand; the question is whether the
            # network was EVER uncongested.
            verdict = ("saturated from h0" if v[0] / n_veh > 0.20
                       else "quiet start")
        else:
            verdict = ("recovers" if final_q <= overnight * 3 else
                       "no recovery - gridlocked")
        print(f"{r.label:14} {v[pk_h]:9.1f}@h{pk_h:<2} {v[mid_h]:9.1f}@h{mid_h:<2} "
              f"{v[23]:12.1f} {final_q:11.2f}x {overnight:10.2f}x  {verdict}")
    print()


def crossover(runs, spec, lab):
    """Realism starts ahead and ends behind; find the hour it flips."""
    print("CROSSOVER: hour at which realism stops beating base")
    groups = []
    for r in spec["runs"]:
        if r.group not in groups:
            groups.append(r.group)
    for g in groups:
        pick = {r.stack: r.stem for r in spec["runs"]
                if r.group == g and r.stem in runs}
        if "base" not in pick or "realism" not in pick:
            print(f"  {g:9} incomplete pair, skipped")
            continue
        bv = runs[pick["base"]]["network_stuck_veh_h_by_hour"]
        rv = runs[pick["realism"]]["network_stuck_veh_h_by_hour"]
        flip = next((h for h in range(24) if rv[h] > bv[h]), None)
        if flip is None:
            print(f"  {g:9} realism never exceeds base")
            continue
        print(f"  {g:9} realism < base for h0-h{flip - 1}, > base from h{flip} on "
              f"| h0 {rv[0]:.0f} vs {bv[0]:.0f}, h23 {rv[23]:.0f} vs {bv[23]:.0f}")
    print()


def quota_freeze(runs, spec, quota):
    """The profile can only shed vehicles when trips COMPLETE (see A1's design).

    If the network gridlocks, nothing completes, so the fleet cannot park down
    to the falling evening quota. Comparing the frozen stuck count against the
    quota the PORTAL curve asked for measures how far the ebb mechanism failed.
    """
    prof = [r for r in spec["runs"] if r.profiled and r.stem in runs]
    if not prof:
        return
    print("EBB FAILURE: profiled arms vs the fleet quota the PORTAL curve asked for")
    print(f"{'h':>3} {'quota':>7} " + " ".join(f"{r.label:>24}" for r in prof))
    for h in range(16, 24):
        cells = []
        for r in prof:
            v = runs[r.stem]["network_stuck_veh_h_by_hour"][h]
            cells.append(f"{v:11.1f} ({v / quota[h]:4.1f}x quota)")
        print(f"{h:>3} {quota[h]:>7} " + " ".join(cells))
    print()


def paired(runs, spec, lab, quota):
    """Treatment vs its control, hour by hour. The C1 question lives here.

    Read a CLEARED freeze as the treated arm's stuck time falling TOWARD the
    quota, not merely as a whole-day total that moved: a run can shed a large
    absolute number of stuck vehicle-hours and still end the day deadlocked.
    """
    live = [(c, t) for c, t in spec["pairs"] if c in runs and t in runs]
    if not live:
        return
    print("PAIRED: treatment vs control by elapsed hour (network stuck veh-h)")
    for ctrl_stem, treat_stem in live:
        cv = runs[ctrl_stem]["network_stuck_veh_h_by_hour"]
        tv = runs[treat_stem]["network_stuck_veh_h_by_hour"]
        print(f"\n  {lab[treat_stem]} vs {lab[ctrl_stem]}")
        print(f"  {'h':>3} {'quota':>7} {'control':>12} {'x q':>7} "
              f"{'treated':>12} {'x q':>7} {'delta':>12} {'pct':>8}")
        for h in range(24):
            pct = 100 * (tv[h] - cv[h]) / cv[h] if cv[h] else float("nan")
            print(f"  {h:>3} {quota[h]:>7} {cv[h]:12.1f} {cv[h] / quota[h]:6.1f}x "
                  f"{tv[h]:12.1f} {tv[h] / quota[h]:6.1f}x "
                  f"{tv[h] - cv[h]:+12.1f} {pct:+7.1f}%")
        c_tot = runs[ctrl_stem]["network_stuck_veh_h"]
        t_tot = runs[treat_stem]["network_stuck_veh_h"]
        print(f"  {'all':>3} {'':>7} {c_tot:12.1f} {'':>7} {t_tot:12.1f} {'':>7} "
              f"{t_tot - c_tot:+12.1f} "
              f"{100 * (t_tot - c_tot) / c_tot:+7.1f}%")
        cd, td = _deadlock_hours(cv), _deadlock_hours(tv)
        print(f"  integral-valued hours (deadlock flag, heuristic): "
              f"control {len(cd)} {cd if cd else ''}, treated {len(td)} "
              f"{td if td else ''}")
        # the verdict the plan pre-registered: h23 falling toward quota
        print(f"  h23 vs quota {quota[23]}: control {cv[23] / quota[23]:.1f}x -> "
              f"treated {tv[23] / quota[23]:.1f}x")
    print()


def powell_vs_network(runs, spec, lab):
    """Powell can be quiet because it is flowing or because it is starved."""
    print("POWELL vs NETWORK: is a quiet Powell flowing, or starved?")
    print(f"{'arm':14} {'Powell veh-h':>13} {'Powell stuck':>13} "
          f"{'stuck share':>12} {'net stuck':>11} {'last Powell h':>14}")
    for r in spec["runs"]:
        if r.stem not in runs:
            continue
        s = runs[r.stem]
        pv, ps = s["powell_veh_h"], s["powell_stuck_veh_h"]
        arr = s["powell_stuck_veh_h_by_hour"]
        last = next((h for h in range(23, -1, -1) if arr[h] > 0.05), None)
        print(f"{r.label:14} {pv:13.1f} {ps:13.1f} {ps / pv:11.1%} "
              f"{s['network_stuck_veh_h']:11.0f} "
              f"{('h' + str(last)) if last is not None else 'never':>14}")
    print()


def totals(runs, spec, n_veh):
    print("WHOLE-DAY TOTALS")
    print(f"{'arm':14} {'net stuck veh-h':>16} {'share of fleet-day':>19} "
          f"{'total NOx kg':>13}")
    fleet_day = n_veh * 24
    for r in spec["runs"]:
        if r.stem not in runs:
            continue
        s = runs[r.stem]
        print(f"{r.label:14} {s['network_stuck_veh_h']:16.0f} "
              f"{s['network_stuck_veh_h'] / fleet_day:18.1%} "
              f"{s['total_nox_g'] / 1000:13.1f}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="a2", choices=sorted(RUN_SETS),
                    help="which declared run set to read (default: a2)")
    ap.add_argument("--list", action="store_true",
                    help="show the runs each set expects and whether they exist")
    args = ap.parse_args()

    if args.list:
        for name, spec in sorted(RUN_SETS.items()):
            print(f"\n{name}:")
            for r in spec["runs"]:
                mark = "ok     " if load(r.stem) else "MISSING"
                print(f"  {mark} {r.label:14} {r.stem}")
        return

    spec = RUN_SETS[args.runs]
    lab = {r.stem: r.label for r in spec["runs"]}
    runs = {r.stem: s for r in spec["runs"] if (s := load(r.stem)) is not None}

    missing = [r for r in spec["runs"] if r.stem not in runs]
    if missing:
        print("NOT ON DISK YET:")
        for r in missing:
            print(f"  {r.label:14} {r.stem}_summary.json")
        print()
    if not runs:
        raise SystemExit(f"no runs of set '{args.runs}' are on disk")

    # elapsed hour == clock hour only when the run started at midnight, and the
    # PORTAL curve is lined up on that assumption throughout
    for stem, s in runs.items():
        assert s["stuck_hour_start"] == 0, f"{stem}: elapsed != clock hour"
    # the quota is derived from the fleet the RUNS used, not from whatever
    # config.N_VEHICLES happens to be set to when the readout is invoked
    fleets = {s["n_veh"] for s in runs.values()}
    assert len(fleets) == 1, f"runs disagree on fleet size: {fleets}"
    n_veh = fleets.pop()
    quota = _quota(n_veh)

    print(spec["title"] + "\n")
    check_control(runs, spec, lab)
    totals(runs, spec, n_veh)
    shape(runs, spec, lab, quota, n_veh)
    crossover(runs, spec, lab)
    quota_freeze(runs, spec, quota)
    paired(runs, spec, lab, quota)
    powell_vs_network(runs, spec, lab)
    order = [r.stem for r in spec["runs"] if r.stem in runs]
    hourly_table(runs, order, lab, "network_stuck_veh_h_by_hour",
                 "NETWORK stuck veh-h by elapsed hour")
    hourly_table(runs, order, lab, "powell_stuck_veh_h_by_hour",
                 "POWELL stuck veh-h by elapsed hour")


if __name__ == "__main__":
    main()
