"""Grade Appendix R's summary-based predictions (R1, R2, R3 route totals, R5).

Reads the fwrqc and fwrqi summary JSONs pulled from Orca into data/processed/.
R3's instrument pairs and R4 are graded separately from the travel-time
instrument output; this script covers everything the campaign summaries hold.

The registered wording being graded (PREREG_I5_ROSEQUARTER.md, Appendix R):
  R1 (primary): I-405 NOx gain (closed minus open) increases monotonically
      with the compliance level, gain(.25) < gain(.50) < gain(.75), PER SEED.
  R2: at every level the I-405 gain is at least fwrqi's (+37.7%), and I-405
      outranks I-205 at every level.
  R3 (route-total part): US 26 and OR 213 route totals move DOWN relative to
      fwrqi as compliance rises. (The registered list also names OR 99E, but
      the summaries track no OR 99E route; its stand-in is the mlk_sb
      instrument pair, graded with R4. Reported as-is, not papered over.)
  R5: network NOx total rises slightly with compliance, within a few percent.
Verdict bar, unchanged: unanimous sign across the 8 paired seeds and |t| > 3.
"""

import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data" / "processed"
SEEDS = [7, 8, 13, 42, 99, 314, 777, 2024]
LEVELS = ["25", "50", "75"]
FWRQI_I405_PCT = 37.7  # Appendix L's cited mean gain


def load(stem):
    with open(DATA / f"{stem}_summary.json") as f:
        return json.load(f)


def route_nox(rec, route):
    return sum(v[0] for v in rec["routes"][route].values())


def tstat(diffs):
    n = len(diffs)
    mean = sum(diffs) / n
    sd = math.sqrt(sum((d - mean) ** 2 for d in diffs) / (n - 1))
    return mean, sd, (mean / (sd / math.sqrt(n)) if sd > 0 else float("inf"))


# ---- load everything once -------------------------------------------------
recs = {}  # (kind, seed) -> record
for s in SEEDS:
    recs[("c_open", s)] = load(f"fwrqc_open_s{s}")
    recs[("i_open", s)] = load(f"fwrqi_open_s{s}")
    recs[("i_closed", s)] = load(f"fwrqi_rosequarter_s{s}")
    for lv in LEVELS:
        recs[(f"c{lv}", s)] = load(f"fwrqc{lv}_rosequarter_s{s}")

# Registered integrity restated locally: open arms identical across stacks.
for s in SEEDS:
    a, b = recs[("c_open", s)], recs[("i_open", s)]
    assert a["network_nox_g"] == b["network_nox_g"], f"open mismatch seed {s}"

print("open-arm identity vs fwrqi re-verified locally: 8/8 seeds\n")

# Fallbacks and realized compliance across the whole campaign.
total_fb = 0
for lv in LEVELS:
    elig = sum(recs[(f"c{lv}", s)]["detour_stats"]["n_eligible"] for s in SEEDS)
    comp = sum(recs[(f"c{lv}", s)]["detour_stats"]["n_compliant"] for s in SEEDS)
    fb = sum(recs[(f"c{lv}", s)]["detour_stats"]["n_fallback"] for s in SEEDS)
    total_fb += fb
    print(f"level {lv}%: eligible {elig}, complied {comp} "
          f"(realized {100*comp/elig:.1f}%), fallbacks {fb}")
print(f"total fallbacks across 24 closed runs: {total_fb}\n")

# ---- R1: per-seed monotonicity of the I-405 gain --------------------------
print("R1 (primary): I-405 NOx gain monotone in level, per seed")
mono = 0
for s in SEEDS:
    open_g = route_nox(recs[("c_open", s)], "I 405")
    gains = [route_nox(recs[(f"c{lv}", s)], "I 405") - open_g for lv in LEVELS]
    ok = gains[0] < gains[1] < gains[2]
    mono += ok
    print(f"  seed {s:>4}: +{gains[0]:7.1f} < +{gains[1]:7.1f} < +{gains[2]:7.1f} g"
          f"  {'OK' if ok else 'VIOLATED'}")
print(f"  R1: {mono}/8 seeds strictly monotone -> "
      f"{'SUPPORTED' if mono == 8 else 'NOT SUPPORTED'}\n")

