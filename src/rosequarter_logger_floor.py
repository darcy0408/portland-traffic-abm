"""Null floor + October scoring for the public travel-time logger (M.3 rule 5).

Appendix M registered the October protocol for grading the model's arterial
travel-time predictions against github.com/darcy0408/portland-traveltime-log.
Rule 5 requires a null floor measured from the logger's OWN pre-closure data,
scored exactly as October will be. This script is that instrument: ONE code
path computes a percent change in mean daytime travel_s per pair between two
day pools, and both the floor draws and the October before-vs-during run go
through it, so the floor and the graded number can never diverge in method.

Implementation choices pinned here, in code committed BEFORE this script has
ever run on logger data (mechanics verified by --selftest on synthetic rows):

  - status ok rows only; the graded quantity is travel_s per pair (M.3 rule 1).
  - Hours are assigned in Pacific time. The whole logging window (Aug 18 to
    the end of the up-to-5-week closure that starts Sept 11) sits inside
    Pacific DAYLIGHT time, so the conversion is a fixed UTC-7. The script
    REFUSES rows on or after 2026-11-01 (the DST change) rather than silently
    mislabeling hours.
  - Daytime rows only: 06:00 <= local hour < 20:00 (M.3 rule 2), 14 hourly
    slots per pair-day.
  - A pair-day with fewer than 12 of its 14 daytime hours ok is dropped and
    said so (Appendix J's 20-of-24 drop rule scaled to the daytime window).
    A pair with no usable day in one pool is unusable for that draw and
    reported, never silently skipped.
  - A pool's mean is the mean of travel_s over all ok daytime rows on usable
    pair-days; the change is (during - before) / before * 100.
  - The floor unit is the clean pre-closure Tue-Thu WEEK: all three days
    Tue-Thu, entirely before Sept 11, excluding Labor Day week (Sept 7-11).
    Every pairwise combination of clean weeks is scored. With three clean
    weeks the three draws share weeks and are NOT independent; that is
    printed wherever the floor is printed.
  - The FLOOR is the largest per-pair magnitude across all pairs and draws
    (one global floor, Appendix J style). Appendix J's a-priori 2x margin
    and tier wording apply verbatim at scoring time.
  - Day-level draws measure a different quantity than October's three-day
    pools (within-week pairs miss week-scale drift; single days across
    weeks average less), so they are NOT part of the floor. If ever
    printed, they are labeled diagnostic and never govern verdict wording.
  - Weekend rows are never part of the graded instrument or the floor:
    weekend traffic is pattern, not noise, and the model simulates an
    average weekday hour. Any weekend analysis is exploratory only.

Modes (all read-only on the logger clone):
  python src/rosequarter_logger_floor.py --selftest
  python src/rosequarter_logger_floor.py --floor [--log-dir PATH]
  python src/rosequarter_logger_floor.py --score --before D1 D2 D3 \
      --during D4 D5 D6 --floor-pct T [--log-dir PATH]
"""
import argparse
import csv
import glob
import os
from collections import defaultdict
from datetime import datetime, timedelta, date

CLOSURE_START = date(2026, 9, 11)     # I-5 SB closes; no clean week touches it
LABOR_DAY_WEEK = (date(2026, 9, 7), date(2026, 9, 13))  # excluded by M.3 rule 3
DST_END = date(2026, 11, 1)           # fixed UTC-7 is wrong from here on
PACIFIC_OFFSET = timedelta(hours=-7)  # PDT
DAY_START, DAY_END = 6, 20            # 06:00 <= local hour < 20:00
MIN_OK_HOURS = 12                     # of the 14 daytime slots, else drop day
TUE, THU = 1, 3                       # Monday = 0


def load_rows(log_dir):
    """All logger rows -> list of (local_date, local_hour, pair, travel_s).

    Applies M.3 rules 1-2 (status ok, daytime, Pacific hours) and the DST
    refusal. Everything else (day sets, drop rule) happens per pool.
    """
    rows = []
    files = sorted(glob.glob(os.path.join(log_dir, "data", "traveltimes_*.csv")))
    if not files:
        raise SystemExit(f"no traveltimes_*.csv under {log_dir}/data")
    for path in files:
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if r["status"] != "ok":
                    continue
                utc = datetime.strptime(r["utc"], "%Y-%m-%dT%H:%M:%SZ")
                local = utc + PACIFIC_OFFSET
                if local.date() >= DST_END:
                    raise SystemExit(
                        f"row at {r['utc']} is on/after {DST_END}: the fixed "
                        "UTC-7 conversion is invalid there, refusing")
                if not (DAY_START <= local.hour < DAY_END):
                    continue
                rows.append((local.date(), local.hour, r["pair"],
                             float(r["travel_s"])))
    return rows


