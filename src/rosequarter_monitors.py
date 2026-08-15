"""Model predictions at the Portland metro's two regulatory NO2 monitors for
the pre-registered Rose Quarter I-5 SB closure (PREREG_I5_ROSEQUARTER.md,
Appendix C).

The metro has exactly two regulatory NO2 monitors (Oregon DEQ 2023 Annual
Ambient Criteria Pollutant Air Monitoring Network Plan, Table 2 and Appendix
C):

  SEL  Portland SE Lafayette, AQS 41-051-0080, 45.4966 -122.6029
       (5824 SE Lafayette St; NCore, urban scale, hourly NO2 since 1984).
  TBC  Portland Near Roadway, AQS 41-067-0005, Tualatin
       (6745 SW Bradbury Ct, 27 m from I-5 at milepost 290.14; microscale,
       hourly NO2 since 2015). The DEQ table prints latitude 45.8992, which
       is Woodland WA and contradicts the site's own address, county, and
       milepost; the coordinate used here (45.3840 -122.7470) is derived
       from the street address and milepost. MP 290.14 places the monitor
       NORTH of the I-205 rejoin (exit 288) and SOUTH of the I-405 rejoin,
       so the model expects this stretch to keep I-405-detoured through
       traffic and lose only the I-205-diverted share.

For each monitor this reads the fwrq campaign's per-segment parquets (all
159k edges, both arms, 8 paired seeds) and computes closed-minus-open paired
differences of NOx grams and throughput over edges within RADIUS_M of the
monitor: all edges, I-5 mainline edges, and the SB-only I-5 subset (the
closure is directional, and the monitor prediction is about the SB
carriageway). Selection rule and radius are fixed a priori here, before any
during-closure data exists.

    python src/rosequarter_monitors.py --graph PATH --data-dir PATH [--out PATH]
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import osmnx as ox
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import generate        # noqa: E402
from freeway_rosequarter import SEEDS  # noqa: E402

RADIUS_M = 500.0       # a-priori selection radius around each monitor

MONITORS = {
    "SEL 41-051-0080": (45.4966, -122.6029),
    "TBC 41-067-0005": (45.3840, -122.7470),
}


def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def edge_sets(G, lat, lon):
    """Edges within RADIUS_M of the point (by edge-midpoint distance), as
    three sets: all, I-5 mainline, and SB-only I-5 mainline."""
    near = set()
    for u, v, k in G.edges(keys=True):
        mlat = 0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"]))
        mlon = 0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"]))
        if _haversine_m(lat, lon, mlat, mlon) <= RADIUS_M:
            near.add((u, v, k))
    i5 = set(generate.freeway_mainline_edges(G, "I 5"))
    near_i5 = near & i5
    near_i5_sb = set(generate._directional_subset(G, sorted(near_i5), "S")) \
        if near_i5 else set()
    return near, near_i5, near_i5_sb


def paired(data_dir, edge_set, col):
    """Per-seed closed-minus-open sums of `col` over edge_set."""
    diffs, base = [], []
    for seed in SEEDS:
        vals = {}
        for arm in ("open", "rosequarter"):
            p = os.path.join(data_dir, f"fwrq_{arm}_s{seed}_segments.parquet")
            df = pd.read_parquet(p, columns=["u", "v", "key", col])
            m = [(u, v, k) in edge_set
                 for u, v, k in zip(df["u"], df["v"], df["key"])]
            vals[arm] = float(df.loc[m, col].sum())
        diffs.append(vals["rosequarter"] - vals["open"])
        base.append(vals["open"])
    return np.array(diffs), np.array(base)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    print(f"loading graph {args.graph} ...")
    G = ox.load_graphml(args.graph)
    print(f"graph: {G.number_of_nodes():,} nodes / {G.number_of_edges():,} edges")

    results = {}
    for name, (lat, lon) in MONITORS.items():
        near, near_i5, near_i5_sb = edge_sets(G, lat, lon)
        sets = [("all edges", near), ("I-5 mainline", near_i5),
                ("I-5 mainline SB", near_i5_sb)]
        print(f"\n{name} ({lat}, {lon}), {RADIUS_M:.0f} m radius: "
              f"{len(near)} edges, {len(near_i5)} I-5 mainline, "
              f"{len(near_i5_sb)} SB")
        results[name] = {"lat": lat, "lon": lon, "radius_m": RADIUS_M,
                         "n_edges": len(near), "n_i5": len(near_i5),
                         "n_i5_sb": len(near_i5_sb), "metrics": {}}
        for label, es in sets:
            if not es:
                continue
            for col in ("nox_g", "throughput"):
                d, base = paired(args.data_dir, es, col)
                rel = 100.0 * d / np.where(base == 0, np.nan, base)
                pos = int((d > 0).sum())
                t = (abs(np.nanmean(rel))
                     / (np.nanstd(rel, ddof=1) / np.sqrt(len(rel)))
                     if np.nanstd(rel, ddof=1) > 0 else float("inf"))
                print(f"  {label:16s} {col:10s} open {base.mean():12,.1f}  "
                      f"diff {d.mean():+10,.1f} (sd {d.std(ddof=1):,.1f})  "
                      f"{np.nanmean(rel):+7.2f}% (sd {np.nanstd(rel, ddof=1):.2f})  "
                      f"signs {pos}/{len(d)}  t={t:.1f}")
                results[name]["metrics"][f"{label}|{col}"] = {
                    "open_mean": float(base.mean()),
                    "diff_mean": float(d.mean()),
                    "diff_sd": float(d.std(ddof=1)),
                    "rel_mean_pct": float(np.nanmean(rel)),
                    "rel_sd_pct": float(np.nanstd(rel, ddof=1)),
                    "signs_pos": pos, "n": len(d), "t": float(t),
                }

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1)
        print(f"\nwritten -> {args.out}")


if __name__ == "__main__":
    main()
