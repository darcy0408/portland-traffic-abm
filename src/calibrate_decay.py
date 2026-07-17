"""EXPLORATORY (branch experiment/decay): fit the gravity decay scale from LODES.

The gravity demand model draws a trip's destination with weight
jobs_j * exp(-distance / config.GRAVITY_DECAY_SCALE_M). The 1500 m scale was set
a priori and deliberately never calibrated, because the only local traffic data
(the PBOT counts) is the held-out validation set and must never be used for tuning.

This script calibrates the scale the honest way: from the LODES8 origin-destination
commute flows (src/lodes_od.py), which are measured Census data and completely
independent of the PBOT counts. LODES tells us how far people who live near Powell
actually commute, so the decay scale can be DERIVED from data instead of guessed.

Estimator choice, explained:

  1) The naive estimator: flow-weighted mean trip distance. If trip distances were
     drawn straight from an exponential distribution, the maximum-likelihood scale
     is just the mean distance. Reported because it is transparent, but it is
     BIASED here, because trips are not free to land anywhere: they can only go
     where jobs exist. If most jobs sit 1 km away, trips average 1 km regardless
     of how strong the distance preference is. The naive mean confuses the job
     GEOGRAPHY with the distance PREFERENCE.

  2) The estimator used for the headline fit: conditional-logit maximum likelihood
     that matches the simulation's own generative form. The sim draws destination
     j for a trip from origin i with probability
         P(j | i, lambda) = jobs_j * exp(-d_ij/lambda) / sum_k jobs_k * exp(-d_ik/lambda)
     so the likelihood of the observed LODES flows T_ij under scale lambda is
     prod_ij P(j|i,lambda)^T_ij. This controls for the jobs geography exactly the
     way the sim experiences it: the denominator says what was AVAILABLE at each
     distance, so lambda captures only the residual distance preference. The MLE
     solves the score equation
         observed flow-weighted mean distance == model-expected mean distance,
     and the expected mean is monotone increasing in lambda, so bisection finds it.

Truncation caveat, quantified not hidden: the study window keeps only OD pairs with
BOTH ends inside 1.5 km, which throws away every longer commute and biases the
within-window distances short. The raw LODES file is statewide, so we also fit on
wider pulls (both ends within 10 km, and homes in the window with workplaces
anywhere within 30 km, i.e. corridor residents' real commutes untruncated) to show
how much the window compresses the fitted scale.

Reads the cached statewide OD file (data/raw/or_od_main_<year>.csv.gz); pulls it via
lodes_od/landuse_data machinery if absent. Runs no simulation.

Run it with:  python src/calibrate_decay.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import landuse_data

# wider pulls used to quantify the window-truncation bias (meters from study center)
MID_RADIUS_M = 10_000     # "both ends within 10 km": a mid-size window
WIDE_RADIUS_M = 30_000    # workplace choice set for the untruncated fit (covers the
                          # Oregon side of the metro; commutes past 30 km are rare
                          # enough not to move a ~2-6 km scale)

_CHUNK = 500_000          # same chunked read as lodes_od.py: statewide file stays small in memory


def _od_pairs(home_set, work_set, year=None):
    """Aggregate the statewide LODES OD file to block-group pairs with the home end
    in home_set and the work end in work_set. Same source and aggregation as
    lodes_od.od_table, but with independent home/work filters so we can lift the
    both-ends-in-window truncation."""
    year = config.LODES_YEAR if year is None else year
    path = landuse_data._download(
        lodes_od_url(year), os.path.join(config.RAW_DIR, f"or_od_main_{year}.csv.gz"),
        force=False)
    kept = []
    for chunk in pd.read_csv(path, usecols=["h_geocode", "w_geocode", "S000"],
                             dtype={"h_geocode": str, "w_geocode": str},
                             chunksize=_CHUNK):
        chunk["h_bg"] = chunk["h_geocode"].str[:12]
        chunk["w_bg"] = chunk["w_geocode"].str[:12]
        m = chunk["h_bg"].isin(home_set) & chunk["w_bg"].isin(work_set)
        if m.any():
            kept.append(chunk.loc[m, ["h_bg", "w_bg", "S000"]])
    if not kept:
        return pd.DataFrame(columns=["h_bg", "w_bg", "flow"])
    od = pd.concat(kept, ignore_index=True)
    od = od.groupby(["h_bg", "w_bg"], as_index=False)["S000"].sum()
    return od.rename(columns={"S000": "flow"})


def lodes_od_url(year):
    import lodes_od
    return lodes_od.LODES_OD_URL.format(year=year)


def _dist_matrix_m(lat_a, lon_a, lat_b, lon_b):
    """Haversine distances (meters) between every centroid in A and every one in B."""
    out = np.empty((len(lat_a), len(lat_b)))
    for i in range(len(lat_a)):
        out[i, :] = landuse_data._haversine_m(lat_a[i], lon_a[i], lat_b, lon_b)
    return out


def _weighted_quantiles(d, w, qs=(0.25, 0.5, 0.75, 0.9)):
    """Flow-weighted quantiles of trip distance (each commuter counts once)."""
    order = np.argsort(d)
    d, w = d[order], w[order]
    cw = np.cumsum(w) / w.sum()
    return {q: float(d[np.searchsorted(cw, q)]) for q in qs}


def fit_conditional_logit(od, homes, choice, lo=10.0, hi=200_000.0, tol=1.0):
    """MLE of the decay scale under the sim's own destination-choice form.

    od:     DataFrame h_bg, w_bg, flow (the observed trips)
    homes:  DataFrame bg_geoid, lat, lon for the origin block groups
    choice: DataFrame bg_geoid, lat, lon, jobs for the FULL destination choice set
            (what was available, not just what was chosen)

    Solves: flow-weighted mean observed distance == expected mean distance under
    P(j|i,lambda) ~ jobs_j * exp(-d_ij/lambda), averaged over origins weighted by
    their outgoing flow. The right side is monotone increasing in lambda (larger
    scale = weaker deterrence = longer expected trips), so bisection converges.
    Returns (lambda_m, diagnostics dict).
    """
    choice = choice[choice["jobs"] > 0].reset_index(drop=True)
    ch_idx = {g: i for i, g in enumerate(choice["bg_geoid"])}
    h_idx = {g: i for i, g in enumerate(homes["bg_geoid"])}

    # observed pairs the model could generate (home known, work in the choice set
    # with jobs > 0); report anything dropped instead of silently eating it
    ok = od["h_bg"].isin(h_idx) & od["w_bg"].isin(ch_idx)
    dropped_flow = float(od.loc[~ok, "flow"].sum())
    od = od[ok]

    D = _dist_matrix_m(homes["lat"].to_numpy(), homes["lon"].to_numpy(),
                       choice["lat"].to_numpy(), choice["lon"].to_numpy())
    jobs = choice["jobs"].to_numpy(dtype=float)

    hi_ = od["h_bg"].map(h_idx).to_numpy()
    wi_ = od["w_bg"].map(ch_idx).to_numpy()
    flow = od["flow"].to_numpy(dtype=float)
    obs_mean = float((D[hi_, wi_] * flow).sum() / flow.sum())

    # per-origin outgoing flow (the weight each origin's expectation gets)
    out_flow = np.zeros(len(homes))
    np.add.at(out_flow, hi_, flow)
    active = out_flow > 0

    def expected_mean(lam):
        # E[d | i, lambda] for each active origin, then flow-weighted average.
        # exp is computed on (row - row_min) for numerical safety at tiny lambda.
        exps = np.exp(-(D[active] - D[active].min(axis=1, keepdims=True)) / lam)
        w = jobs[None, :] * exps
        e_i = (w * D[active]).sum(axis=1) / w.sum(axis=1)
        return float((e_i * out_flow[active]).sum() / out_flow[active].sum())

    # bisection on g(lam) = expected_mean(lam) - obs_mean (monotone increasing)
    g_lo, g_hi = expected_mean(lo) - obs_mean, expected_mean(hi) - obs_mean
    if g_lo > 0:    # even the strongest deterrence gives trips longer than observed
        lam = lo
    elif g_hi < 0:  # observed trips longer than a no-deterrence draw: no finite fit
        lam = float("inf")
    else:
        a, b = lo, hi
        while b - a > tol:
            mid = 0.5 * (a + b)
            if expected_mean(mid) - obs_mean < 0:
                a = mid
            else:
                b = mid
        lam = 0.5 * (a + b)

    d_obs = D[hi_, wi_]
    diag = {
        "n_pairs": int(len(od)),
        "flow": float(flow.sum()),
        "dropped_flow": dropped_flow,
        "obs_mean_m": obs_mean,
        "intrazonal_flow": float(flow[d_obs == 0].sum()),
        "quantiles_m": _weighted_quantiles(d_obs, flow),
        # naive exponential MLE on the same trips = flow-weighted mean distance
        # (transparent but biased by the jobs geography; see module docstring)
        "naive_scale_m": obs_mean,
        "naive_scale_excl_intrazonal_m":
            float((d_obs[d_obs > 0] * flow[d_obs > 0]).sum() / flow[d_obs > 0].sum())
            if (d_obs > 0).any() else float("nan"),
    }
    return lam, diag


def main():
    year = config.LODES_YEAR
    # block groups at three footprints, all from the same Census/LODES machinery the
    # sim's demand uses, so centroids and jobs line up exactly
    lu_win = landuse_data.landuse_table(radius_m=config.STUDY_RADIUS_M)
    lu_mid = landuse_data.landuse_table(radius_m=MID_RADIUS_M)
    lu_wide = landuse_data.landuse_table(radius_m=WIDE_RADIUS_M)
    win_set = set(lu_win["bg_geoid"])
    mid_set = set(lu_mid["bg_geoid"])
    wide_set = set(lu_wide["bg_geoid"])
    print(f"block groups: {len(lu_win)} in the 1.5 km window, {len(lu_mid)} within "
          f"{MID_RADIUS_M/1000:.0f} km, {len(lu_wide)} within {WIDE_RADIUS_M/1000:.0f} km")

    # one statewide pass with the widest filter, then subset in memory
    od_wide = _od_pairs(wide_set, wide_set, year)
    print(f"LODES {year}: {len(od_wide):,} BG pairs / {int(od_wide['flow'].sum()):,} "
          f"commuters with both ends within {WIDE_RADIUS_M/1000:.0f} km")

    fits = []

    # Fit A: the truncated within-window fit. This is the like-for-like calibration
    # for the sim's INTERNAL demand: both ends inside the window, choice set = the
    # window's own job geography (exactly what make_vehicle can draw).
    od_a = od_wide[od_wide["h_bg"].isin(win_set) & od_wide["w_bg"].isin(win_set)]
    lam_a, dg_a = fit_conditional_logit(od_a, lu_win, lu_win)
    fits.append(("A: window 1.5 km (truncated, like-for-like with the sim)", lam_a, dg_a))

    # Fit C: both ends within 10 km. Less truncated; shows the trend with window size.
    od_c = od_wide[od_wide["h_bg"].isin(mid_set) & od_wide["w_bg"].isin(mid_set)]
    lam_c, dg_c = fit_conditional_logit(od_c, lu_mid, lu_mid)
    fits.append((f"C: both ends within {MID_RADIUS_M/1000:.0f} km", lam_c, dg_c))

    # Fit B: the untruncated read. Homes in the window (the people the sim's internal
    # demand represents), workplaces anywhere within 30 km, choice set = the full
    # 30 km job geography. This is what corridor residents' commutes actually look
    # like when the window stops cutting them off.
    od_b = od_wide[od_wide["h_bg"].isin(win_set)]
    lam_b, dg_b = fit_conditional_logit(od_b, lu_win, lu_wide)
    fits.append((f"B: homes in window, work within {WIDE_RADIUS_M/1000:.0f} km "
                 "(untruncated commutes)", lam_b, dg_b))

    rows = []
    for name, lam, dg in fits:
        q = dg["quantiles_m"]
        print(f"\nFit {name}")
        print(f"  {dg['n_pairs']:,} OD pairs, {int(dg['flow']):,} commuters "
              f"({int(dg['dropped_flow'])} commuters dropped: work BG outside the "
              f"choice set or zero WAC jobs)")
        print(f"  trip distances (flow-weighted): mean {dg['obs_mean_m']:.0f} m, "
              f"median {q[0.5]:.0f} m, p25 {q[0.25]:.0f} m, p75 {q[0.75]:.0f} m, "
              f"p90 {q[0.9]:.0f} m; intrazonal flow {int(dg['intrazonal_flow'])}")
        print(f"  naive exponential MLE (mean distance): {dg['naive_scale_m']:.0f} m "
              f"({dg['naive_scale_excl_intrazonal_m']:.0f} m excluding intrazonal)")
        lam_s = f"{lam:.0f} m" if np.isfinite(lam) else "unbounded (no finite MLE)"
        print(f"  conditional-logit MLE decay scale: {lam_s}")
        rows.append({"fit": name, "lambda_m": lam, **{k: v for k, v in dg.items()
                                                      if k != "quantiles_m"},
                     **{f"q{int(100*k)}_m": v for k, v in dg["quantiles_m"].items()}})

    out = os.path.join(config.PROCESSED_DIR, "decay_fit_summary.parquet")
    pd.DataFrame(rows).to_parquet(out, index=False)
    print(f"\nA-priori scale in config: {config.GRAVITY_DECAY_SCALE_M:.0f} m")
    print(f"Saved fit summary to {out}")


if __name__ == "__main__":
    main()
