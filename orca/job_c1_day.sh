#!/bin/bash
# C1 DAY jobs: the A2 profiled pair re-run with en-route rerouting on.
# Submit:
#   N=$(python src/metro_c1_experiment.py --count-day)
#   sbatch --array=0-$((N-1)) orca/job_c1_day.sh
# Needs data/portal_powell_sample.csv on this machine (data/ is gitignored) or
# the profiled arms silently fall back to a synthetic hourly shape and stop
# being comparable to A2; --check verifies this before any time is spent.
# Checkpoints every config.CHECKPOINT_EVERY steps, so a killed task resumes.
#
#SBATCH --job-name=c1-day
#SBATCH --partition=long
#SBATCH --time=120:00:00
#SBATCH --mem=24G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/c1_day_%A_%a.out
# time/mem: copied from job_day.sh, whose four A2 tasks (array 117428, same
# graph, demand, steps and hour buckets) ran 8:28-13:59 at 24G with no OOM.
# C1 measured +30% wall on a corridor probe, so budget ~11-18 h; 120 h is the
# same wide ceiling A2 used and the long partition caps at 7 d.
# mem is 24G, not 16G, because "segments" hour buckets hold a sparse dict of
# up to ~0.9M entries (~150 MB, measured).

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/metro_c1_experiment.py --day-task "$SLURM_ARRAY_TASK_ID"
