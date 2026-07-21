"""How much of the traffic-validation Spearman gap comes from noise in the PBOT
reference counts themselves? (Read-only: reads saved runs, runs no simulation.)

The counts span 2010-2026 and are averaged per segment with no year filter. This
script reuses validate_traffic.py's geometry snapping (SNAP_MAX_M = 40 m), then asks
three questions of the ALREADY-SAVED data:

  1. does restricting to recent years raise rho? (paired with a sample-size control,
     because narrowing the years also shrinks the sample, and small samples alone
     move rho)
  2. how much do repeat counts on the same segment disagree with each other, and is
     that disagreement a year effect or intrinsic replicate noise?
  3. what rho does the reference data achieve against ITSELF? Split each
     multi-count segment's counts into two random halves and correlate the
     half-means across segments; Spearman-Brown converts that half-vs-half value to
     the reliability of the full per-segment mean. No model can beat that ceiling
     by much, so the model's rho is best read as a share of it.

Ledger entries V5-V7 come from this script (baseline must reproduce V1 = 0.590).

Run:  python src/count_noise_analysis.py [run_name]     (default powell_through)
First run `python src/traffic_counts.py` to pull the counts.
"""
import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from validate_traffic import SNAP_MAX_M, _spearman

SEED = 42


def snap_all(run_name):
    """Snap every count once; year filters are applied to the result afterwards."""
    counts = pd.read_parquet(
        os.path.join(config.PROCESSED_DIR, "pbot_traffic_counts.parquet")
    ).dropna(subset=["adt"])
    abm = pd.read_parquet(
        os.path.join(config.PROCESSED_DIR, f"{run_name}_segments.parquet"))
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))

    Gp = ox.project_graph(G)
    pts = gpd.GeoSeries(gpd.points_from_xy(counts["lon"], counts["lat"]),
                        crs="EPSG:4326").to_crs(Gp.graph["crs"])
    ne, nd = ox.distance.nearest_edges(Gp, pts.x.to_numpy(), pts.y.to_numpy(),
                                       return_dist=True)
    key_to_row = {(r.u, r.v, r.key): i for i, r in enumerate(abm.itertuples())}
    seg = np.array([key_to_row.get(tuple(uvk), -1) for uvk in ne])

    matched = counts.assign(seg=seg, snap_m=np.asarray(nd, dtype=float))
    matched = matched[(matched["snap_m"] <= SNAP_MAX_M) & (matched["seg"] >= 0)]
    return matched, abm


def rho_for(matched, abm, model_col="throughput"):
    """Collapse to one row per segment (mean ADT, as validate_traffic.py does)
    and return the Spearman vs the model column."""
    per_seg = (matched.groupby("seg")
               .agg(adt=("adt", "mean"), n=("adt", "size")).reset_index())
    if len(per_seg) < 3:
        return float("nan"), len(per_seg), len(matched)
    model = abm[model_col].to_numpy()[per_seg["seg"].to_numpy()]
    return _spearman(per_seg["adt"], model), len(per_seg), len(matched)


