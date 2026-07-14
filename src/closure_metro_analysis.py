"""Metro-scale closure analysis: difference the metro20k open/closed pair.

Read-only (single-source-of-truth rule): reads the two saved result files
(metro20k_open_segments.parquet / metro20k_closed_segments.parquet, produced
Jul 14 2026 by generate.py closure open half + run_closed_half.py closed half,
seed 42, 16,500 vehicles, LODES OD demand, 15% through-traffic) and the cached
20 km graph. Runs no simulation.

Reports the SE Powell closure's NO2 redistribution at two scopes:
  - near-zone: segments whose midpoint lies within 1500 m of the closure
    center. This matches the corridor runs' 1.5 km study radius, so these
    numbers are the apples-to-apples comparison against the corridor-scale
    closure results (ledger C1-C4).
  - full-metro: every matching street segment in the 20 km network. Included
    for context; a street like Powell runs ~20 km here, so this scope dilutes
    a 150 m closure by design and is expected to read small.

Also prints the network total change and the largest absolute NO2 movers near
the zone, to show where the detour traffic actually lands when the model has
the whole metro to reroute through (the corridor could only offer Division and
Holgate; the metro run gets to disagree).

Run:  python src/closure_metro_analysis.py
"""
import os
import sys

import numpy as np
import pandas as pd
import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import generate
from closure_robustness import name_of

ARTERIALS = ["Powell", "Division", "Holgate"]
NEAR_ZONE_M = 1500.0        # the corridor runs' study radius, for apples-to-apples
MOVERS_ZONE_M = 3000.0      # wider look for where detours land
TOP_N = 8


def load_pair():
    op = os.path.join(config.PROCESSED_DIR, "metro20k_open_segments.parquet")
    cp = os.path.join(config.PROCESSED_DIR, "metro20k_closed_segments.parquet")
    o = pd.read_parquet(op)[["u", "v", "key", "nox_g"]].rename(columns={"nox_g": "nox_open"})
    c = pd.read_parquet(cp)[["u", "v", "key", "nox_g"]].rename(columns={"nox_g": "nox_closed"})
    # outer merge: the 24 removed segments exist only in the open half; closed
    # NOx there is genuinely zero (no street, no emissions), so fill 0.
    df = o.merge(c, on=["u", "v", "key"], how="outer")
    df[["nox_open", "nox_closed"]] = df[["nox_open", "nox_closed"]].fillna(0.0)
    return df


def main():
    df = load_pair()
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))

    # street name and midpoint distance-to-closure for every segment
    name_by_edge = {(u, v, k): name_of(d) for u, v, k, d in G.edges(keys=True, data=True)}
    lat0, lon0, _ = config.CLOSURE
    ys = {n: float(G.nodes[n]["y"]) for n in G.nodes}
    xs = {n: float(G.nodes[n]["x"]) for n in G.nodes}
    keys = list(zip(df["u"], df["v"], df["key"]))
    df["street"] = [name_by_edge.get(k, "") for k in keys]
    df["dist_m"] = [
        generate._haversine_m(lat0, lon0,
                              0.5 * (ys[u] + ys[v]), 0.5 * (xs[u] + xs[v]))
        for u, v, _k in keys
    ]
    df["no2_open"] = config.F_NO2 * df["nox_open"]
    df["no2_closed"] = config.F_NO2 * df["nox_closed"]
    df["no2_delta"] = df["no2_closed"] - df["no2_open"]

    net_o, net_c = df["no2_open"].sum(), df["no2_closed"].sum()
    print(f"metro20k closure (seed {config.RANDOM_SEED}, {len(df)} segments)")
    print(f"network total NO2: open {net_o:.1f} g -> closed {net_c:.1f} g "
          f"({100 * (net_c - net_o) / net_o:+.2f}%)\n")

    def pct_change(sub):
        o, c = sub["no2_open"].sum(), sub["no2_closed"].sum()
        return (100 * (c - o) / o if o > 0 else np.nan), o, c

    print(f"{'arterial':<10} {'near-zone (<=1.5 km)':>24} {'full-metro street':>22}")
    for a in ARTERIALS:
        on_street = df["street"].str.contains(a, case=False, na=False)
        near, no, nc = pct_change(df[on_street & (df["dist_m"] <= NEAR_ZONE_M)])
        full, fo, fc = pct_change(df[on_street])
        print(f"{a:<10} {near:>+9.1f}%  ({no:8.1f} g) {full:>+9.1f}%  ({fo:9.1f} g)")

    movers = (df[df["dist_m"] <= MOVERS_ZONE_M]
              .groupby("street", as_index=False)
              .agg(no2_open=("no2_open", "sum"), delta=("no2_delta", "sum")))
    movers = movers[movers["street"] != ""]
    movers["pct"] = 100 * movers["delta"] / movers["no2_open"].replace(0, np.nan)

    print(f"\nlargest NO2 movers within {MOVERS_ZONE_M / 1000:.0f} km of the zone (grams):")
    print(f"{'street':<38} {'delta g':>9} {'pct':>8}")
    top = pd.concat([movers.nsmallest(TOP_N, "delta"), movers.nlargest(TOP_N, "delta")])
    for _, r in top.sort_values("delta").iterrows():
        pct = f"{r['pct']:+.0f}%" if np.isfinite(r["pct"]) else "new"
        print(f"{r['street']:<38} {r['delta']:>+9.1f} {pct:>8}")


if __name__ == "__main__":
    main()