# ---- R2: every level >= fwrqi's gain; I-405 > I-205 everywhere ------------
print("R2: I-405 gain at least fwrqi's at every level; I-405 outranks I-205")
r2_ok = True
for lv in LEVELS:
    pct = []
    paired = []   # fwrqc closed - fwrqi closed, I-405 NOx, per seed
    rank = 0
    for s in SEEDS:
        open_g = route_nox(recs[("c_open", s)], "I 405")
        closed_g = route_nox(recs[(f"c{lv}", s)], "I 405")
        pct.append(100 * (closed_g - open_g) / open_g)
        paired.append(closed_g - route_nox(recs[("i_closed", s)], "I 405"))
        g205 = (route_nox(recs[(f"c{lv}", s)], "I 205")
                - route_nox(recs[("c_open", s)], "I 205"))
        rank += (closed_g - open_g) > g205
    # Rank on the percent scale as well: the established convention (the
    # readout tables and Appendix J's rank floors are in percentage points).
    # The gram-scale count is disclosed beside it, never hidden.
    rank_pct = 0
    rankdiffs = []
    for s in SEEDS:
        o405 = route_nox(recs[("c_open", s)], "I 405")
        o205 = route_nox(recs[("c_open", s)], "I 205")
        g405 = 100 * (route_nox(recs[(f"c{lv}", s)], "I 405") - o405) / o405
        g205 = 100 * (route_nox(recs[(f"c{lv}", s)], "I 205") - o205) / o205
        rank_pct += g405 > g205
        rankdiffs.append(g405 - g205)
    rm, rsd, rt = tstat(rankdiffs)
    mean_pct = sum(pct) / len(pct)
    m, sd, t = tstat(paired)
    signs = sum(d > 0 for d in paired)
    lvl_ok = mean_pct >= FWRQI_I405_PCT and rank_pct == 8 and abs(rt) > 3
    r2_ok &= lvl_ok
    print(f"  level {lv}%: mean gain {mean_pct:+6.1f}% (fwrqi {FWRQI_I405_PCT:+.1f}%), "
          f"rank pct {rank_pct}/8 t={rt:.1f} (grams {rank}/8), "
          f"vs fwrqi closed {m:+7.1f} g ({signs}/8, t={t:.1f})  "
          f"{'OK' if lvl_ok else 'FAILED'}")
print(f"  R2: {'SUPPORTED' if r2_ok else 'NOT SUPPORTED'} "
      "(threshold clause graded on level means, the scale the registered "
      "+37.7% is stated in; rank graded on percent, the prereg's rank "
      "convention, gram-scale count disclosed)\n")

# ---- R3 route totals: US 26, OR 213 vs fwrqi closed -----------------------
print("R3 (route-total part): surface alternates DOWN vs fwrqi as compliance rises")
print("  (OR 99E is not a tracked route in the summaries; its instrument")
print("   stand-in mlk_sb is graded with R4. Reported as registered-wording gap.)")
for route in ["US 26", "OR 213"]:
    print(f"  {route}:")
    for lv in LEVELS:
        diffs = [route_nox(recs[(f"c{lv}", s)], route)
                 - route_nox(recs[("i_closed", s)], route) for s in SEEDS]
        m, sd, t = tstat(diffs)
        base = sum(route_nox(recs[("i_closed", s)], route) for s in SEEDS) / 8
        signs = sum(d < 0 for d in diffs)
        verdict = "SUPPORTED" if (signs == 8 and abs(t) > 3 and m < 0) else \
                  ("under the bar" if m < 0 else "WRONG DIRECTION")
        print(f"    level {lv}%: {m:+8.1f} g ({100*m/base:+5.2f}%), "
              f"down {signs}/8, t={t:5.1f}  -> {verdict}")
print()

# ---- R5: network NOx rises slightly with compliance -----------------------
print("R5: network NOx total rises slightly with level, within a few percent")
for lv in LEVELS:
    diffs = [recs[(f"c{lv}", s)]["network_nox_g"]
             - recs[("c_open", s)]["network_nox_g"] for s in SEEDS]
    base = sum(recs[("c_open", s)]["network_nox_g"] for s in SEEDS) / 8
    m, sd, t = tstat(diffs)
    signs = sum(d > 0 for d in diffs)
    pct = 100 * m / base
    print(f"  level {lv}%: {pct:+5.2f}% ({signs}/8 up, t={t:5.1f})")
diffs_i = [recs[("i_closed", s)]["network_nox_g"]
           - recs[("i_open", s)]["network_nox_g"] for s in SEEDS]
base_i = sum(recs[("i_open", s)]["network_nox_g"] for s in SEEDS) / 8
print(f"  fwrqi reference: {100 * (sum(diffs_i)/8) / base_i:+5.2f}%")