def pool_means(rows, days):
    """Per-pair mean travel_s over the day pool, applying the drop rule.

    Returns (means, dropped): means[pair] = mean over ok daytime rows on
    usable pair-days; dropped = [(pair, day, n_ok), ...] for printing.
    """
    days = set(days)
    by_pair_day = defaultdict(list)
    for d, _h, pair, t in rows:
        if d in days:
            by_pair_day[(pair, d)].append(t)
    dropped, per_pair = [], defaultdict(list)
    for (pair, d), vals in sorted(by_pair_day.items()):
        if len(vals) < MIN_OK_HOURS:
            dropped.append((pair, d, len(vals)))
        else:
            per_pair[pair].extend(vals)
    means = {p: sum(v) / len(v) for p, v in per_pair.items()}
    return means, dropped


def score_pools(rows, before_days, during_days, label_a, label_b):
    """The shared scoring path: per-pair percent change, before vs during."""
    means_a, drop_a = pool_means(rows, before_days)
    means_b, drop_b = pool_means(rows, during_days)
    for pair, d, n in drop_a + drop_b:
        print(f"  DROPPED {pair} {d}: {n} of 14 daytime hours ok "
              f"(< {MIN_OK_HOURS})")
    changes = {}
    for pair in sorted(set(means_a) | set(means_b)):
        if pair not in means_a or pair not in means_b:
            missing_in = label_a if pair not in means_a else label_b
            print(f"  UNUSABLE {pair}: no usable day in {missing_in}")
            continue
        changes[pair] = (means_b[pair] - means_a[pair]) / means_a[pair] * 100.0
    return changes


def clean_weeks(rows):
    """Clean pre-closure Tue-Thu weeks present in the data, oldest first."""
    dates = sorted({d for d, _h, _p, _t in rows})
    by_week = defaultdict(set)
    for d in dates:
        if TUE <= d.weekday() <= THU:
            by_week[d.isocalendar()[:2]].add(d)
    weeks = []
    for wk in sorted(by_week):
        days = sorted(by_week[wk])
        if len(days) != 3:
            continue                       # partial week, not clean
        if days[-1] >= CLOSURE_START:
            continue                       # touches the closure
        if LABOR_DAY_WEEK[0] <= days[0] <= LABOR_DAY_WEEK[1]:
            continue                       # M.3 rule 3 exclusion
        weeks.append(days)
    return weeks


def fmt_week(days):
    return f"{days[0]}..{days[-1]}"


def run_floor(log_dir):
    rows = load_rows(log_dir)
    weeks = clean_weeks(rows)
    print(f"clean pre-closure Tue-Thu weeks: "
          f"{[fmt_week(w) for w in weeks] or 'NONE'}")
    if len(weeks) < 2:
        raise SystemExit("fewer than two clean weeks: no draws possible yet")
    print("NOTE: draws share weeks and are NOT independent "
          "(three weeks give three overlapping pairings).")
    print()
    global_max, control_max = 0.0, 0.0
    per_pair_max = defaultdict(float)
    for i in range(len(weeks)):
        for j in range(i + 1, len(weeks)):
            a, b = weeks[i], weeks[j]
            print(f"draw: {fmt_week(a)} vs {fmt_week(b)}")
            changes = score_pools(rows, a, b, fmt_week(a), fmt_week(b))
            for pair, c in sorted(changes.items(), key=lambda kv: -abs(kv[1])):
                print(f"  {pair:>14} {c:+7.2f}%")
                per_pair_max[pair] = max(per_pair_max[pair], abs(c))
                global_max = max(global_max, abs(c))
                if pair.startswith("ctrl_"):
                    control_max = max(control_max, abs(c))
            print()
    print("=" * 60)
    print("largest null magnitude per pair (across draws):")
    for pair, m in sorted(per_pair_max.items(), key=lambda kv: -kv[1]):
        print(f"  {pair:>14} {m:6.2f}%")
    print()
    print(f"FLOOR (largest per-pair magnitude, any pair, any draw): "
          f"{global_max:.2f}%")
    print(f"control pairs' largest magnitude: {control_max:.2f}%")
    print(f"tier thresholds with the a-priori 2x margin: within floor "
          f"<= {global_max:.2f}% < weak <= {2 * global_max:.2f}% < clear")
    return global_max


def run_score(log_dir, before, during, floor_pct):
    rows = load_rows(log_dir)
    b = [date.fromisoformat(d) for d in before]
    u = [date.fromisoformat(d) for d in during]
    print(f"before: {b}")
    print(f"during: {u}")
    print()
    changes = score_pools(rows, b, u, "before", "during")
    ranked = []
    for pair, c in sorted(changes.items(), key=lambda kv: -kv[1]):
        if abs(c) <= floor_pct:
            word = "within the measured null floor, no evidence either way"
        elif abs(c) <= 2 * floor_pct:
            word = "direction consistent, weak evidence"
        else:
            word = "clear of the null floor"
            ranked.append(pair)
        print(f"  {pair:>14} {c:+7.2f}%  {word}")
    print()
    print(f"rank of gains among pairs clear of the floor "
          f"(others take no rank): {ranked or 'NONE'}")


