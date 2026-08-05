"""Road-class-only baseline for the traffic validation (Christof review item 4).

THE OBJECTION IT ANSWERS: Spearman 0.59 against PBOT ADT could be dominated by
the arterial-vs-local split, which the OSM `highway` tag nearly determines. If
ranking segments by road class ALONE lands near 0.59, the ABM's dynamics added
little to the validation number; if it lands well below, the 0.59 carries real
information beyond network structure. Either answer belongs in the chapter, and
this also removes the reliance on the McDonald thesis for that context.

Analysis-only: reads the committed powell_through count-validation parquet
(built by src/validate_traffic.py: geometry-snapped PBOT counts, one row per
matched segment) + the segments parquet + the cached corridor graph. Never runs
a sim. The class ordinal is generate.DEFAULT_KPH -- the committed a-priori
speed-by-class table -- so this script introduces no new tunable choice; a
`maxspeed`-tagged edge still ranks by its CLASS default (the baseline must be
structure-only, not speed-limit-aware).

Run: python src/roadclass_baseline.py
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import osmnx as ox
import pandas as pd
from scipy import stats

import config
from generate import DEFAULT_KPH

RUN = "powell_through"


def class_rank(highway_attr):
    """Ordinal for the segment's road class: the committed DEFAULT_KPH value
    for its OSM highway tag (lists take their first entry; unknown tags get
    the residential-level default)."""
    hw = highway_attr if isinstance(highway_attr, list) else [highway_attr]
    tag = str(hw[0]) if hw and hw[0] else "residential"
    return DEFAULT_KPH.get(tag, DEFAULT_KPH.get("residential", 40))


def main():
    val = pd.read_parquet(os.path.join(config.PROCESSED_DIR,
                                       f"{RUN}_count_validation.parquet"))
    abm = pd.read_parquet(os.path.join(config.PROCESSED_DIR,
                                       f"{RUN}_segments.parquet"))
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    hw = {(u, v, k): d.get("highway") for u, v, k, d in G.edges(keys=True, data=True)}

    seg_idx = val["seg"].to_numpy()
    keys = [(abm["u"].iat[i], abm["v"].iat[i], abm["key"].iat[i]) for i in seg_idx]
    val["class_rank"] = [class_rank(hw.get(kk)) for kk in keys]

    rho_class = stats.spearmanr(val["adt"], val["class_rank"]).statistic
    rho_abm = stats.spearmanr(val["adt"], val["throughput"]).statistic
    n_classes = val["class_rank"].nunique()

    print(f"Road-class baseline on the {RUN} validation set "
          f"({len(val)} matched segments, {n_classes} distinct class levels)")
    print(f"  Spearman(real ADT, road-class ordinal alone): {rho_class:+.3f}")
    print(f"  Spearman(real ADT, ABM throughput)  [same segments]: {rho_abm:+.3f}")
    print(f"  gap (ABM - class-only): {rho_abm - rho_class:+.3f}")
    print("\nReading: if the class-only number sits near the ABM's, structure")
    print("explains the validation; a large gap means the simulated dynamics")
    print("rank streets beyond what the road hierarchy already encodes.")


if __name__ == "__main__":
    main()
