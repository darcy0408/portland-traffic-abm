"""Where do the model's queues actually form, and are those places real?

Read-only. Runs no simulation. Reads the finished lane-capacity sweep parquets
and answers the question behind "the cars are queuing, is that wrong": a queue
is only a defect if it forms somewhere real Portland traffic does not queue.

The segments parquets carry everything needed directly:
    value      vehicle-seconds of occupancy on the edge
    v_sum      sum of instantaneous speeds over those vehicle-seconds (m/s)
    stuck_sum  vehicle-seconds spent stuck
so mean speed = v_sum / value and stuck share = stuck_sum / value, no graph
join required for the physics. The graph supplies street names only.

Usage (after the lcap campaign has run):
    python src/queue_diagnostic.py
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import osmnx as ox

import config

GRAPH = os.path.join(config.NETWORK_DIR, "graph_metro20k_lanes.graphml")
SEEDS = [42, 7, 13, 99, 2024, 314, 777, 8]
ARM = "lcap_realism_reallanes"


def load_arm(n):
    """Per-edge means across seeds, keyed by (u, v, key)."""
    frames = []
    for s in SEEDS:
        p = os.path.join(config.PROCESSED_DIR,
                         f"{ARM}_n{n}_s{s}_segments.parquet")
        if os.path.exists(p):
            frames.append(pd.read_parquet(p))
    if not frames:
        raise SystemExit(f"no parquets for demand {n}")
    cat = pd.concat(frames)
    return cat.groupby(["u", "v", "key"]).mean(), len(frames)


def main():
    print(f"loading graph for street names: {GRAPH}")
    G = ox.load_graphml(GRAPH)
    meta = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name") or d.get("ref") or "(unnamed)"
        if isinstance(nm, list):
            nm = nm[0]
        hw = d.get("highway")
        if isinstance(hw, list):
            hw = hw[0]
        meta[(int(u), int(v), int(k))] = (str(nm), str(hw))

    lo, n_lo = load_arm(16500)
    hi, n_hi = load_arm(33000)
    print(f"seeds averaged: {n_lo} at 16,500 / {n_hi} at 33,000\n")

    def enrich(df):
        df = df.copy()
        info = [meta.get(i, ("?", "?")) for i in df.index]
        df["name"] = [x[0] for x in info]
        df["hwy"] = [x[1] for x in info]
        df["kmh"] = 3.6 * df["v_sum"] / df["value"].where(df["value"] > 0)
        df["stuck_frac"] = df["stuck_sum"] / df["value"].where(df["value"] > 0)
        return df

    lo, hi = enrich(lo), enrich(hi)

    print("=== worst bottlenecks at the CITED demand (16,500) ===")
    print("ranked by vehicle-seconds of occupancy (mean over 8 seeds)")
    print(f"{'veh-s':>10}  {'km/h':>5}  {'stuck%':>6}  {'veh':>6}  street")
    for i, r in lo.sort_values("value", ascending=False).head(20).iterrows():
        print(f"{r['value']:>10,.0f}  {r['kmh']:>5.1f}  "
              f"{100 * r['stuck_frac']:>5.0f}%  {r['throughput']:>6,.0f}  "
              f"{r['hwy']:<15} {r['name']}")

    print("\n=== where the EXTRA queueing goes as demand doubles ===")
    print("ranked by growth in occupancy, 16,500 -> 33,000")
    j = lo.join(hi[["value", "kmh"]], rsuffix="_hi", how="inner")
    j["growth"] = j["value_hi"] - j["value"]
    for i, r in j.sort_values("growth", ascending=False).head(20).iterrows():
        print(f"+{r['growth']:>10,.0f}  {r['kmh']:>5.1f} -> {r['kmh_hi']:>5.1f} km/h  "
              f"{r['hwy']:<15} {r['name']}")

    # network-level congestion shape at each demand
    for label, df in (("16,500", lo), ("33,000", hi)):
        used = df[df["value"] > 0]
        slow = used[used["kmh"] < 10]
        print(f"\nat {label}: {len(used):,} edges carried traffic; "
              f"{len(slow):,} ({100 * len(slow) / len(used):.1f}%) had mean "
              f"speed under 10 km/h, holding "
              f"{100 * slow['value'].sum() / used['value'].sum():.1f}% of all "
              f"vehicle-time; network mean speed "
              f"{3.6 * used['v_sum'].sum() / used['value'].sum():.1f} km/h; "
              f"stuck share {100 * used['stuck_sum'].sum() / used['value'].sum():.1f}%")

    # class profile of where vehicle-time is spent at the cited demand
    print("\n=== vehicle-time by road class at 16,500 ===")
    byc = lo[lo["value"] > 0].groupby("hwy").agg(
        vehs=("value", "sum"), v=("v_sum", "sum"), stuck=("stuck_sum", "sum"))
    byc["kmh"] = 3.6 * byc["v"] / byc["vehs"]
    byc["share"] = 100 * byc["vehs"] / byc["vehs"].sum()
    byc["stuckpct"] = 100 * byc["stuck"] / byc["vehs"]
    for cls, r in byc.sort_values("share", ascending=False).head(10).iterrows():
        print(f"  {cls:<16} {r['share']:>5.1f}% of vehicle-time  "
              f"{r['kmh']:>5.1f} km/h  stuck {r['stuckpct']:>4.0f}%")


if __name__ == "__main__":
    main()
