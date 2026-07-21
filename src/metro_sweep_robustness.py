"""Metro closure robustness: aggregate the 12-seed Powell sweep.

The metro variant of closure_robustness.py that run_metro_sweep.py's docstring
promises. Read-only (single-source-of-truth rule): reads the 12 seed pairs the
overnight sweep wrote (sweep_powell_<seed>_{open,closed}_segments.parquet,
finished Jul 15 2026 04:07) plus the cached 20 km graph. Runs no simulation.

Question it answers: is the metro-scale closure redistribution (M20.14, a
single seed) stable across seeds, or one seed's noise? Same bar the mentor set
Jul 2 for the corridor result (12 seeds, report every seed, mean with std).

Scope choices copied from closure_metro_analysis.py so the numbers are
comparable: per-arterial changes are reported in the near zone (segment
midpoint <= 1.5 km of the closure center), the corridor runs' study radius,
which is the apples-to-apples frame against the corridor sweep (ledger C6).
The full-metro street scope dilutes a 150 m closure by design, so it is not
aggregated here.

Run:  python src/metro_sweep_robustness.py
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

SEEDS = [42, 7, 13, 21, 99, 2024, 1, 5, 8, 100, 314, 777]  # run_metro_sweep.py's fixed list
ARTERIALS = ["Powell", "Division", "Holgate"]
NEAR_ZONE_M = 1500.0


def edge_lookup():
    """Street name and distance-to-closure per edge, computed once (the graph
    is identical for every seed; only demand draws differ)."""
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    lat0, lon0, _ = config.CLOSURE
    rows = []
    for u, v, k, d in G.edges(keys=True, data=True):
        ym = 0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"]))
        xm = 0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"]))
        rows.append((u, v, k, name_of(d),
                     generate._haversine_m(lat0, lon0, ym, xm)))
    return pd.DataFrame(rows, columns=["u", "v", "key", "street", "dist_m"])


def load_pair(seed, prefix="sweep_powell"):
    base = os.path.join(config.PROCESSED_DIR, f"{prefix}_{seed}")
    o = pd.read_parquet(f"{base}_open_segments.parquet")[["u", "v", "key", "nox_g"]]
    c = pd.read_parquet(f"{base}_closed_segments.parquet")[["u", "v", "key", "nox_g"]]
    df = (o.rename(columns={"nox_g": "nox_open"})
           .merge(c.rename(columns={"nox_g": "nox_closed"}), on=["u", "v", "key"], how="outer"))
    # the 24 removed segments exist only in the open half; closed NOx there is
    # genuinely zero (no street, no emissions)
    return df.fillna({"nox_open": 0.0, "nox_closed": 0.0})


def main(prefix="sweep_powell"):
    # a prefix argument selects a sweep variant (e.g. "sweepmix_powell" for the
    # mixed-fleet sweep); the data dirs follow the metro caches (worktree when
    # running from the main checkout, defaults when running inside the worktree)
    from mixed_rerun import apply_metro_dirs
    apply_metro_dirs()
    edges = edge_lookup()
    per_seed = []
    for seed in SEEDS:
        pair = os.path.join(config.PROCESSED_DIR, f"{prefix}_{seed}")
        if not (os.path.exists(f"{pair}_open_segments.parquet")
                and os.path.exists(f"{pair}_closed_segments.parquet")):
            print(f"[warn] seed {seed}: pair incomplete, skipping")
            continue
        df = load_pair(seed, prefix).merge(edges, on=["u", "v", "key"], how="left")
        no2_o = config.F_NO2 * df["nox_open"]
        no2_c = config.F_NO2 * df["nox_closed"]
        row = {"seed": seed,
               "net_pct": 100 * (no2_c.sum() - no2_o.sum()) / no2_o.sum()}
        near = df["dist_m"] <= NEAR_ZONE_M
        for a in ARTERIALS:
            m = near & df["street"].str.contains(a, case=False, na=False)
            o, c = no2_o[m].sum(), no2_c[m].sum()
            row[a] = 100 * (c - o) / o if o > 0 else np.nan
        per_seed.append(row)

    t = pd.DataFrame(per_seed)
    print(f"{prefix} closure, {len(t)} seeds, near zone <= {NEAR_ZONE_M / 1000:.1f} km")
    print(t.to_string(index=False, float_format=lambda x: f"{x:+.1f}"))
    print("\nacross seeds (mean +/- std):")
    for col in ARTERIALS + ["net_pct"]:
        print(f"  {col:<10} {t[col].mean():+6.1f}%  +/- {t[col].std():.1f}"
              f"   (range {t[col].min():+.1f} to {t[col].max():+.1f})")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sweep_powell")
