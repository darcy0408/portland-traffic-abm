"""The week-6 model-to-model comparison: same algorithm, same target, same points,
different predictor SOURCE.

We fit a random forest to predict measured NO2 at Rao's passive-sampler sites from
two predictor sets and compare their out-of-sample skill:
  - LAND-USE  : Rao-style fixed built-environment features (landuse_model)
  - ABM       : traffic features the agent simulation produces (predictors)
and, as an extra, BOTH together (does interaction-modeled traffic ADD skill over
land use alone?).

The forests use identical settings, so any difference in skill comes from the
predictors, which is the project's whole thesis: does source-based interaction
modeling describe NO2 as well as, or better than, static land use?

EVALUATION: spatial block cross-validation (Roberts et al. 2017). Air-pollution
sites near each other are not independent: a random train/test split lets a test
site lean on a training neighbor a few hundred meters away and inflates the score.
We instead bin sites into a spatial grid and hold out WHOLE blocks at a time, so
a test site never leans on a training neighbor inside its own block. Sites near a
block BOUNDARY can still have a training neighbor in the adjacent block; that is
inherent to grid-block CV, and the control is choosing block_m at least as large
as the NO2 spatial-autocorrelation range (why block_m is a knob to set with
the mentor). The same discipline applies identically to both forests, so the
comparison stays fair either way.

This module runs NO simulation. It READS an ABM run's saved per-segment surface,
the cached graph, the land-use block-group parquet, and the (gitignored) Rao data.

Honest scope note: the comparison is only meaningful with enough sites. On the
1.5 km Powell network only ~15 sampler sites fall in range, too few to cross-
validate; this is the data-side reason the network must grow (a 5 km network holds
~68 sites). Until then __main__ runs as a PLUMBING check and says so.
"""
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GroupKFold, cross_val_predict
from sklearn.metrics import r2_score, mean_squared_error
from scipy.stats import spearmanr

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import rao_data
import predictors
import landuse_model


def _forest():
    """The shared random forest. Identical for every predictor set so only the
    features differ (same n_estimators, seed, and parallelism as landuse_model)."""
    return RandomForestRegressor(
        n_estimators=400, random_state=config.RANDOM_SEED, n_jobs=-1,
    )


def spatial_blocks(lat, lon, block_m):
    """Assign each site to a square spatial block of side `block_m` meters. Sites in
    the same block share a group id and are never split across a train/test fold.
    Returns an integer group id per site."""
    x, y = predictors._local_xy(np.asarray(lat, float), np.asarray(lon, float))
    bx = np.floor(x / block_m).astype(np.int64)
    by = np.floor(y / block_m).astype(np.int64)
    key = bx * 1_000_000 + by
    _, ids = np.unique(key, return_inverse=True)
    return ids


def assemble(run_name=None, season="summer", year=None, average_rounds=True,
             demog="centroid"):
    """Build the aligned comparison table for one ABM run.

    Returns a dict with: site_ids, y (NO2 ppb), X_abm, X_lu (DataFrames), lat, lon,
    and the names of each feature block. Sites with no simulated network within the
    largest buffer are dropped (a site outside the network gets all-zero ABM
    features and cannot be described by the ABM, so it is not a fair test point).

    demog: 'centroid' (original point-mass pop/jobs) or 'areal' (polygon overlap,
    OR+WA); see landuse_model.build_site_features. Only the land-use features
    change; the ABM features and site set are identical either way."""
    run_name = config.RUN_NAME if run_name is None else run_name
    tgt = rao_data.rao_targets(season=season, year=year, average_rounds=average_rounds)

    abm = predictors.build_site_predictors(tgt, run_name=run_name)
    G = predictors.load_network()
    lu = landuse_model.build_site_features(G, tgt, demog=demog)

    on_net = abm[f"n_seg_buf{max(config.BUFFER_RADII_M)}"].to_numpy() > 0
    # Explicit allowlist, not a substring test: only these traffic-descriptor
    # families may enter the ABM feature set. If a future buffered column is
    # emissions-derived (e.g. nox_buf*) it is excluded by default, so the
    # no-target-leakage rule is enforced here, not just by convention upstream.
    _abm_ok = ("activity_buf", "throughput_buf", "meanspeed_buf")
    abm_cols = [c for c in abm.columns if c.startswith(_abm_ok)]

    keep = on_net
    return {
        "site_ids": tgt["site_id"].to_numpy()[keep],
        "y": tgt["no2"].to_numpy(float)[keep],
        "lat": tgt["lat"].to_numpy(float)[keep],
        "lon": tgt["lon"].to_numpy(float)[keep],
        "X_abm": abm.loc[keep, abm_cols].reset_index(drop=True),
        "X_lu": lu.loc[keep].reset_index(drop=True),
        "abm_cols": abm_cols,
        "lu_cols": list(lu.columns),
    }


