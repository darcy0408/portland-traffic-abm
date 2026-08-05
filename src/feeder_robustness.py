"""Which upstream feeder streets robustly lose traffic-NO2 under the metro
SE Powell closure? Read-only, no simulation.

Motivation: ledger M20.14 cites three upstream feeders (Grand Ave -40%,
McLoughlin -9%, Ross Island Bridge -14%) from the SINGLE seed-42 all-diesel
pair. The mixed-fleet seed-42 pair flips the Ross Island Bridge to +29%, so the
per-street feeder claim needs the same 12-seed treatment the arterials got
(M20.15 / M20.17) before any of it goes on a slide.

Reads the 12 saved mixed-fleet sweep pairs (sweepmix_powell_<seed>_{open,closed})
and reports, per street within 3 km of the closure zone, the mean gram delta and
how many of the 12 seeds agree on the sign. Sign agreement is the gate: a feeder
is citable only if it moves the same way on all 12.
"""
import os
import sys

import numpy as np
import pandas as pd
import osmnx as ox

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)))
REPO = r"C:\dev\portland-traffic-abm"
sys.path.append(os.path.join(REPO, "src"))
sys.path.append(REPO)

import config
import generate
from closure_robustness import name_of
from mixed_rerun import apply_metro_dirs

SEEDS = [42, 7, 13, 21, 99, 2024, 1, 5, 8, 100, 314, 777]   # the fixed Jul 2 list
ZONE_M = 3000.0     # same scope as closure_metro_analysis's movers table


def main():
    apply_metro_dirs()
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))

    # street name + midpoint distance to the closure center, computed once
    name_by_edge = {(u, v, k): name_of(d) for u, v, k, d in G.edges(keys=True, data=True)}
    lat0, lon0, _ = config.CLOSURE
    ys = {n: float(G.nodes[n]["y"]) for n in G.nodes}
    xs = {n: float(G.nodes[n]["x"]) for n in G.nodes}

    per_seed = {}
    for seed in SEEDS:
        base = f"sweepmix_powell_{seed}"
        op = os.path.join(config.PROCESSED_DIR, f"{base}_open_segments.parquet")
        cp = os.path.join(config.PROCESSED_DIR, f"{base}_closed_segments.parquet")
        if not (os.path.exists(op) and os.path.exists(cp)):
            print(f"  MISSING pair for seed {seed}, skipped")
            continue
        o = pd.read_parquet(op)[["u", "v", "key", "nox_g"]].rename(columns={"nox_g": "o"})
        c = pd.read_parquet(cp)[["u", "v", "key", "nox_g"]].rename(columns={"nox_g": "c"})
        df = o.merge(c, on=["u", "v", "key"], how="outer")
        df[["o", "c"]] = df[["o", "c"]].fillna(0.0)

        keys = list(zip(df["u"], df["v"], df["key"]))
        df["street"] = [name_by_edge.get(k, "") for k in keys]
        df["dist_m"] = [
            generate._haversine_m(lat0, lon0, 0.5 * (ys[u] + ys[v]), 0.5 * (xs[u] + xs[v]))
            for u, v, _k in keys
        ]
        df = df[(df["dist_m"] <= ZONE_M) & (df["street"] != "")]
        # NO2 = F_NO2 * NOx, applied here exactly as the other analyses do
        g = df.groupby("street").apply(
            lambda s: pd.Series({
                "open_g": config.F_NO2 * s["o"].sum(),
                "delta_g": config.F_NO2 * (s["c"].sum() - s["o"].sum()),
            }), include_groups=False)
        per_seed[seed] = g
        print(f"  seed {seed}: {len(g)} named streets within {ZONE_M/1000:.0f} km")

    streets = sorted(set().union(*[set(g.index) for g in per_seed.values()]))
    rows = []
    for st in streets:
        d = np.array([per_seed[s]["delta_g"].get(st, 0.0) for s in per_seed])
        o = np.array([per_seed[s]["open_g"].get(st, 0.0) for s in per_seed])
        n_neg, n_pos = int((d < 0).sum()), int((d > 0).sum())
        with np.errstate(divide="ignore", invalid="ignore"):
            pct = np.where(o > 0, 100.0 * d / o, np.nan)
        rows.append({
            "street": st,
            "mean_open_g": o.mean(),
            "mean_delta_g": d.mean(),
            "std_delta_g": d.std(),
            "mean_pct": np.nanmean(pct) if np.isfinite(pct).any() else np.nan,
            "n_down": n_neg,
            "n_up": n_pos,
            "agree": max(n_neg, n_pos),
        })
    res = pd.DataFrame(rows)
    n = len(per_seed)

    print(f"\n=== FEEDERS THAT DROP ON ALL {n} SEEDS (mixed fleet, within 3 km) ===")
    print(f"{'street':<40} {'mean delta g':>13} {'mean %':>8} {'open g':>9} {'down/12':>8}")
    drop = res[(res["n_down"] == n)].nsmallest(12, "mean_delta_g")
    for _, r in drop.iterrows():
        print(f"{r['street']:<40} {r['mean_delta_g']:>+13.1f} {r['mean_pct']:>+7.0f}% "
              f"{r['mean_open_g']:>9.1f} {r['n_down']:>5}/{n}")

    print(f"\n=== RISES ON ALL {n} SEEDS ===")
    print(f"{'street':<40} {'mean delta g':>13} {'mean %':>8} {'open g':>9} {'up/12':>8}")
    rise = res[(res["n_up"] == n)].nlargest(10, "mean_delta_g")
    for _, r in rise.iterrows():
        pct = f"{r['mean_pct']:+.0f}%" if np.isfinite(r["mean_pct"]) else "new"
        print(f"{r['street']:<40} {r['mean_delta_g']:>+13.1f} {pct:>8} "
              f"{r['mean_open_g']:>9.1f} {r['n_up']:>5}/{n}")

    print(f"\n=== THE M20.14 CITED FEEDERS, SEED BY SEED ===")
    for st in ["Southeast Grand Avenue", "Southeast McLoughlin Boulevard",
               "Ross Island Bridge", "Southeast Foster Road"]:
        r = res[res["street"] == st]
        if r.empty:
            print(f"{st}: not found")
            continue
        r = r.iloc[0]
        verdict = "ROBUST" if r["agree"] == n else f"NOT ROBUST ({r['n_down']} down / {r['n_up']} up)"
        print(f"{st:<40} mean {r['mean_delta_g']:>+8.1f} g "
              f"({r['mean_pct']:>+5.0f}%)  {verdict}")


if __name__ == "__main__":
    main()
