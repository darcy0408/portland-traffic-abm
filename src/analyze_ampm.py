"""Analyze the directional AM/PM commute day experiment (worktree experiment/ampm).

EXPLORATORY. Reads the two saved 24-hour day runs (no simulation, per the
single-source-of-truth rule) and measures what directional commute demand changes:

  symmetric baseline : powell_no2_day     (gravity demand, no through-traffic,
                                           same home->work draw at every hour)
  directional run    : powell_day_ampm    (gravity + 30% through-traffic, AM
                                           home->work, PM reversed work->home)

CONFOUND, stated up front: the two runs differ in BOTH directionality and
through-traffic (the symmetric day run predates through-traffic). The clean
directional measurement is therefore the WITHIN-run AM-vs-PM asymmetry (section b),
because through-traffic draws its boundary endpoints the same way at every hour and
so cannot create an AM/PM asymmetry by itself. Between-run level differences mix
the two changes and are labeled as such.

Measurements:
  (a) face validity: realized hourly throughput share vs the input PORTAL profile
      share (the validate_day Spearman), for both runs.
  (b) directional asymmetry on SE Powell Boulevard: eastbound vs westbound
      throughput in the AM window vs the PM window, both runs. Directionality
      should make the AM ratio and the PM ratio move in opposite directions
      (a flow reversal); the symmetric run should show none.
  (c) congestion nonlinearity: per-vehicle NO2 in the AM and PM peak windows and
      the quiet hour, both runs.
  (d) EVALUATION ONLY: Spearman rank correlation of each run's summed daily
      throughput vs the held-out PBOT counts, using validate_traffic.py's
      corrected geometry snapping. The counts are a held-out evaluation metric;
      nothing in the experiment was tuned against them.

Run it with:  python src/analyze_ampm.py
"""
import os
import sys

import numpy as np
import pandas as pd
import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import demand_data
import validate_traffic

SYM_RUN = "powell_no2"         # symmetric baseline day run (file powell_no2_day_segments.parquet)
DIR_RUN = "powell_day_ampm"    # the directional experiment run
AM = tuple(config.AM_PEAK_HOURS)
PM = tuple(config.PM_PEAK_HOURS)


def _spearman(a, b):
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def _load_day(run):
    path = os.path.join(config.PROCESSED_DIR, f"{run}_day_segments.parquet")
    if not os.path.exists(path):
        raise SystemExit(f"missing {path}; run the day experiment first")
    return pd.read_parquet(path)


def face_validity(df, label):
    """(a) hourly throughput share vs the input profile share, as in validate_day."""
    profile = pd.Series(demand_data.hourly_demand_profile(), index=range(24))
    thru = df.groupby("hour")["throughput"].sum().reindex(range(24))
    p = (profile / profile.sum()).to_numpy()
    t = (thru / thru.sum()).to_numpy()
    rho = _spearman(t, p)
    r = float(np.corrcoef(t, p)[0, 1])
    print(f"  {label:<28} Spearman {rho:+.3f}   Pearson {r:+.3f}")
    return rho


def powell_directional(df, G, label):
    """(b) SE Powell eastbound vs westbound throughput, AM vs PM windows.

    Powell is mapped as one-way carriageway pairs, so each directed edge carries one
    travel direction. Eastbound = the downstream node lies east (larger longitude)
    of the upstream node. The frontage road is excluded."""
    powell = set()
    eastbound = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        name = d.get("name")
        if isinstance(name, list):
            name = name[0]
        if str(name) == "Southeast Powell Boulevard":
            powell.add((u, v, k))
            eastbound[(u, v, k)] = float(G.nodes[v]["x"]) > float(G.nodes[u]["x"])

    df = df.copy()
    df["edge"] = list(zip(df["u"], df["v"], df["key"]))
    pw = df[df["edge"].isin(powell)]
    out = {}
    for win, hours in (("AM", AM), ("PM", PM)):
        w = pw[pw["hour"].isin(hours)]
        eb = w[w["edge"].map(eastbound)]["throughput"].sum()
        wb = w[~w["edge"].map(eastbound)]["throughput"].sum()
        ratio = eb / wb if wb > 0 else float("nan")
        out[win] = (eb, wb, ratio)
        print(f"  {label:<28} {win} (hours {hours}): eastbound {eb:8.0f}  "
              f"westbound {wb:8.0f}  EB/WB {ratio:.3f}")
    rev = out["AM"][2] / out["PM"][2] if out["PM"][2] else float("nan")
    print(f"  {label:<28} reversal index (AM ratio / PM ratio): {rev:.3f}  "
          f"(1.0 = no AM/PM directional difference)")
    return out


