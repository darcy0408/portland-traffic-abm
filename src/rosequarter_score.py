"""Score the Rose Quarter closure predictions against real PORTAL volumes.

This is the October scoring pipeline for PREREG_I5_ROSEQUARTER.md section 5,
built and committed BEFORE the Sept 11 closure so every implementation choice
(aggregation window, detector handling, day sets) is pinned in advance, not
picked after seeing closure data. The registered rules it implements:

  1. Direction of change per corridor group, before vs during.
  2. Rank of relative gains across the detour corridors (I-405 vs I-205).
  3. Never absolute volumes against the model: each station is compared
     against ITSELF (before vs during), because model demand is fixed and
     cannot evaporate, shift in time, or change mode.
  4. Mainline 2DS stations only, the frozen 13-station set.

Implementation choices pinned here, before any closure data exists:
  - A station's DAILY VOLUME is the sum of hourly volumes across its
    detectors. The closure is 24/7, so the full day is the honest window.
  - Only detectors that report in BOTH periods count, so a detector dying
    between periods cannot masquerade as a traffic change.
  - A station-day with fewer than 20 of 24 hours reporting is dropped and
    said so. A frozen station with no usable data in either period is
    reported as unusable, per the prereg's drop rule (re-run the coverage
    check on pre-closure data, never on closure data).
  - A corridor group's change is the MEAN of its stations' relative changes;
    per-station values are always printed alongside so the mean hides
    nothing.

Modes (all read-only; API responses cached under data/portal_rq/):
  python src/rosequarter_score.py --coverage 2026-08-11 2026-08-12
      Coverage check: which frozen stations report on those days.
  python src/rosequarter_score.py --null
      Dress rehearsal: scores Aug 11-13 (Tue-Thu) against Aug 4-6 (Tue-Thu),
      two ordinary pre-closure weeks. Expectation: small changes, no
      consistent direction, rank meaningless. This validates the pipeline
      mechanics, not the model.
  python src/rosequarter_score.py --score --before D1 D2 D3 --during D4 D5 D6
      The October run: registered directions and the detour rank are graded.

The model-side predicted directions come from the prereg (in-span down,
I-405 up, I-205 up); the predicted detour RANK is read from the campaign's
banked appendix values at scoring time, not hardcoded here.
"""
import argparse
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

API = "https://new.portal.its.pdx.edu/highways/api"
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "portal_rq")

# The frozen station set from PREREG_I5_ROSEQUARTER.md section 5, grouped as
# registered. "pred" is the registered direction of change during the closure;
# groups without one are context only and get no verdict.
GROUPS = [
    {"name": "in-span I-5 SB", "stations": [3121, 10642], "pred": "down"},
    {"name": "upstream I-5 SB approach", "stations": [3172, 10640],
     "pred": None},
    {"name": "downstream I-5 SB (S of I-84 merge)", "stations": [3120, 3185],
     "pred": None},
    {"name": "I-405 SB signed detour", "stations": [3122, 3196, 3110],
     "pred": "up"},
    {"name": "I-205 SB regional detour", "stations": [10579, 3107, 10582, 3105],
     "pred": "up"},
]
FROZEN = [s for g in GROUPS for s in g["stations"]]

# The null test's pinned day sets: two ordinary Tue-Thu pre-closure weeks.
NULL_A = ["2026-08-04", "2026-08-05", "2026-08-06"]
NULL_B = ["2026-08-11", "2026-08-12", "2026-08-13"]

MIN_HOURS = 20   # a station-day reporting fewer hours than this is dropped


def fetch(name, url):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        print(f"  fetching {url}")
        with urllib.request.urlopen(url, timeout=120) as r, open(path, "wb") as f:
            f.write(r.read())
    with open(path) as f:
        return json.load(f)


def station_meta():
    """Frozen-station metadata (name text), plus detector -> station for the
    frozen set only. Same active/2DS filters the speed-check harness froze."""
    def is_active(props):
        return '"upper": null' in (props.get("active_dates") or "")

    smeta = fetch("stationmeta.json", f"{API}/stationmetadata/?format=json")
    text = {}
    for feat in smeta["features"]:
        p = feat["properties"]
        if p["stationid"] in FROZEN and is_active(p):
            text[p["stationid"]] = p.get("locationtext") or str(p["stationid"])

    dmeta = fetch("detmeta.json", f"{API}/detectormetadata/?format=json")
    if isinstance(dmeta, dict):
        dmeta = dmeta.get("features", dmeta)
    det2sta = {}
    for d in dmeta:
        p = d.get("properties", d)
        if is_active(p) and p["stationid"] in FROZEN:
            det2sta[p["detectorid"]] = p["stationid"]
    return text, det2sta


