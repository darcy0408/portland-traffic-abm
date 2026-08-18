"""Where do the model's queues actually form, and are those places real?

Read-only. Runs no simulation. Reads the finished lane-capacity sweep parquets
and answers the question behind "the cars are queuing, is that wrong": a queue
is only a defect if it forms somewhere real Portland traffic does not queue.

For each edge, realized speed is recovered the same way noise.py does:
    v_mean = length * throughput / value
where value is vehicle-seconds of occupancy. An edge with high occupancy and
low realized speed is a jam. Ranking edges by occupancy, averaged across the 8
seeds, names the model's worst bottlenecks; comparing 16,500 against 33,000
demand shows where the EXTRA queueing concentrates as load rises.

Usage (after the lcap campaign has run):
    python src/queue_diagnostic.py
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import osmnx as ox

import config

GRAPH = os.path.join(config.NETWORK_DIR, "graph_metro20k_lanes.graphml")
SEEDS = [42, 7, 13, 99, 2024, 314, 777, 8]
ARM = "lcap_realism_reallanes"


def load_arm(n):
    """Mean per-edge occupancy (veh-s) and throughput across seeds, as frames
    indexed by (u, v, key)."""
    frames = []
    for s in SEEDS:
        p = os.path.join(config.PROCESSED_DIR, f"{ARM}_n{n}_s{s}.parquet")
        if os.path.exists(p):
            frames.append(pd.read_parquet(p))
    if not frames:
        raise SystemExit(f"no parquets for demand {n}")
    cat = pd.concat(frames)
    return cat.groupby(cat.index).mean(), len(frames)


def main():
    print(f"loading graph for names/lengths: {GRAPH}")
    G = ox.load_graphml(GRAPH)
    meta = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        if isinstance(nm, list):
            nm = nm[0]
        hw = d.get("highway")
        if isinstance(hw, list):
            hw = hw[0]
        meta[str((u, v, k))] = (str(nm), str(hw), float(d.get("length", 0)))

    lo, n_lo = load_arm(16500)
    hi, n_hi = load_arm(33000)
    print(f"seeds averaged: {n_lo} at 16,500 / {n_hi} at 33,000\n")

    def enrich(df):
        df = df.copy()
        info = [meta.get(str(i), ("?", "?", 0.0)) for i in df.index]
        df["name"] = [x[0] for x in info]
        df["hwy"] = [x[1] for x in info]
        df["len_m"] = [x[2] for x in info]
        # realized mean speed on the edge, km/h (same recovery as noise.py)
        with np.errstate(divide="ignore", invalid="ignore"):
            df["kmh"] = 3.6 * df["len_m"] * df["throughput"] / df["value"]
        return df

    lo, hi = enrich(lo), enrich(hi)

    print("=== worst bottlenecks at the CITED demand (16,500) ===")
    print("ranked by vehicle-seconds of occupancy; kmh is realized speed")
    top = lo.sort_values("value", ascending=False).head(15)
    for i, r in top.iterrows():
        print(f"  {r['value']:>10,.0f} veh-s  {r['kmh']:>5.1f} km/h  "
              f"{r['throughput']:>6,.0f} veh  {r['hwy']:<14} {r['name']}")

    print("\n=== where the EXTRA queueing goes as demand doubles ===")
    print("ranked by growth in occupancy, 16,500 -> 33,000")
    j = lo[["value", "name", "hwy", "kmh"]].join(
        hi[["value", "kmh"]], rsuffix="_hi", how="inner")
    j["growth"] = j["value_hi"] - j["value"]
    top = j.sort_values("growth", ascending=False).head(15)
    for i, r in top.iterrows():
        print(f"  +{r['growth']:>9,.0f} veh-s  {r['kmh']:>5.1f} -> "
              f"{r['kmh_hi']:>5.1f} km/h  {r['hwy']:<14} {r['name']}")

    # How much of the network ever congests at all, both demands.
    for label, df in (("16,500", lo), ("33,000", hi)):
        used = df[df["throughput"] > 0]
        slow = used[used["kmh"] < 10]
        print(f"\nat {label}: {len(used):,} edges carried traffic; "
              f"{len(slow):,} ({100 * len(slow) / len(used):.1f}%) "
              f"ran below 10 km/h; they hold "
              f"{100 * slow['value'].sum() / used['value'].sum():.1f}% "
              f"of all vehicle-time")


if __name__ == "__main__":
    main()
