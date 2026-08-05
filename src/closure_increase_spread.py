"""Seed-level spread of the closure DETOUR INCREASES (Christof review item 6).

The drop on a closed arterial is near-mechanical; the redistribution onto the
detours is the chapter's actual claim, and it was reported from seed 42 alone.
This reads the committed 12-seed Powell-closure sweep parquets (closure_sweep.py
outputs, on disk) and reports the per-seed distribution of the Division and
Holgate NO2 increases, plus the Powell drop and network total, with the same
street matcher as closure_static_reassignment.py. Analysis-only; no sim.

Result recorded Jul 30 (ledger section 10): Powell -59.6 +/- 2.1, Division
+32.4 +/- 12.9 (min +8.3), Holgate +42.4 +/- 8.1, total +3.4 +/- 1.9 -- every
sign consistent in 12/12 seeds; seed 42's Division +41.2 sits above the mean.

Run: python src/closure_increase_spread.py
"""
import glob
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import osmnx as ox
import pandas as pd

import config

STREETS = ("Powell", "Division", "Holgate")


def main():
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    names = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        nm = nm if isinstance(nm, list) else [nm]
        for s in STREETS:
            if any(n and s.lower() in str(n).lower() for n in nm):
                names[(u, v, k)] = s
                break

    def street_nox(path):
        df = pd.read_parquet(path)
        out = {s: 0.0 for s in STREETS}
        tot = 0.0
        for r in df.itertuples():
            tot += r.nox_g
            s = names.get((r.u, r.v, r.key))
            if s:
                out[s] += r.nox_g
        out["total"] = tot
        return out

    seeds = sorted({int(re.search(r"sweep_powell_(\d+)_open", f).group(1))
                    for f in glob.glob(os.path.join(
                        config.PROCESSED_DIR, "sweep_powell_*_open_segments.parquet"))})
    rows = []
    for sd in seeds:
        o = street_nox(os.path.join(config.PROCESSED_DIR,
                                    f"sweep_powell_{sd}_open_segments.parquet"))
        c = street_nox(os.path.join(config.PROCESSED_DIR,
                                    f"sweep_powell_{sd}_closed_segments.parquet"))
        rows.append({k: 100 * (c[k] / o[k] - 1) for k in (*STREETS, "total")}
                    | {"seed": sd})
    df = pd.DataFrame(rows).set_index("seed")
    print(f"Powell-closure sweep, {len(seeds)} seeds\n")
    print(df.round(1).to_string())
    print("\nmean +/- SD (ddof=1), sign consistency:")
    for k in (*STREETS, "total"):
        v = df[k]
        consistent = (v < 0).sum() if k == "Powell" else (v > 0).sum()
        print(f"  {k:9s} {v.mean():+6.1f} +/- {v.std():4.1f}   "
              f"min {v.min():+6.1f}  max {v.max():+6.1f}  "
              f"consistent sign in {consistent}/{len(v)} seeds")


if __name__ == "__main__":
    main()
