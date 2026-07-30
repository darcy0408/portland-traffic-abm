"""Noise vs pollution under the realism stack, at metro scale — the contrast.

Analysis-only: reads the metrocal parquets (which carry the MEASURED
time-weighted speed sums v_sum, so mean speed needs no graph) plus the
Orca-run metro graph (data/network/graph_metro20k_orca.graphml — kept under
its own name; data/network/graph.graphml stays the corridor graph) for
Powell-edge identity only. Reuses src/noise.py's CNOSSOS functions; never
runs a sim.

The physics being contrasted, per segment at the SAME demand:
  NOx  is emitted per SECOND, so congestion (idling, stop-and-go) multiplies
       it — the realism stack, by clearing queues, cuts Powell NOx ~29% at
       high demand while carrying MORE cars.
  Noise is a LOG-energy quantity whose CNOSSOS flow term is 10*log10(Q/v):
       clearing a queue raises v (quieter per metre: cars spread out) but
       raises per-vehicle rolling noise with speed — the two mostly cancel,
       and the dB scale compresses what survives. Expect the noise surface
       to move by ~a dB where NOx moved by tens of percent.

Run: python src/metro_noise_contrast.py
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

import config
import noise

METRO_GRAPH = os.path.join(config.NETWORK_DIR, "graph_metro20k_orca.graphml")
SEEDS = [42, 7, 13, 99, 2024, 314, 777, 8]
DEMANDS = [16500, 24750, 33000]


def powell_edges():
    import osmnx as ox
    G = ox.load_graphml(METRO_GRAPH)
    out = set()
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        names = nm if isinstance(nm, list) else [nm]
        if any(n and "powell" in str(n).lower() for n in names):
            out.add((u, v, k))
    return out


def surface(run_name):
    """Per-segment dB(A) from the parquet's own measured mean speed
    (v_sum/value) and hourly flow (throughput / sim-hours = throughput here,
    hour runs). Returns df indexed by (u,v,key) with noise_db + nox_g."""
    df = noise.load_run_segments(run_name).copy()
    flowing = (df["throughput"] > 0) & (df["value"] > 0)
    v_kph = np.where(flowing, df["v_sum"] / df["value"].where(df["value"] > 0) * 3.6,
                     np.nan)
    out = np.full(len(df), np.nan)
    for i, (q, v) in enumerate(zip(df["throughput"].to_numpy(), v_kph)):
        if q > 0 and np.isfinite(v) and v > 0:
            lwa = noise.segment_line_power_dba(float(q), float(v))
            if lwa is not None:
                out[i] = noise.propagate_line(lwa)
    df["noise_db"] = out
    return df.set_index(["u", "v", "key"])[["noise_db", "nox_g"]]


def main():
    pw = powell_edges()
    print(f"{len(pw)} Powell edges in the metro graph\n")
    print(f"{'demand':>7} {'seeds':>5} | {'Powell NOx delta':>17} | "
          f"{'Powell noise median delta':>25} | {'network noise median delta':>26}")
    for n in DEMANDS:
        nox_d, noi_pw, noi_net = [], [], []
        for seed in SEEDS:
            try:
                b = surface(f"metrocal_base_n{n}_s{seed}")
                r = surface(f"metrocal_realism_n{n}_s{seed}")
            except SystemExit:
                continue
            j = b.join(r, lsuffix="_b", rsuffix="_r")
            is_pw = pd.Series([t in pw for t in j.index], index=j.index)
            # NOx: percent change on Powell (sums, so zero-flow segments count)
            nox_d.append(100 * (j.loc[is_pw, "nox_g_r"].sum()
                                / j.loc[is_pw, "nox_g_b"].sum() - 1))
            # noise: per-segment dB delta where BOTH runs have flow (a dB delta
            # needs a level on both sides), median over segments
            both = j["noise_db_b"].notna() & j["noise_db_r"].notna()
            d = (j["noise_db_r"] - j["noise_db_b"])[both]
            noi_pw.append(d[is_pw[both]].median())
            noi_net.append(d.median())
        if not nox_d:
            continue
        print(f"{n:>7,} {len(nox_d):>5} | "
              f"{np.mean(nox_d):+9.1f}% ± {np.std(nox_d, ddof=1):.1f} | "
              f"{np.mean(noi_pw):+9.2f} dB ± {np.std(noi_pw, ddof=1):.2f}   | "
              f"{np.mean(noi_net):+9.2f} dB ± {np.std(noi_net, ddof=1):.2f}")


if __name__ == "__main__":
    main()
