"""Phase 2 probes (CALIBRATED_DEMAND_PLAN.md): can the diagnosed levers push
Powell to its REAL peak volume (1,400-1,745 veh/hr directional) without
gridlocking the network?

Phase 1 found: Powell itself never chokes -- SE Division and SE Cesar Chavez
saturate first at their signals (uniform 60s/50-50 green halves a signalized
single-lane street's discharge), and their spillback strangles the network.
So the two levers under test, at N=1500 with real lanes on (seed 42):

  probe_T50           through-traffic 0.30 -> 0.50   (real Powell is through-
  probe_T70           through-traffic 0.30 -> 0.70    dominated; through trips
                                                      ride the fast arterial
                                                      instead of clogging the
                                                      side streets)
  probe_T30_webster   Webster per-node signal timing (heavy approaches earn
  probe_T50_webster   more green -> unchokes the Division/Chavez signals)

Baseline for comparison: lanepoll_2lane_n1500_s42 (T=0.30, uniform signals),
already on disk from the Jul 27 sweep. Each probe prints busiest-Powell
throughput + jam distribution so the winning lever is visible immediately.

Discipline: sequential in one process, unique RUN_NAMEs, seed recorded, all
overrides visible here; analysis reads the parquets after.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import osmnx as ox

import config
import generate

BASE = {
    "STUDY_RADIUS_M": 1500, "N_STEPS": 3600, "N_VEHICLES": 1500,
    "DEMAND_LODES_OD": False, "DEMAND_GRAVITY": True,
    "LANES_ENABLED": True, "MOBIL_ENABLED": False,
    "DRIVER_HETEROGENEITY": False, "RANDOM_SEED": 42,
}

PROBES = [
    ("probe_T50",         {"THROUGH_TRAFFIC_FRACTION": 0.50, "WEBSTER_ENABLED": False}),
    ("probe_T70",         {"THROUGH_TRAFFIC_FRACTION": 0.70, "WEBSTER_ENABLED": False}),
    ("probe_T30_webster", {"THROUGH_TRAFFIC_FRACTION": 0.30, "WEBSTER_ENABLED": True}),
    ("probe_T50_webster", {"THROUGH_TRAFFIC_FRACTION": 0.50, "WEBSTER_ENABLED": True}),
]


def summarize(name, G, nox, thru, totals):
    """Powell busiest + jam picture, computed like gridlock_diagnosis.py."""
    jam_by_street, powell_busy, powell_jam = {}, 0.0, 0.0
    for (u, v, k), sec in totals.items():
        if sec <= 0:
            continue
        d = G.get_edge_data(u, v, k) or {}
        length = float(d.get("length", 10.0))
        t = thru.get((u, v, k), 0.0)
        kmh = t * length / sec * 3.6 if sec > 0 else float("nan")
        nm = d.get("name")
        if isinstance(nm, list):
            nm = nm[0] if nm else None
        nm = str(nm) if nm else "(unnamed)"
        is_pow = "powell" in nm.lower()
        if is_pow:
            powell_busy = max(powell_busy, t)
        if kmh == kmh and kmh < 5.0:
            jam_by_street[nm] = jam_by_street.get(nm, 0.0) + sec / 3600.0
            if is_pow:
                powell_jam += sec / 3600.0
    tot_jam = sum(jam_by_street.values())
    top = sorted(jam_by_street.items(), key=lambda x: -x[1])[:3]
    print(f"\n{name}: busiest POWELL {powell_busy:.0f} veh/hr | "
          f"network jam {tot_jam:.0f} veh-h (Powell {powell_jam:.0f})")
    for st, v in top:
        print(f"    jam: {st[:40]:40s} {v:6.1f} veh-h")


def main():
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    for name, over in PROBES:
        for k, v in {**BASE, **over}.items():
            setattr(config, k, v)
        config.RUN_NAME = name
        out = os.path.join(config.PROCESSED_DIR, f"{name}_segments.parquet")
        if os.path.exists(out):
            print(f"SKIP {name} (on disk)")
            continue
        G = ox.load_graphml(graph_file)
        generate.set_seeds(config.RANDOM_SEED)
        totals, nox, thru = generate.run_simulation(G, verbose=False,
                                                    use_checkpoint=False)
        generate.save_results(totals, nox, thru)
        summarize(name, G, nox, thru, totals)
    print("\nBaseline for comparison (from the Jul 27 sweep): "
          "lanepoll_2lane_n1500_s42 -- busiest Powell ~1,269, network jam ~819 veh-h. "
          "Real target: 1,400-1,745 veh/hr with the network still flowing.")


if __name__ == "__main__":
    main()
