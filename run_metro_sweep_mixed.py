"""Metro closure robustness sweep under the MIXED fleet: Powell, 12 seeds.

The mixed-fleet twin of run_metro_sweep.py (gate G2 set Jul 20: the mixed fleet
is the live setting, so the metro closure robustness result M20.15 needs a
mixed-fleet counterpart before mixed absolute numbers are cited for the metro
closure). Same fixed 12-seed list, same config, same graph; only the fleet flag
and the file names differ (sweepmix_powell_<seed>_{open,closed}).

Design, matching the all-diesel sweep's hard-won conventions:
  - data dirs point at the metro5k-scaleup worktree (the 20 km caches and every
    metro result live there), via mixed_rerun.apply_metro_dirs.
  - skip-existing resume at the HALF level: a half whose parquet exists is
    skipped, so a killed sweep relaunches and loses at most the half in flight.
    Each half is an independent run_simulation call with its own per-call
    seeding (exactly what run_closure_experiment does internally), so running
    halves separately is equivalent to running the pair in one call.
  - seed 42's open half is not recomputed: metro20k_mixed (Jul 21) came from
    the same graph, config, seed, and fleet, and the sim is deterministic per
    call (verified: the all-diesel open half is bit-identical to its base run),
    so the driver copies that file to the sweep name.
  - all runs serial in this one process (one simulation at a time).
  - a failed half is logged to sweepmix_errors.log and the sweep moves on.

Run from the repo root (detached, ~12 hours):
    python -u run_metro_sweep_mixed.py
Analyze afterward (read-only):
    python src/mixed_rerun.py metro-closure-report          # seed-42 pair
    python src/metro_sweep_robustness.py sweepmix_powell    # all seeds
"""
import os
import shutil
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import config
from mixed_rerun import apply_metro_dirs

SEEDS = [42, 7, 13, 21, 99, 2024, 1, 5, 8, 100, 314, 777]  # closure_sweep.py's fixed list
PREFIX = "sweepmix_powell"


def half_path(base, half):
    return os.path.join(config.PROCESSED_DIR, f"{base}_{half}_segments.parquet")


def main():
    apply_metro_dirs()
    config.FLEET_MIXED = True
    assert config.N_VEHICLES == 16500, "expected the committed metro20k configuration"

    import generate  # after dirs are set, so get_network() loads the 20 km cache

    # seed 42 open half: reuse the verified metro20k_mixed base run
    src42 = os.path.join(config.PROCESSED_DIR, "metro20k_mixed_segments.parquet")
    dst42 = half_path(f"{PREFIX}_42", "open")
    if os.path.exists(src42) and not os.path.exists(dst42):
        shutil.copyfile(src42, dst42)
        print("[reuse] seed 42 open half copied from metro20k_mixed", flush=True)

    generate.set_seeds(config.RANDOM_SEED)
    G = generate.get_network()
    Gc = G.copy()
    removed = generate.apply_closure(Gc)
    print(f"closure zone: {len(removed)} segments removed", flush=True)

    errlog = os.path.join(config.PROCESSED_DIR, "sweepmix_errors.log")
    saved = (config.RANDOM_SEED, config.RUN_NAME)
    try:
        for i, seed in enumerate(SEEDS, 1):
            base = f"{PREFIX}_{seed}"
            for half, graph in (("open", G), ("closed", Gc)):
                if os.path.exists(half_path(base, half)):
                    print(f"=== ({i}/{len(SEEDS)}) seed {seed} {half}: exists, skipping ===",
                          flush=True)
                    continue
                config.RANDOM_SEED = seed
                config.RUN_NAME = f"{base}_{half}"
                print(f"=== ({i}/{len(SEEDS)}) seed {seed} {half} ===", flush=True)
                try:
                    totals, nox, thru = generate.run_simulation(
                        graph, use_checkpoint=False, verbose=False)
                    generate.save_results(totals, nox, thru)
                except Exception:
                    with open(errlog, "a") as f:
                        f.write(f"seed {seed} {half}:\n{traceback.format_exc()}\n")
                    print(f"[error] seed {seed} {half} failed; logged and continuing",
                          flush=True)
    finally:
        config.RANDOM_SEED, config.RUN_NAME = saved

    done = sum(os.path.exists(half_path(f"{PREFIX}_{s}", h))
               for s in SEEDS for h in ("open", "closed"))
    print(f"\nMixed metro sweep: {done}/{2 * len(SEEDS)} halves on disk.", flush=True)


if __name__ == "__main__":
    main()