def day_records(day, det2sta):
    """(station, detector, hour) -> volume for one day, frozen stations only.
    Volume None means the detector did not report; volume 0 is data."""
    import pandas as pd
    end = (pd.Timestamp(day) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    recs = fetch(f"freewaydata_{day}.json",
                 f"{API}/freewaydata/?start_date={day}&end_date={end}"
                 f"&resolution=01:00:00&format=json")
    out = {}
    for r in recs:
        sta = det2sta.get(r["detector_id"])
        if sta is None or r.get("volume") is None:
            continue
        hour = int(str(r["starttime"])[11:13])
        out[(sta, r["detector_id"], hour)] = float(r["volume"])
    return out


def period_volumes(days, det2sta, detectors_keep=None):
    """Mean daily volume per station over a period.

    Returns (daily, seen): daily maps station -> mean daily volume across its
    kept station-days; seen maps station -> the set of detectors that reported
    at all in this period (for the both-periods consistency rule). With
    detectors_keep, only those detectors are summed."""
    per_day = defaultdict(lambda: defaultdict(float))   # (sta, day) accumulation
    hours = defaultdict(set)                            # (sta, day) -> hours seen
    seen = defaultdict(set)                             # sta -> detectors seen
    for day in days:
        for (sta, det, hour), vol in day_records(day, det2sta).items():
            seen[sta].add(det)
            if detectors_keep is not None and det not in detectors_keep.get(sta, ()):
                continue
            per_day[(sta, day)][hour] += vol
            hours[(sta, day)].add(hour)
    daily = {}
    for sta in FROZEN:
        vals = []
        for day in days:
            if len(hours[(sta, day)]) >= MIN_HOURS:
                vals.append(sum(per_day[(sta, day)].values()))
            elif hours[(sta, day)]:
                print(f"  drop {sta} {day}: only {len(hours[(sta, day)])} "
                      f"hours reporting (< {MIN_HOURS})")
        if vals:
            daily[sta] = sum(vals) / len(vals)
    return daily, seen


def score(days_a, days_b, label_a, label_b):
    """The scoring core, used identically by --null and --score: mean daily
    volume per frozen station in each period (common detectors only), relative
    change, group direction, and the detour rank."""
    text, det2sta = station_meta()
    print(f"frozen stations with active metadata: {len(text)}/{len(FROZEN)}")

    # first pass per period to learn which detectors report, then the
    # consistency rule: only detectors present in BOTH periods count
    _, seen_a = period_volumes(days_a, det2sta)
    _, seen_b = period_volumes(days_b, det2sta)
    common = {sta: seen_a.get(sta, set()) & seen_b.get(sta, set())
              for sta in FROZEN}
    for sta in FROZEN:
        na, nb = len(seen_a.get(sta, ())), len(seen_b.get(sta, ()))
        if len(common[sta]) < max(na, nb):
            print(f"  station {sta}: {na} detectors in {label_a}, {nb} in "
                  f"{label_b}, using the {len(common[sta])} common ones")

    vol_a, _ = period_volumes(days_a, det2sta, detectors_keep=common)
    vol_b, _ = period_volumes(days_b, det2sta, detectors_keep=common)

    print(f"\n{label_a}: {days_a}\n{label_b}: {days_b}")
    print(f"\n{'group / station':<52}{label_a:>10}{label_b:>10}{'change':>9}")
    group_change = {}
    for g in GROUPS:
        changes = []
        print(g["name"])
        for sta in g["stations"]:
            a, b = vol_a.get(sta), vol_b.get(sta)
            if a is None or b is None or a == 0:
                print(f"  {sta:<6} {text.get(sta, ''):<43}"
                      f"{'UNUSABLE (no data in one period)':>29}")
                continue
            ch = (b - a) / a
            changes.append(ch)
            print(f"  {sta:<6} {text.get(sta, ''):<43}"
                  f"{a:>10,.0f}{b:>10,.0f}{ch:>+8.1%}")
        if changes:
            group_change[g["name"]] = sum(changes) / len(changes)
            arrow = {"down": "predicted DOWN", "up": "predicted UP",
                     None: "context, no prediction"}[g["pred"]]
            mean = group_change[g["name"]]
            verdict = ""
            if g["pred"] == "down":
                verdict = " -> " + ("MATCHES" if mean < 0 else "DOES NOT MATCH")
            elif g["pred"] == "up":
                verdict = " -> " + ("MATCHES" if mean > 0 else "DOES NOT MATCH")
            print(f"  group mean {mean:+.1%}  ({arrow}){verdict}")

    i405 = group_change.get("I-405 SB signed detour")
    i205 = group_change.get("I-205 SB regional detour")
    if i405 is not None and i205 is not None:
        lead = "I-405" if i405 > i205 else "I-205"
        print(f"\nrank of relative gains: {lead} first "
              f"(I-405 {i405:+.1%} vs I-205 {i205:+.1%})")
    return group_change


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", nargs="+", metavar="DAY")
    ap.add_argument("--null", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--before", nargs="+", metavar="DAY")
    ap.add_argument("--during", nargs="+", metavar="DAY")
    args = ap.parse_args()

    if args.coverage:
        text, det2sta = station_meta()
        daily, seen = period_volumes(args.coverage, det2sta)
        print(f"\ncoverage on {args.coverage}:")
        for sta in FROZEN:
            ok = sta in daily
            print(f"  {sta:<6} {text.get(sta, ''):<45} "
                  f"{'ok, ' + format(daily[sta], ',.0f') + ' veh/day' if ok else 'NOT REPORTING'}"
                  f"  ({len(seen.get(sta, ()))} detectors)")
        missing = [s for s in FROZEN if s not in daily]
        print(f"\n{len(FROZEN) - len(missing)}/{len(FROZEN)} frozen stations "
              f"usable" + (f"; drop per prereg rule: {missing}" if missing else ""))
        return

    if args.null:
        print("NULL TEST: two ordinary pre-closure weeks scored as if one "
              "were the closure.\nExpectation: small changes, no consistent "
              "direction, rank not meaningful.\nThis validates the pipeline "
              "mechanics, not the model.\n")
        score(NULL_A, NULL_B, "week A", "week B")
        return

    if args.score:
        if not args.before or not args.during:
            raise SystemExit("--score needs --before DAYS and --during DAYS")
        score(args.before, args.during, "before", "during")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
