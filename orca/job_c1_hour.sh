#!/bin/bash
# C1 HOUR jobs: the peak-hour band regression check, 2 arms x 8 seeds.
# Submit:
#   N=$(python src/metro_c1_experiment.py --count)
#   sbatch --array=0-$((N-1)) orca/job_c1_hour.sh
# A day result is uninterpretable if rerouting wrecks the peak-hour band on the
# way, so this runs alongside the day pair rather than after it.
# Each task writes its own uniquely named parquet+summary (one-writer rule) and
# finished tasks SKIP on their existing parquet, so resubmitting is safe.
#
#SBATCH --job-name=c1-hour
#SBATCH --partition=normal
#SBATCH --time=06:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/c1_hour_%A_%a.out
# time/mem MEASURED, not guessed: ablation array 115208 ran the same graph and
# demand for one simulated hour in 1:01-1:56 at 16G with no OOM. C1 measured
# +30% wall on a corridor probe, and tasks co-locating on one node has twice
# been observed to cost ~2.4x -- 6 h covers the pessimistic product of both.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python -u src/metro_c1_experiment.py --task "$SLURM_ARRAY_TASK_ID"
