"""Export the Rose Quarter (I-5 SB closure) PREDICTION tables for the Tableau dashboard.

Read-only and prediction-only. It reads the saved fwrq campaign summaries (16 files,
8 seeds x open/closed), the PORTAL station metadata cache, and the travel-time
logger's frozen route list, and writes one .xlsx with four small sheets:

  corridors     route-level mean paired change per tracked freeway (ledger RQ1 to RQ5),
                with the verdict recomputed by the frozen rule and every mean asserted
                against the ledger value, so the sheet cannot drift from the ledger
  stations      the 13 frozen PORTAL stations with lat/lon and their registered
                direction (from rosequarter_score.GROUPS, the October instrument)
  routes        the 12 logger routes with endpoints, the Appendix M.2 expectation, and
                the frozen October rank (Appendix N.4 / U.6)
  route_points  the same routes in long form (two rows per route) so Tableau can draw
                each as a line

Nothing here reads observed closure data, and nothing here grades anything: grades
come from src/rosequarter_score.py and the logger instrument in October. The
per-segment map table comes from `tableau_export.py paired` (see TABLEAU.md).

Example (from the tableau worktree; the campaign files live in pta-realism and the
PORTAL cache in the main checkout):

  python src/tableau_rosequarter.py --data-dir C:/dev/pta-realism/data/processed
      --stationmeta C:/dev/portland-traffic-abm/data/portal_rq/stationmeta.json
      --pairs C:/dev/portland-traveltime-log/pairs.json
      --out outputs/tableau/rosequarter_tables.xlsx
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from rosequarter_score import GROUPS   # the October instrument's frozen station groups

# The campaign as registered (PREREG_I5_ROSEQUARTER.md section 1): 8 paired seeds,
# arms open / rosequarter, run names <prefix>_<arm>_s<seed>.
SEEDS = [42, 7, 13, 99, 314, 777, 2024, 8]
PREFIX, OPEN_ARM, CLOSED_ARM = "fwrq", "open", "rosequarter"
# Prereg section 3 (frozen): a directional claim is SUPPORTED only with unanimous
# sign across the 8 paired seeds and t > 3 (the standing campaign bar).
T_BAR = 3.0

# What the ledger banked per tracked route (RESULTS_LEDGER section 27: mean percent
# change in route NOx, closed minus open, over the 8 seeds) and the registered
# direction (Appendix A.1). The script recomputes each mean from the summaries and
# REFUSES to write if any differs from the ledger by more than 0.05 points: the sheet
# copies the ledger, it never re-derives it silently.
LEDGER = {
    "I 405":  ("RQ1", 84.91, "up strongly: the signed detour, predicted to gain most"),
    "I 205":  ("RQ2", 3.08,  "up weakly: the regional detour, predicted second"),
    "I 5":    ("RQ3", -0.79, "whole route not graded; the closed span goes to zero by "
                             "construction and the in-span stations are predicted down"),
    "OR 213": ("RQ4", 2.90,  "none registered: surface alternates sit inside seed noise"),
    "US 26":  ("RQ5", -0.58, "none registered: surface alternates sit inside seed noise"),
}

# Registered direction per frozen station group, Appendix A.1 wording, keyed by the
# group names in rosequarter_score.GROUPS. The October instrument grades only the
# groups that carry a "pred" there; the other two are context and get no verdict,
# which the sheet says outright rather than inventing a direction.
EXPECTATION = {
    "in-span I-5 SB": "down to the local-access residual",
    "upstream I-5 SB approach": "down (Appendix A.1 expectation, not graded)",
    "downstream I-5 SB (S of I-84 merge)": "none registered (context only)",
    "I-405 SB signed detour": "up strongly",
    "I-205 SB regional detour": "up weakly",
}

# Appendix M.2: directional expectations for the 12 logger routes, banked Aug 20
# before the instrument ran. (expectation, role)
ROUTE_EXPECTATION = {
    "i5sb_span":     ("up", "test"),
    "vanc_pdx":      ("up", "test"),
    "i5sb_detour":   ("up", "test"),
    "interstate_sb": ("up", "test"),
    "mlk_sb":        ("up", "test"),
    "i84wb_feeder":  ("up", "test"),
    "i205_sb":       ("up weakly, may not clear the bar", "test"),
    "williams_nb":   ("about no change", "direction control"),
    "grand_nb":      ("about no change", "direction control"),
    "ctrl_se":       ("no change", "far-field control"),
    "powell_wb":     ("open question, either answer reported", "open question"),
    "ctrl_west":     ("no model comparison: endpoint outside the graph", "logger-side control"),
}
# The frozen October rank of modeled slowdowns, largest first. Appendix N.4 registered
# one ordering per arm; U.6 froze the improved-arm ordering for fwrqe as well (Sept 8).
# The base arm swaps the last two. Both are registered and arm-labeled, and the six
# unranked routes are declared indistinguishable from seed noise.
RANK_IMPROVED = ["i5sb_detour", "i5sb_span", "vanc_pdx", "interstate_sb", "mlk_sb"]
RANK_BASE = ["i5sb_detour", "i5sb_span", "vanc_pdx", "mlk_sb", "interstate_sb"]

MERCATOR_R = 20037508.342789244   # half the Web Mercator world width, metres


def corridors(data_dir):
    """Route-level paired readout from the 16 campaign summaries, one row per route."""
    pct, absd, base, edges, model = {}, {}, {}, {}, set()
    for s in SEEDS:
        o = json.load(open(os.path.join(data_dir, f"{PREFIX}_{OPEN_ARM}_s{s}_summary.json")))
        c = json.load(open(os.path.join(data_dir, f"{PREFIX}_{CLOSED_ARM}_s{s}_summary.json")))
        model.add(f"{o['stack']} stack, {o['fleet']} fleet")
        model.add(f"{c['stack']} stack, {c['fleet']} fleet")
        for r in o["routes"]:
            no = sum(v[0] for v in o["routes"][r].values())
            nc = sum(v[0] for v in c["routes"][r].values())
            pct.setdefault(r, []).append(100 * (nc - no) / no)
            absd.setdefault(r, []).append(nc - no)
            base.setdefault(r, []).append(no)
            edges[r] = len(o["routes"][r])
    assert len(model) == 1, f"mixed model settings across the campaign: {model}"
    model = model.pop()   # one label for the whole campaign, e.g. "base stack, mixed fleet"
    rows = []
    for r in pct:
        a = np.array(pct[r])
        mean, sd = a.mean(), a.std(ddof=1)
        t = mean / (sd / math.sqrt(len(a)))
        agree = int((np.sign(a) == np.sign(mean)).sum())
        verdict = "SUPPORTED" if agree == len(a) and abs(t) > T_BAR else "not at bar"
        lid, ledger_mean, prediction = LEDGER[r]
        assert abs(mean - ledger_mean) <= 0.05, \
            f"{r}: recomputed {mean:.2f}% vs ledger {lid} {ledger_mean:.2f}%; refusing to write"
        rows.append({
            "Route": r.replace(" ", "-"), "Ledger ID": lid,
            "Registered Prediction": prediction,
            "Mean Change (%)": round(mean, 1), "SD (%)": round(sd, 1),
            "Seeds Agreeing": f"{agree}/{len(a)}", "t": round(t, 1), "Verdict": verdict,
            "Mean Change (g NOx)": round(float(np.mean(absd[r]))),
            "Open Baseline (g NOx)": round(float(np.mean(base[r]))),
            "Edges": edges[r], "Model": model,
        })
    return pd.DataFrame(rows)


def stations(stationmeta):
    """The 13 frozen PORTAL stations with lat/lon (converted from the cache's Web
    Mercator metres) and the registered direction of their group."""
    meta = {f["properties"]["stationid"]: f
            for f in json.load(open(stationmeta))["features"]}
    missing = set(EXPECTATION) ^ {g["name"] for g in GROUPS}
    assert not missing, f"station groups renamed, update EXPECTATION: {missing}"
    rows = []
    for g in GROUPS:
        for sid in g["stations"]:
            f = meta[sid]
            x, y = f["geometry"]["coordinates"]
            lat = math.degrees(2 * math.atan(math.exp(y / MERCATOR_R * math.pi)) - math.pi / 2)
            rows.append({
                "Station ID": sid, "Location": f["properties"]["locationtext"],
                "Group": g["name"], "Milepost": f["properties"]["milepost"],
                "Lat": round(lat, 5), "Lon": round(x / MERCATOR_R * 180, 5),
                "Registered Direction": EXPECTATION[g["name"]],
                "Graded in October": "yes" if g["pred"] else "no",
            })
    return pd.DataFrame(rows)


def routes(pairs_path):
    """The 12 frozen logger routes with endpoints, expectation, role, and rank."""
    pairs = json.load(open(pairs_path))["pairs"]   # the file is {"comment": ..., "pairs": [...]}
    assert {p["id"] for p in pairs} == set(ROUTE_EXPECTATION), "pairs.json changed"
    wide, long = [], []
    for p in pairs:
        exp, role = ROUTE_EXPECTATION[p["id"]]
        row = {
            "Pair": p["id"], "Name": p["name"], "Why": p["why"],
            "Registered Expectation": exp, "Role": role,
            "Frozen Rank": RANK_IMPROVED.index(p["id"]) + 1 if p["id"] in RANK_IMPROVED else None,
            "Frozen Rank (base arm)": RANK_BASE.index(p["id"]) + 1 if p["id"] in RANK_BASE else None,
            "From Lat": p["from"][0], "From Lon": p["from"][1],
            "To Lat": p["to"][0], "To Lon": p["to"][1],
        }
        wide.append(row)
        for order, (lat, lon) in ((1, p["from"]), (2, p["to"])):
            point = {k: v for k, v in row.items() if not k.startswith(("From", "To"))}
            point.update({"Point Order": order, "Lat": lat, "Lon": lon})
            long.append(point)
    return pd.DataFrame(wide), pd.DataFrame(long)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, help="dir holding the fwrq summaries")
    ap.add_argument("--stationmeta", required=True, help="PORTAL stationmeta.json cache")
    ap.add_argument("--pairs", required=True, help="the logger's frozen pairs.json")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    sheets = {"corridors": corridors(a.data_dir), "stations": stations(a.stationmeta)}
    sheets["routes"], sheets["route_points"] = routes(a.pairs)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with pd.ExcelWriter(a.out) as xw:
        for name, df in sheets.items():
            df.to_excel(xw, index=False, sheet_name=name)
            print(f"  {name:<13}{len(df):>4} rows")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
