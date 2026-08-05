"""Review item 3: how much of the forest comparison is luck of the draw?

The committed comparison (forest_compare.py, M20.10) reports ONE number per
predictor set: a single spatial-block fold assignment (deterministic GroupKFold)
and a single forest seed. Christof's review asks for the variance behind that
number. This script repeats the whole cross-validation many times, varying the
two arbitrary choices a forest comparison hides:

  - the FOLD ASSIGNMENT: which spatial blocks land in which fold. Blocks are
    randomly partitioned into k folds with a seeded RNG each repetition,
    replacing GroupKFold's deterministic assignment. Whole blocks still move
    together, so the Roberts spatial discipline is never weakened.
  - the FOREST SEED: the RandomForestRegressor's random_state.

Each repetition scores all three predictor sets (land-use, ABM, combined) on
the SAME folds, so the combined-minus-land-use lift is a paired difference and
its distribution answers "does the +0.06 lift survive the draw?".

It also fits the combined forest on all sites to report variable importance,
averaged over the repetition seeds, to interpret WHY ABM-alone trails while
combined wins (which features the combined forest actually leans on).

Read-only: reads the saved metro20k surface, the 20 km graph cache, and the Rao
sites via forest_compare.assemble; runs NO simulation. Uses the fair (areal,
OR+WA) land-use baseline, the same configuration as the cited M20.10 numbers.
Results land in <processed>/cvvar_<run>_<season>.json for the chapter table.

Run: python src/forest_cv_variance.py            (metro20k summer, 2 and 3 km)
     python src/forest_cv_variance.py --reps 50  (more repetitions)
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import r2_score, mean_squared_error
from scipy.stats import spearmanr

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import forest_compare
from mixed_rerun import apply_metro_dirs

RUN_NAME = "metro20k"
SEASON = "summer"
BLOCK_SIZES_M = (2000, 3000)
N_SPLITS = 5
# Seed offsets keep every repetition reproducible from config.RANDOM_SEED while
# never reusing the committed run's exact seed for a "new" draw.
FOLD_SEED_BASE = config.RANDOM_SEED + 1000
FOREST_SEED_BASE = config.RANDOM_SEED + 2000


def random_fold_assignment(groups, k, rng):
    """Randomly partition spatial blocks into k folds. Returns a per-site fold
    id. Blocks stay intact (every site in a block shares a fold), only WHICH
    fold a block lands in is random. Block counts per fold differ by at most
    one; site counts per fold vary freely, which is part of the variance being
    measured."""
    block_ids = np.unique(groups)
    fold_of_block = rng.permutation(len(block_ids)) % k
    lookup = dict(zip(block_ids, fold_of_block))
    return np.array([lookup[g] for g in groups])


def oof_predict(X, y, fold_ids, k, forest_seed):
    """Pooled out-of-fold predictions over a predefined fold assignment, with
    the forest seeded per repetition (forest_compare._forest pins the seed to
    config.RANDOM_SEED, so the seed is a parameter here instead)."""
    yhat = np.empty_like(y, dtype=float)
    for f in range(k):
        test = fold_ids == f
        model = RandomForestRegressor(
            n_estimators=400, random_state=forest_seed, n_jobs=-1)
        model.fit(X[~test], y[~test])
        yhat[test] = model.predict(X[test])
    return yhat


def _score(y, yhat):
    return {
        "r2": float(r2_score(y, yhat)),
        "rmse": float(np.sqrt(mean_squared_error(y, yhat))),
        "spearman": float(spearmanr(y, yhat).statistic),
    }


def run_variance(data, block_m, n_reps):
    """One block size: n_reps repetitions, each scoring the three predictor
    sets on a shared random fold assignment with a fresh forest seed."""
    y, lat, lon = data["y"], data["lat"], data["lon"]
    groups = forest_compare.spatial_blocks(lat, lon, block_m)
    k = min(N_SPLITS, len(np.unique(groups)))

    feature_sets = {
        "land-use": data["X_lu"].to_numpy(),
        "abm": data["X_abm"].to_numpy(),
        "combined": pd.concat([data["X_lu"], data["X_abm"]], axis=1).to_numpy(),
    }

    reps = []
    for i in range(n_reps):
        rng = np.random.default_rng(FOLD_SEED_BASE + i)
        fold_ids = random_fold_assignment(groups, k, rng)
        rep = {"fold_seed": FOLD_SEED_BASE + i, "forest_seed": FOREST_SEED_BASE + i}
        for name, X in feature_sets.items():
            rep[name] = _score(y, oof_predict(X, y, fold_ids, k, rep["forest_seed"]))
        rep["lift"] = rep["combined"]["r2"] - rep["land-use"]["r2"]
        reps.append(rep)
        print(f"  block {block_m} m rep {i + 1:>3}/{n_reps}: "
              f"LU {rep['land-use']['r2']:.3f}  ABM {rep['abm']['r2']:.3f}  "
              f"combined {rep['combined']['r2']:.3f}  lift {rep['lift']:+.3f}",
              flush=True)

    # The committed single-number configuration, for anchoring the distribution
    # (GroupKFold assignment, forest seed = config.RANDOM_SEED).
    committed = {}
    for name, X in feature_sets.items():
        yhat = forest_compare.block_cv_predict(X, y, groups, n_splits=N_SPLITS)
        committed[name] = _score(y, yhat)
    committed["lift"] = committed["combined"]["r2"] - committed["land-use"]["r2"]

    return {"block_m": block_m, "n_folds": int(k),
            "n_blocks": int(len(np.unique(groups))),
            "reps": reps, "committed": committed}


def variable_importance(data, n_reps):
    """Impurity importance of the combined forest fit on ALL sites, averaged
    over the repetition forest seeds so no single seed's tree draw decides the
    ranking. Grouped shares answer the interpretation question directly: how
    much of the combined forest's splitting goes to ABM traffic features vs
    land-use features."""
    X = pd.concat([data["X_lu"], data["X_abm"]], axis=1)
    cols = list(X.columns)
    lu_cols = set(data["lu_cols"])
    imps = np.zeros(len(cols))
    for i in range(n_reps):
        model = RandomForestRegressor(
            n_estimators=400, random_state=FOREST_SEED_BASE + i, n_jobs=-1)
        model.fit(X.to_numpy(), data["y"])
        imps += model.feature_importances_
    imps /= n_reps

    per_feature = sorted(zip(cols, imps), key=lambda t: -t[1])
    lu_share = float(sum(v for c, v in zip(cols, imps) if c in lu_cols))
    return {
        "lu_share": lu_share,
        "abm_share": float(1.0 - lu_share),
        "top15": [{"feature": c, "importance": float(v)}
                  for c, v in per_feature[:15]],
        "n_seeds_averaged": n_reps,
    }


def _summ(vals):
    v = np.asarray(vals, float)
    return f"{v.mean():.3f} +/- {v.std(ddof=1):.3f}  [{v.min():.3f}, {v.max():.3f}]"


def _print_report(out):
    print(f"\nCV-variance report: '{out['run_name']}' {out['season']}, "
          f"{out['n_sites']} sites, {out['n_reps']} repetitions "
          f"(random block-to-fold assignment x fresh forest seed)")
    for blk in out["blocks"]:
        print(f"\n  {blk['block_m']} m blocks ({blk['n_blocks']} blocks, "
              f"{blk['n_folds']} folds); mean +/- SD [min, max] of R^2:")
        for name in ("land-use", "abm", "combined"):
            vals = [r[name]["r2"] for r in blk["reps"]]
            print(f"    {name:<9} {_summ(vals)}   (committed: "
                  f"{blk['committed'][name]['r2']:.3f})")
        lifts = [r["lift"] for r in blk["reps"]]
        frac = np.mean(np.asarray(lifts) > 0)
        print(f"    lift      {_summ(lifts)}   (committed: "
              f"{blk['committed']['lift']:+.3f}); positive in "
              f"{frac:.0%} of repetitions")
    vi = out["importance"]
    print(f"\n  Combined-forest variable importance (all sites, averaged over "
          f"{vi['n_seeds_averaged']} seeds):")
    print(f"    land-use share {vi['lu_share']:.1%}, ABM share {vi['abm_share']:.1%}")
    for t in vi["top15"]:
        print(f"    {t['feature']:<28} {t['importance']:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=30)
    args = ap.parse_args()

    apply_metro_dirs()
    print(f"assembling site table for '{RUN_NAME}' ({SEASON}, areal land use)...",
          flush=True)
    data = forest_compare.assemble(run_name=RUN_NAME, season=SEASON, demog="areal")
    print(f"  {len(data['y'])} on-net sites, {len(data['lu_cols'])} land-use + "
          f"{len(data['abm_cols'])} ABM features", flush=True)

    out = {
        "run_name": RUN_NAME, "season": SEASON, "demog": "areal",
        "n_sites": int(len(data["y"])), "n_reps": args.reps,
        "fold_seed_base": FOLD_SEED_BASE, "forest_seed_base": FOREST_SEED_BASE,
        "blocks": [run_variance(data, b, args.reps) for b in BLOCK_SIZES_M],
        "importance": variable_importance(data, args.reps),
    }

    path = os.path.join(config.PROCESSED_DIR, f"cvvar_{RUN_NAME}_{SEASON}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"\nsaved -> {path}")
    _print_report(out)


if __name__ == "__main__":
    main()
