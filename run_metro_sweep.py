"""Metro-scale closure robustness sweep: Powell scenario, 12 seeds.

Why this exists: M20.14 (the metro closure replication) is a single seed.
Christof's own bar (Jul 2) is that six seeds is small to call something
robust, so this runs the corridor sweep's exact 12-seed list at metro scale.
Verification only: no parameter changes, seeds fixed Jul 2 before any metro
result existed, every seed reported. Powell scenario only (the headline);
the 3-arterial generality sweep is ~3x the compute and can come later.

Scaled-up twin of closure_sweep.py with two differences for 10-hour runs on
a machine that has killed long tasks before:
  - skip-existing resume: a (seed) pair whose two parquet files both exist
    is skipped, so a killed sweep relaunches and loses at most the half-run
    that was in flight (run_closure_experiment itself does not checkpoint).
  - seed 42 is not recomputed: metro20k_open/_closed (Jul 14) came from the
    same graph, config, and seed, and the sim is deterministic per seed, so
    the driver copies those files to the sweep names.

The iron rule holds: all runs are serial in this one process.

Run from the metro5k-scaleup worktree root (detached, ~10 hours):
    python -u run_metro_sweep.py
Analyze afterward (read-only) with a metro variant of closure_robustness.py.
"""
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import config
import generate

SEEDS = [42, 7, 13, 21, 99, 2024, 1, 5, 8, 100, 314, 777]  # closure_sweep.py's fixed list


def pair_files(base):
    return [os.path.join(config.PROCESSED_DIR, f"{base}_{half}_segments.parquet")
            for half in ("open", "closed")]


def pair_done(base):
    return all(os.path.exists(p) for p in pair_files(base))


def main():
    # seed 42 already exists as the metro20k pair (same graph/config/seed,
    # deterministic); copy rather than recompute.
    for half in ("open", "closed"):
        src = os.path.join(config.PROCESSED_DIR, f"metro20k_{half}_segments.parquet")
        dst = os.path.join(config.PROCESSED_DIR, f"sweep_powell_42_{half}_segments.parquet")
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copyfile(src, dst)
            print(f"[reuse] seed 42 {half} half copied from metro20k")

    generate.set_seeds(config.RANDOM_SEED)
    G = generate.get_network()

    saved = (config.RANDOM_SEED, config.RUN_NAME)
    try:
        for i, seed in enumerate(SEEDS, 1):
            base = f"sweep_powell_{seed}"
            if pair_done(base):
                print(f"=== ({i}/{len(SEEDS)}) seed {seed}: already complete, skipping ===",
                      flush=True)
                continue
            config.RANDOM_SEED = seed
            config.RUN_NAME = base
            print(f"=== ({i}/{len(SEEDS)}) seed {seed} ===", flush=True)
            generate.run_closure_experiment(G)
    finally:
        config.RANDOM_SEED, config.RUN_NAME = saved

    print("\nMetro sweep complete: "
          f"{sum(pair_done(f'sweep_powell_{s}') for s in SEEDS)}/{len(SEEDS)} seed pairs on disk.")


if __name__ == "__main__":
    main()