def main(run_name):
    matched, abm = snap_all(run_name)
    col = "throughput" if "throughput" in abm.columns else "value"

    # ---- 1. baseline -----------------------------------------------------
    base_rho, base_segs, base_n = rho_for(matched, abm, col)
    print(f"run={run_name}   model column={col}")
    print(f"BASELINE (all years): rho={base_rho:+.3f}  "
          f"segments={base_segs}  counts={base_n}")
    if abs(base_rho - 0.59) > 0.02:
        print("!! Baseline does not reproduce the headline 0.59. STOPPING.")
        return

    # ---- 2. year windows -------------------------------------------------
    print("\nYEAR-WINDOW RESTRICTIONS")
    print(f"{'filter':<22}{'rho':>8}{'d_rho':>9}{'segments':>10}{'counts':>9}")
    print(f"{'all years (2010-2026)':<22}{base_rho:>+8.3f}{0.0:>9.3f}"
          f"{base_segs:>10}{base_n:>9}")
    filters = [(f"year >= {y}", matched["year"] >= y)
               for y in (2015, 2018, 2020, 2022)]
    filters.append(("drop 2020 (COVID)", matched["year"] != 2020))
    filters.append(("drop 2020-2021", ~matched["year"].isin([2020, 2021])))
    for label, mask in filters:
        r, s, n = rho_for(matched[mask], abm, col)
        print(f"{label:<22}{r:>+8.3f}{r - base_rho:>+9.3f}{s:>10}{n:>9}")

    # Sample-size control: narrowing the years also shrinks the sample, and a
    # smaller sample alone moves rho. So draw random subsets of the SAME size as
    # each year window, from all years, and report the spread of rho that size
    # produces by itself.
    print("\nSAMPLE-SIZE CONTROL (random subsets of all-year counts, 200 draws)")
    print(f"{'n counts':>9}{'rho mean':>10}{'rho p5':>9}{'rho p95':>9}")
    rng = np.random.default_rng(SEED)
    for n_target in sorted({int((matched["year"] >= y).sum())
                            for y in (2015, 2018, 2020, 2022)}):
        rs = []
        for _ in range(200):
            sub = matched.iloc[rng.choice(len(matched), n_target, replace=False)]
            r, _, _ = rho_for(sub, abm, col)
            rs.append(r)
        rs = np.array(rs)
        print(f"{n_target:>9}{rs.mean():>+10.3f}{np.percentile(rs, 5):>+9.3f}"
              f"{np.percentile(rs, 95):>+9.3f}")

    # ---- 3. within-segment disagreement ----------------------------------
    print("\nWITHIN-SEGMENT DISAGREEMENT (segments with >= 3 counts)")
    g = matched.groupby("seg")["adt"]
    stats = pd.DataFrame({"n": g.size(), "mean": g.mean(), "std": g.std(),
                          "mn": g.min(), "mx": g.max()})
    yr = matched.groupby("seg")["year"]
    stats["yr_span"] = yr.max() - yr.min()
    multi = stats[stats["n"] >= 3].copy()
    multi["cv"] = multi["std"] / multi["mean"]
    multi["ratio"] = multi["mx"] / multi["mn"].replace(0, np.nan)
    print(f"  {len(multi)} of {len(stats)} matched segments have >= 3 counts "
          f"({int(multi['n'].sum())} counts); median year span "
          f"{multi['yr_span'].median():.0f} yr")
    for name, s in (("CV (std/mean)", multi["cv"]), ("max/min ratio", multi["ratio"])):
        q = s.quantile([0.25, 0.5, 0.75, 0.9]).to_numpy()
        print(f"  {name:<15} median={q[1]:.2f}  IQR {q[0]:.2f}-{q[2]:.2f}  "
              f"p90={q[3]:.2f}")
    print(f"  segments where the max count is >2x the min: "
          f"{(multi['ratio'] > 2).mean() * 100:.0f}%")

    # ---- 3b. is that spread a YEAR effect, or replicate noise? ------------
    # Split the disagreement two ways: repeat counts within a single year on one
    # segment, vs the drift between per-year means on the same segment. If the
    # within-year spread dominates, year mixing is not the problem.
    sub = matched[matched["seg"].isin(multi.index)]
    wy = sub.groupby(["seg", "year"])["adt"].agg(["size", "mean", "std", "min", "max"])
    wy = wy[wy["size"] >= 3]
    print(f"  within ONE year, same segment ({len(wy)} seg-year cells, >=3 counts):"
          f"  CV median {(wy['std'] / wy['mean']).median():.2f}, "
          f"max/min median {(wy['max'] / wy['min'].replace(0, np.nan)).median():.2f}")
    ym = sub.groupby(["seg", "year"])["adt"].mean().reset_index()
    nyr = ym.groupby("seg").size()
    ms = ym[ym["seg"].isin(nyr.index[nyr >= 2])]
    gy = ms.groupby("seg")["adt"]
    print(f"  across YEARS, per-year means ({ms['seg'].nunique()} segments, "
          f">=2 distinct years):  CV median {(gy.std() / gy.mean()).median():.2f}, "
          f"max/min median {(gy.max() / gy.min().replace(0, np.nan)).median():.2f}")

    # ---- 4. self-consistency ceiling -------------------------------------
    # Split each multi-count segment's counts into two random halves and
    # correlate half-A's mean ADT against half-B's across segments. This is the
    # reference data measured against itself: no model can beat it by much.
    print("\nSELF-CONSISTENCY CEILING (split-half, >= 2 counts per segment)")
    eligible = matched[matched["seg"].isin(stats.index[stats["n"] >= 2])]
    rhos, rhos3 = [], []
    for trial in range(200):
        shuf = eligible.sample(frac=1.0, random_state=SEED + trial)
        half = shuf.groupby("seg").cumcount() % 2      # alternate after shuffling
        a = shuf[half == 0].groupby("seg")["adt"].mean()
        b = shuf[half == 1].groupby("seg")["adt"].mean()
        both = pd.concat([a, b], axis=1, join="inner").dropna()
        both.columns = ["a", "b"]
        rhos.append(_spearman(both["a"], both["b"]))
        keep = both.index.intersection(stats.index[stats["n"] >= 3])
        rhos3.append(_spearman(both.loc[keep, "a"], both.loc[keep, "b"]))
        if trial == 0:
            n_pairs, n_pairs3 = len(both), len(keep)
    rhos, rhos3 = np.array(rhos), np.array(rhos3)
    print(f"  >=2 counts: rho_split-half = {rhos.mean():+.3f} "
          f"(p5 {np.percentile(rhos, 5):+.3f}, p95 {np.percentile(rhos, 95):+.3f}) "
          f"on {n_pairs} segments")
    print(f"  >=3 counts: rho_split-half = {rhos3.mean():+.3f} "
          f"(p5 {np.percentile(rhos3, 5):+.3f}, p95 {np.percentile(rhos3, 95):+.3f}) "
          f"on {n_pairs3} segments")
    # Spearman-Brown: a half is half the data, so the FULL reference's
    # reliability is higher than the half-vs-half number.
    sb = 2 * rhos.mean() / (1 + rhos.mean())
    print(f"  Spearman-Brown corrected (reliability of the full per-segment mean): "
          f"{sb:+.3f}")
    print(f"\n  model rho {base_rho:+.3f} vs ceiling {sb:+.3f} -> the model reaches "
          f"{100 * base_rho / sb:.0f}% of what the reference data can support")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "powell_through")