def selftest():
    """Mechanics check on synthetic rows with hand-computed answers."""
    import tempfile
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "data"))
    # Local 06:00 PDT = 13:00Z same day; local 20:00 PDT = 03:00Z next day.
    wk_a = [date(2026, 8, 18) + timedelta(days=k) for k in range(3)]
    wk_b = [date(2026, 8, 25) + timedelta(days=k) for k in range(3)]
    lines = ["utc,pair,travel_s,no_traffic_s,historic_s,delay_s,length_m,status"]

    def emit(d, hour_local, pair, travel, status="ok"):
        utc = datetime(d.year, d.month, d.day, hour_local) - PACIFIC_OFFSET
        lines.append(f"{utc:%Y-%m-%dT%H:%M:%SZ},{pair},{travel},0,0,0,0,{status}")

    for d in wk_a + wk_b:
        base = 1000 if d in wk_a else 1100        # synth_up: exactly +10%
        for h in range(DAY_START, DAY_END):
            emit(d, h, "synth_up", base)
        # synth_flat week A: the 06:00 boundary row on the first day is 814,
        # every other daytime row 800, so the week-A mean is hand-computable
        # and correct ONLY if the boundary row is included.
        for h in range(DAY_START, DAY_END):
            v = 814 if (d == wk_a[0] and h == DAY_START) else 800
            emit(d, h, "synth_flat", v)
        # poison rows, all of which the filters must exclude
        emit(d, 5, "synth_up", 99999)             # 05:xx local, pre-daytime
        emit(d, 20, "synth_up", 99999)            # 20:xx local, post-daytime
        emit(d, 12, "synth_up", 99999, status="error")
    emit(date(2026, 8, 17), 12, "synth_up", 99999)  # Monday, outside Tue-Thu
    # drop rule: synth_drop has only 5 ok daytime rows on the first Tuesday
    for h in range(DAY_START, DAY_START + 5):
        emit(wk_a[0], h, "synth_drop", 500)
    for d in wk_a[1:] + wk_b:
        for h in range(DAY_START, DAY_END):
            emit(d, h, "synth_drop", 500)
    with open(os.path.join(tmp, "data", "traveltimes_2026-08.csv"), "w") as f:
        f.write("\n".join(lines) + "\n")

    rows = load_rows(tmp)
    weeks = clean_weeks(rows)
    assert [w[0] for w in weeks] == [wk_a[0], wk_b[0]], f"weeks wrong: {weeks}"
    # the Monday poison row must not have created a partial fourth week
    assert all(len(w) == 3 for w in weeks)
    changes = score_pools(rows, wk_a, wk_b, "A", "B")
    assert abs(changes["synth_up"] - 10.0) < 1e-9, changes
    # week-A synth_flat mean: 41 rows at 800 plus the one boundary row at 814
    ma, _ = pool_means(rows, wk_a)
    expected = (41 * 800 + 814) / 42
    assert abs(ma["synth_flat"] - expected) < 1e-9, ma["synth_flat"]
    assert abs(changes["synth_flat"] - (800 - expected) / expected * 100) < 1e-9
    _, dropped = pool_means(rows, wk_a)
    assert ("synth_drop", wk_a[0], 5) in dropped, dropped
    assert abs(changes["synth_drop"] - 0.0) < 1e-9, changes
    # DST refusal: one November row must abort the whole load
    bad = os.path.join(tmp, "data", "traveltimes_2026-11.csv")
    with open(bad, "w") as f:
        f.write(lines[0] + "\n2026-11-02T15:00:04Z,synth_up,1000,0,0,0,0,ok\n")
    try:
        load_rows(tmp)
        raise AssertionError("DST refusal did not fire")
    except SystemExit:
        pass
    os.remove(bad)
    print("selftest PASS: filters, boundary hours, drop rule, week "
          "enumeration, the +10.0% change, and the DST refusal all check out")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--floor", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--before", nargs="+", metavar="DAY")
    ap.add_argument("--during", nargs="+", metavar="DAY")
    ap.add_argument("--floor-pct", type=float,
                    help="the measured floor T; wording tiers are T and 2T")
    ap.add_argument("--log-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        os.pardir, "portland-traveltime-log"))
    args = ap.parse_args()
    if args.selftest:
        selftest()
    elif args.floor:
        run_floor(args.log_dir)
    elif args.score:
        if not (args.before and args.during and args.floor_pct is not None):
            raise SystemExit("--score needs --before, --during, --floor-pct")
        run_score(args.log_dir, args.before, args.during, args.floor_pct)
    else:
        raise SystemExit("pick a mode: --selftest, --floor, or --score")


if __name__ == "__main__":
    main()
