"""Grade Appendix R's instrument-based predictions (R4, R3 pair clauses).

Reads rqtt_fwrqc{25,50,75}.json and rqtt_fwrqi.json (pulled from Orca).
  R4: the i5sb_detour pair's closed travel time rises with the compliance
      level, and Appendix N's October rank (detour > span > vanc on the
      closed-vs-open rise) is re-registered per level.
  R3 (pair part): interstate_sb, mlk_sb, vanc_pdx move DOWN relative to
      fwrqi as compliance rises (registered caveat: may land under the bar,
      reported as such).
Verdict bar unchanged: unanimous sign across the 8 paired seeds, |t| > 3.
"""

import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "processed"
SEEDS = ["7", "8", "13", "42", "99", "314", "777", "2024"]
LEVELS = ["25", "50", "75"]

arms = {lv: json.load(open(DATA / f"rqtt_fwrqc{lv}.json"))["results"]
        for lv in LEVELS}
fwrqi = json.load(open(DATA / f"rqtt_fwrqi.json"))["results"]


def tstat(diffs):
    n = len(diffs)
    mean = sum(diffs) / n
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n - 1))
    return mean, sd, (mean / (sd / math.sqrt(n)) if sd > 0 else float("inf"))


# Sanity: the shared open arm must give identical open_s everywhere.
for pair in fwrqi:
    for s in SEEDS:
        vals = {fwrqi[pair][s]["open_s"]} | {arms[lv][pair][s]["open_s"] for lv in LEVELS}
        assert len(vals) == 1, f"open_s mismatch {pair} seed {s}: {vals}"
print("open_s identical across fwrqi and all three levels, every pair/seed\n")

# ---- R4: i5sb_detour rises with level -------------------------------------
print("R4: i5sb_detour closed travel time rises with compliance level")
mono = 0
for s in SEEDS:
    ts = [arms[lv]["i5sb_detour"][s]["closed_s"] for lv in LEVELS]
    ok = ts[0] < ts[1] < ts[2]
    mono += ok
    print(f"  seed {s:>4}: {ts[0]:7.1f} < {ts[1]:7.1f} < {ts[2]:7.1f} s  "
          f"{'OK' if ok else 'VIOLATED'}")
for a, b in [("25", "50"), ("50", "75"), ("25", "75")]:
    diffs = [arms[b]["i5sb_detour"][s]["closed_s"]
             - arms[a]["i5sb_detour"][s]["closed_s"] for s in SEEDS]
    m, sd, t = tstat(diffs)
    signs = sum(d > 0 for d in diffs)
    print(f"  c{b} - c{a}: {m:+7.1f} s ({signs}/8 up, t={t:5.1f})")
print(f"  R4 monotone per seed: {mono}/8 -> "
      f"{'SUPPORTED' if mono == 8 else 'NOT SUPPORTED as a per-seed claim'}\n")

print("Appendix N October rank re-registered per level (closed-vs-open % rise):")
for lv in LEVELS:
    rises = {}
    for pair in ["i5sb_detour", "i5sb_span", "vanc_pdx"]:
        pct = [100 * (arms[lv][pair][s]["closed_s"] / arms[lv][pair][s]["open_s"] - 1)
               for s in SEEDS]
        rises[pair] = sum(pct) / len(pct)
    order = sorted(rises, key=rises.get, reverse=True)
    ok = order == ["i5sb_detour", "i5sb_span", "vanc_pdx"]
    print(f"  level {lv}%: " + " > ".join(f"{p} {rises[p]:+.1f}%" for p in order)
          + ("  (detour > span > vanc HOLDS)" if ok else "  (ORDER DIFFERS)"))
print()

# ---- R3 pair part: DOWN vs fwrqi as compliance rises ----------------------
print("R3 (instrument pairs): DOWN relative to fwrqi as compliance rises")
for pair in ["interstate_sb", "mlk_sb", "vanc_pdx"]:
    print(f"  {pair}:")
    for lv in LEVELS:
        diffs = [arms[lv][pair][s]["closed_s"] - fwrqi[pair][s]["closed_s"]
                 for s in SEEDS]
        m, sd, t = tstat(diffs)
        signs = sum(d < 0 for d in diffs)
        base = sum(fwrqi[pair][s]["closed_s"] for s in SEEDS) / 8
        verdict = ("SUPPORTED" if (signs == 8 and abs(t) > 3 and m < 0)
                   else "under the bar" if m < 0 else "WRONG DIRECTION")
        print(f"    level {lv}%: {m:+7.1f} s ({100*m/base:+5.2f}%), "
              f"down {signs}/8, t={t:5.1f} -> {verdict}")
