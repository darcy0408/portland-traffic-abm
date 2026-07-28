"""Phase 1 of CALIBRATED_DEMAND_PLAN.md: WHY does the model gridlock below real
Powell peak volume even with real lane counts?

Analysis-only: reads the 96 lanepoll_* parquets (Jul 27 overnight sweep) plus
the cached corridor graph. No simulation.

Method: per-segment mean traversal speed is estimated as
    mean_speed = throughput * length / value
(throughput = full traversals/hr, value = vehicle-seconds on the segment over
the hour; the ratio is distance-driven / time-spent, exact for completed
traversals and approximate when many vehicles end mid-segment -- fine for a
jam MAP). A segment is "jammed" when its mean speed is under 5 km/h and it
holds real vehicle-time. We then ask, for the 2-lane arm as demand rises:
  1. WHERE does jammed vehicle-time live (Powell? its cross streets? side
     streets everywhere?) -- named-street ranking.
  2. Does POWELL's own flow keep rising while the network around it collapses
     (routing/demand problem), or does Powell itself choke (corridor problem)?
"""
import glob
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd

import config

NAME_RE = re.compile(r"lanepoll_(1lane|2lane)_n(\d+)_s(\d+)_segments\.parquet$")
JAM_KMH = 5.0


def edge_meta():
    """(u,v,key) -> (length_m, street_name) from the cached corridor graph."""
    import osmnx as ox
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    meta = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        if isinstance(nm, list):
            nm = nm[0] if nm else None
        meta[(u, v, k)] = (float(d.get("length", 10.0)), str(nm) if nm else "(unnamed)")
    return meta


def main():
    meta = edge_meta()
    files = glob.glob(os.path.join(config.PROCESSED_DIR, "lanepoll_2lane_*_segments.parquet"))
    if not files:
        raise SystemExit("no lanepoll_2lane_* runs on disk")

    frames = []
    for f in files:
        m = NAME_RE.search(os.path.basename(f))
        d = pd.read_parquet(f)
        d["n_veh"] = int(m.group(2))
        d["seed"] = int(m.group(3))
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["length"] = [meta.get((r.u, r.v, r.key), (10.0, ""))[0] for r in d.itertuples()]
    d["street"] = [meta.get((r.u, r.v, r.key), (0, "(unknown)"))[1] for r in d.itertuples()]
    # mean traversal speed (km/h); segments with no time get NaN
    with np.errstate(divide="ignore", invalid="ignore"):
        d["kmh"] = np.where(d.value > 0, d.throughput * d.length / d.value * 3.6, np.nan)
    d["veh_h"] = d.value / 3600.0                     # vehicle-hours on segment
    d["jam_veh_h"] = np.where(d.kmh < JAM_KMH, d.veh_h, 0.0)
    d["is_powell"] = d.street.str.contains("Powell", case=False, na=False)

    print(f"loaded {d.seed.nunique()} seeds x {sorted(d.n_veh.unique())} demands "
          f"(2-lane arm)\n")

    # --- Q1: where does jammed vehicle-time live as demand rises? -----------
    print("=== jammed vehicle-hours (mean speed < 5 km/h), by street, mean over seeds ===")
    for n in sorted(d.n_veh.unique()):
        sub = d[d.n_veh == n]
        per_seed = sub.groupby("seed").jam_veh_h.sum()
        by_street = (sub.groupby("street").jam_veh_h.sum() / sub.seed.nunique())
        top = by_street.sort_values(ascending=False).head(5)
        tot = per_seed.mean()
        alltime = sub.groupby("seed").veh_h.sum().mean()
        print(f"\n demand {n}: jammed {tot:6.0f} veh-h of {alltime:6.0f} total "
              f"({100*tot/alltime:4.1f}%)")
        for st, v in top.items():
            if v > 0.5:
                print(f"    {st[:44]:44s} {v:7.1f} veh-h")

    # --- Q2: Powell's own flow vs the network around it ---------------------
    print("\n=== Powell corridor vs demand (2-lane, mean over seeds) ===")
    print(f"  {'demand':>6} | {'Powell thru (busiest)':>21} | {'Powell veh-h':>12} | "
          f"{'Powell jam veh-h':>16} | {'network jam veh-h':>17}")
    for n in sorted(d.n_veh.unique()):
        sub = d[d.n_veh == n]
        ns = sub.seed.nunique()
        pow_busy = sub[sub.is_powell].groupby("seed").throughput.max().mean()
        pow_vh = sub[sub.is_powell].groupby("seed").veh_h.sum().mean()
        pow_jam = sub[sub.is_powell].groupby("seed").jam_veh_h.sum().mean()
        net_jam = sub[~sub.is_powell].groupby("seed").jam_veh_h.sum().mean()
        print(f"  {n:>6} | {pow_busy:>21.0f} | {pow_vh:>12.1f} | "
              f"{pow_jam:>16.1f} | {net_jam:>17.1f}")

    print("\nReading: if Powell's busiest keeps rising and its jam stays small while "
          "the NETWORK jam column explodes, the constraint is demand/routing around "
          "Powell (side-street loading), not Powell capacity -- the calibration lever "
          "is through-traffic structure, not lanes.")


if __name__ == "__main__":
    main()
