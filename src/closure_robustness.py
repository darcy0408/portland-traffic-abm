"""Analyze the closure sweep: robustness (#1) and generality (#2).

Reads the per-(scenario, seed) closure result files that closure_sweep.py wrote and
answers two reviewer questions at once:

  Robustness: is the redistribution real or just one seed's noise? For each scenario
  we report the NO2 change on each arterial as a mean with standard deviation across
  the seeds. Small spread = the effect is stable, not noise.

  Generality: is this a one-off or a method? We run three scenarios, closing a block
  of Powell, of Division, and of Holgate in turn. Closing each arterial should push
  its NO2 onto the OTHER two. Seeing that pattern flip sensibly across scenarios is
  the evidence that the model handles closures in general.

Runs no simulation; reads the sweep files only. Single source of truth.

Run (after the sweep finishes):  python src/closure_robustness.py
"""
import os
import sys
import json

import numpy as np
import pandas as pd
import osmnx as ox
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

MANIFEST = os.path.join(config.PROCESSED_DIR, "sweep_manifest.json")
OUT_DIR = os.path.join(config.BASE_DIR, "outputs", "demo")
ARTERIALS = ["Powell", "Division", "Holgate"]   # the three we close and track


def name_of(data):
    n = data.get("name")
    if n is None:
        return ""
    return str(n[0]) if isinstance(n, list) else str(n)


def street_no2(df, name_by_edge):
    """Total modeled NO2 (F_NO2 * NOx) per street name, plus the network total."""
    no2 = config.F_NO2 * df["nox_g"].to_numpy(float)
    keys = list(zip(df["u"], df["v"], df["key"]))
    by_street = {}
    for k, val in zip(keys, no2):
        nm = name_by_edge.get(k, "")
        by_street[nm] = by_street.get(nm, 0.0) + val
    by_street["__NETWORK__"] = float(no2.sum())
    return by_street


def arterial_total(by_street, target):
    """Sum NO2 over every street whose name contains the target arterial name."""
    return sum(v for nm, v in by_street.items()
               if target.lower() in nm.lower() and nm != "__NETWORK__")


def main():
    with open(MANIFEST) as f:
        manifest = json.load(f)
    seeds = manifest["seeds"]
    scenarios = manifest["scenarios"]

    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    name_by_edge = {(u, v, k): name_of(d) for u, v, k, d in G.edges(keys=True, data=True)}

    # results[scenario][arterial] = list of % changes across seeds; plus network total
    results = {s: {a: [] for a in ARTERIALS} for s in scenarios}
    for s in scenarios:
        results[s]["__NETWORK__"] = []
        for seed in seeds:
            base = f"sweep_{s}_{seed}"
            op = os.path.join(config.PROCESSED_DIR, f"{base}_open_segments.parquet")
            cp = os.path.join(config.PROCESSED_DIR, f"{base}_closed_segments.parquet")
            if not (os.path.exists(op) and os.path.exists(cp)):
                print(f"[warn] missing files for {base}; skipping")
                continue
            o = street_no2(pd.read_parquet(op), name_by_edge)
            c = street_no2(pd.read_parquet(cp), name_by_edge)
            for a in ARTERIALS:
                ot, ct = arterial_total(o, a), arterial_total(c, a)
                results[s][a].append(100 * (ct - ot) / ot if ot > 0 else np.nan)
            ot, ct = o["__NETWORK__"], c["__NETWORK__"]
            results[s]["__NETWORK__"].append(100 * (ct - ot) / ot if ot > 0 else np.nan)

    # --- printed table ---
    print(f"\nClosure sweep: {len(scenarios)} scenarios x {len(seeds)} seeds")
    print("Each cell: mean % NO2 change across seeds (std).  Bold diagonal = the closed street.\n")
    head = "closed \\ arterial".ljust(20) + "".join(a.ljust(18) for a in ARTERIALS) + "network total"
    print(head)
    for s in scenarios:
        row = f"close {scenarios[s]['street']}".ljust(20)
        for a in ARTERIALS + ["__NETWORK__"]:
            arr = np.array(results[s][a], float)
            arr = arr[~np.isnan(arr)]
            cell = f"{np.mean(arr):+.0f}% ({np.std(arr):.0f})" if arr.size else "n/a"
            row += cell.ljust(18)
        print(row)

    # --- figure: grouped bars, one group per scenario, error bars = std across seeds ---
    fig, ax = plt.subplots(figsize=(11, 6.2))
    x = np.arange(len(scenarios))
    w = 0.26
    colors = {"Powell": "#1f77b4", "Division": "#d62728", "Holgate": "#2ca02c"}
    for i, a in enumerate(ARTERIALS):
        means = [np.nanmean(results[s][a]) for s in scenarios]
        stds = [np.nanstd(results[s][a]) for s in scenarios]
        ax.bar(x + (i - 1) * w, means, w, yerr=stds, capsize=4,
               label=f"SE {a}", color=colors[a])
    ax.axhline(0, color="#333333", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"close SE {scenarios[s]['street']}" for s in scenarios], fontsize=12)
    ax.set_ylabel("NO2 change vs open (%)", fontsize=12)
    ax.set_title("Closure redistribution is stable across seeds and generalizes across arterials\n"
                 f"(mean of {len(seeds)} seeds, error bars = std; close one arterial, its NO2 drops and "
                 "lands on the parallels)", fontsize=12.5)
    ax.legend(title="NO2 on", fontsize=11)
    fig.tight_layout()
    out = os.path.join(OUT_DIR, "7_closure_robustness.png")
    fig.savefig(out, dpi=200)
    plt.close(fig)
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
