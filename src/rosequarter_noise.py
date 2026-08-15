"""CNOSSOS noise-change predictions for the pre-registered Rose Quarter I-5
SB closure (PREREG_I5_ROSEQUARTER.md, Appendix D).

Reads the fwrq campaign's saved per-segment parquets (both arms, 8 paired
seeds), builds the project's verified CNOSSOS v1 noise surface for each run
(src/noise.py: category-1 vehicles only, congestion-aware recovered speeds,
geometric divergence to a 10 m receiver), and computes paired closed-minus-
open corridor acoustic changes. No simulation runs.

Corridor metric: length-weighted energy total over the corridor's mainline
segments, E = sum(length_m * 10^(noise_db/10)), and the paired change
delta_dB = 10*log10(E_closed / E_open) per seed. The energy sum is how
incoherent sources combine, so this is "how much louder is the corridor as
a whole", robust to individual segments going quiet or silent. The closed
span itself is reported separately: its SB edges are removed in the closed
arm, so its energy goes to the NB carriageway only.

Known v1 limits, restated from noise.py and carried into the appendix: all
vehicles are CNOSSOS category 1 (cars); real freeway noise is raised by the
heavy vehicles this v1 does not model, so absolute dB(A) is understated and
the CHANGE is what is banked. Propagation is geometric divergence only.

    python src/rosequarter_noise.py --graph PATH --data-dir PATH [--out PATH]
"""
import argparse
import json
import os
import sys

import numpy as np
import osmnx as ox

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import generate        # noqa: E402
import noise           # noqa: E402
from freeway_rosequarter import SEEDS, EXPECTED_SB  # noqa: E402

CORRIDORS = ("I 405", "I 205", "I 5")


def corridor_energy(surface, edge_set):
    """Length-weighted acoustic energy over edge_set from one run's surface.
    Silent segments (NaN) contribute zero, which is physically what silence
    is."""
    m = [(u, v, k) in edge_set
         for u, v, k in zip(surface["u"], surface["v"], surface["key"])]
    sub = surface.loc[m]
    good = sub["noise_db"].notna() & sub["length_m"].notna()
    return float((sub.loc[good, "length_m"]
                  * 10.0 ** (sub.loc[good, "noise_db"] / 10.0)).sum())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph", required=True)
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    config.PROCESSED_DIR = args.data_dir
    print(f"loading graph {args.graph} ...")
    G = ox.load_graphml(args.graph)
    print(f"graph: {G.number_of_nodes():,} nodes / {G.number_of_edges():,} edges")
    noise.load_network = lambda: G      # one load serves all 16 surfaces

    mains = {ref: set(generate.freeway_mainline_edges(G, ref))
             for ref in CORRIDORS}
    span_sb = set(EXPECTED_SB)

    # per-seed, per-arm surfaces -> corridor energies
    energies = {}
    for seed in SEEDS:
        for arm in ("open", "rosequarter"):
            run = f"fwrq_{arm}_s{seed}"
            surf = noise.build_noise_surface(run)
            energies[(arm, seed)] = {ref: corridor_energy(surf, mains[ref])
                                     for ref in CORRIDORS}
            energies[(arm, seed)]["span SB"] = corridor_energy(surf, span_sb)
            print(f"  {run}: surfaces built")

    results = {}
    print(f"\n{'corridor':>10s} {'mean dB':>9s} {'sd':>6s} {'min':>7s} "
          f"{'max':>7s} {'signs':>7s}")
    for ref in CORRIDORS + ("span SB",):
        deltas = []
        for seed in SEEDS:
            eo = energies[("open", seed)][ref]
            ec = energies[("rosequarter", seed)][ref]
            if eo <= 0:
                continue
            if ec <= 0:
                deltas.append(float("-inf"))   # corridor went fully silent
                continue
            deltas.append(10.0 * np.log10(ec / eo))
        d = np.array(deltas)
        finite = d[np.isfinite(d)]
        pos = int((finite > 0).sum())
        if len(finite):
            print(f"{ref:>10s} {finite.mean():+9.2f} {finite.std(ddof=1):6.2f} "
                  f"{finite.min():+7.2f} {finite.max():+7.2f} "
                  f"{pos:3d}/{len(finite):<3d}"
                  + (f"  ({len(d) - len(finite)} seeds to silence)"
                     if len(d) != len(finite) else ""))
        results[ref] = {"delta_db": [None if not np.isfinite(x) else float(x)
                                     for x in d],
                        "mean_db": float(finite.mean()) if len(finite) else None,
                        "sd_db": float(finite.std(ddof=1)) if len(finite) > 1 else None,
                        "signs_pos": pos, "n_finite": len(finite), "n": len(d)}

    if args.out:
        with open(args.out, "w") as f:
            json.dump(results, f, indent=1)
        print(f"\nwritten -> {args.out}")


if __name__ == "__main__":
    main()