def block_cv_predict(X, y, groups, n_splits=5):
    """Out-of-fold predictions under spatial block CV. Folds are formed over whole
    blocks (GroupKFold), capped at the number of distinct blocks. Returns the pooled
    out-of-fold prediction vector aligned to y."""
    n_blocks = len(np.unique(groups))
    if n_blocks < 2:
        raise ValueError(f"need >=2 spatial blocks to cross-validate, got {n_blocks}")
    k = min(n_splits, n_blocks)
    cv = GroupKFold(n_splits=k)
    return cross_val_predict(_forest(), X, y, groups=groups, cv=cv)


def _score(y, yhat):
    """Spatially-honest skill metrics on out-of-fold predictions."""
    return {
        "r2": float(r2_score(y, yhat)),
        "rmse": float(np.sqrt(mean_squared_error(y, yhat))),
        "spearman": float(spearmanr(y, yhat).statistic),
    }


def compare(run_name=None, block_m=2000, n_splits=5, season="summer", year=None,
            data=None):
    """Run the full comparison for one ABM run and return a results dict.

    block_m: spatial-block side in meters (Roberts CV). Should reflect the range of
        spatial autocorrelation in NO2; 2 km is a sensible default for an urban LUR
        and a knob to set with the mentor, not tuned to win.
    data: a dict from assemble(), to reuse across block sizes without rebuilding
        the buffer features (they are the slow part and do not depend on block_m).
    """
    if data is None:
        data = assemble(run_name=run_name, season=season, year=year)
    y, lat, lon = data["y"], data["lat"], data["lon"]
    groups = spatial_blocks(lat, lon, block_m)
    n_blocks = len(np.unique(groups))

    feature_sets = {
        "land-use": data["X_lu"],
        "abm": data["X_abm"],
        "combined": pd.concat([data["X_lu"], data["X_abm"]], axis=1),
    }
    # The fold count is capped at the number of occupied blocks, so record the k
    # actually used; citing "5-fold" when only 4 blocks exist would be wrong.
    k_effective = min(n_splits, n_blocks)

    results = {}
    for name, X in feature_sets.items():
        yhat = block_cv_predict(X.to_numpy(), y, groups, n_splits=n_splits)
        results[name] = _score(y, yhat)

    return {
        "run_name": run_name or config.RUN_NAME,
        "n_sites": len(y), "n_blocks": int(n_blocks), "block_m": block_m,
        "n_folds": int(k_effective),
        "season": season, "year": year, "scores": results,
    }


def shuffle_control(data, block_m=2000, n_splits=5, n_shuffles=10):
    """Adversarial control for the combined forest's lift over land use alone.

    Permute the ABM feature ROWS across sites (breaking the site alignment while
    keeping every marginal distribution and the feature count identical), refit
    the combined forest, and score it the same way. If the true combined score
    beats land-use alone only because extra columns help a forest overfit, the
    shuffled runs will show the same lift; if the lift needs the ABM values to be
    attached to the RIGHT sites, shuffling collapses it back to land-use alone.

    First run Jul 6 was ad hoc; this committed version makes it reproducible.
    Seeded from config.RANDOM_SEED. Returns the shuffled-combined R^2 list.
    """
    y, lat, lon = data["y"], data["lat"], data["lon"]
    groups = spatial_blocks(lat, lon, block_m)
    rng = np.random.default_rng(config.RANDOM_SEED)

    r2s = []
    for _ in range(n_shuffles):
        perm = rng.permutation(len(y))
        X_shuf = pd.concat(
            [data["X_lu"].reset_index(drop=True),
             data["X_abm"].iloc[perm].reset_index(drop=True)], axis=1)
        yhat = block_cv_predict(X_shuf.to_numpy(), y, groups, n_splits=n_splits)
        r2s.append(float(r2_score(y, yhat)))
    return r2s


def _print_report(res):
    print(f"\nModel-to-model NO2 comparison on '{res['run_name']}' "
          f"({res['season']}{'/'+str(res['year']) if res['year'] else ''})")
    print(f"  {res['n_sites']} sites in {res['n_blocks']} spatial blocks "
          f"of {res['block_m']} m; {res['n_folds']}-fold spatial block cross-validation")
    print(f"  {'predictor set':<12} {'R^2':>7} {'RMSE(ppb)':>11} {'Spearman':>9}")
    for name, s in res["scores"].items():
        print(f"  {name:<12} {s['r2']:>7.3f} {s['rmse']:>11.2f} {s['spearman']:>9.3f}")


if __name__ == "__main__":
    run = sys.argv[1] if len(sys.argv) > 1 else config.RUN_NAME
    # Real configuration: 2 km blocks (Roberts CV; block_m is a knob to set with
    # the mentor, not tuned to win). On a network too small to hold enough sampler
    # sites this degrades to a plumbing check at a smaller block size, clearly
    # labeled as uninterpretable.
    try:
        res = compare(run_name=run)
        _print_report(res)
    except ValueError as e:
        print(f"Cannot cross-validate at 2 km blocks: {e}")
        print("Falling back to a small-block PLUMBING CHECK; numbers not meaningful.")
        res = compare(run_name=run, block_m=500, n_splits=4)
        _print_report(res)
        print("\n[plumbing check only: site/block count is too small to interpret]")