def per_vehicle_no2(df, label):
    """(c) per-vehicle NO2 by hour: congestion intensity in the AM/PM windows."""
    g = df.groupby("hour")
    no2 = config.F_NO2 * g["nox_g"].sum()
    nveh = g["n_vehicles"].first()
    pv = (no2 / nveh).reindex(range(24))
    quiet_h = int(no2.idxmin())
    am, pm = float(pv[list(AM)].mean()), float(pv[list(PM)].mean())
    quiet = float(pv[quiet_h])
    print(f"  {label:<28} AM mean {am:.2f} g/veh   PM mean {pm:.2f} g/veh   "
          f"quiet {quiet_h:02d}:00 {quiet:.2f} g/veh   "
          f"AM lift {100*(am/quiet-1):+.0f}%   PM lift {100*(pm/quiet-1):+.0f}%")
    return pv


def daily_eval(df, run, label):
    """(d) EVALUATION ONLY: summed daily throughput vs the held-out PBOT counts,
    through validate_traffic's corrected geometry snapping. Writes a
    {run}_daily_segments.parquet so validate_traffic can read it unchanged."""
    daily = (df.groupby(["u", "v", "key"], as_index=False)
             [["value", "nox_g", "throughput"]].sum())
    name = f"{run}_daily"
    daily.to_parquet(os.path.join(config.PROCESSED_DIR, f"{name}_segments.parquet"),
                     index=False)
    print(f"\n  [{label}]")
    validate_traffic.main(name)
    per_seg = pd.read_parquet(
        os.path.join(config.PROCESSED_DIR, f"{name}_count_validation.parquet"))
    return _spearman(per_seg["adt"], per_seg["throughput"])


if __name__ == "__main__":
    sym = _load_day(SYM_RUN)
    dr = _load_day(DIR_RUN)
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))

    print("EXPLORATORY AM/PM directional demand analysis (worktree experiment/ampm)")
    print(f"symmetric baseline: {SYM_RUN} (gravity only, no through-traffic)")
    print(f"directional run:    {DIR_RUN} (gravity + 30% through, AM {AM} home->work, "
          f"PM {PM} reversed)\n")

    print("(a) Face validity: hourly throughput share vs input PORTAL profile share")
    face_validity(sym, SYM_RUN)
    face_validity(dr, DIR_RUN)

    print("\n(b) SE Powell directional asymmetry (within-run, the clean measurement)")
    powell_directional(sym, G, SYM_RUN)
    powell_directional(dr, G, DIR_RUN)

    print("\n(c) Per-vehicle NO2 (congestion intensity), AM vs PM windows")
    pv_sym = per_vehicle_no2(sym, SYM_RUN)
    pv_dir = per_vehicle_no2(dr, DIR_RUN)

    print("\n(d) EVALUATION ONLY: daily throughput vs held-out PBOT counts "
          "(corrected geometry snapping)")
    rho_sym = daily_eval(sym, SYM_RUN, SYM_RUN)
    rho_dir = daily_eval(dr, DIR_RUN, DIR_RUN)
    print(f"\n  summary: daily-throughput Spearman vs PBOT counts: "
          f"{SYM_RUN} {rho_sym:+.3f}   {DIR_RUN} {rho_dir:+.3f}")
    print("  NOTE: this between-run difference mixes directionality AND "
          "through-traffic (the baseline predates through-traffic); it is an "
          "evaluation readout, not a tuning target.")
