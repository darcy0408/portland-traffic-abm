#!/bin/bash
# One task of the THROUGH_TRAFFIC_FRACTION sensitivity sweep (metro scale).
# Submit (metro graph must already be cached, see orca/RUNBOOK.md):
#   python src/metro_through_sweep.py --check          # refuses if anything is off
#   N=$(python src/metro_through_sweep.py --count)
#   sbatch --array=0-$((N-1)) orca/job_through_sweep.sh
# Same contract as the other array jobs: each task writes its own uniquely named
# parquet+summary under the thsw_ prefix (one-writer rule; the metrocal_* runs
# that supply the joined 0.15 baseline can never be touched), and run_one SKIPS
# on an existing parquet, so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=thsw
#SBATCH --partition=normal
#SBATCH --time=06:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/thsw_%A_%a.out
# time/mem MEASURED from the two closest precedents, then widened: the ablation
# (job 115208) ran this same realism stack on this same graph at this same
# demand for one simulated hour in 1:01-1:56 per task at 16G with no OOM, and
# the patience sweep (job 118055) took 2:14-3:40. The extra headroom here is
# deliberate: the high arms add through-traffic rather than removing it, so the
# 0.45 arm is the most congested configuration this project has ever run, and
# congestion is what makes these runs slow.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/metro_through_sweep.py --task "$SLURM_ARRAY_TASK_ID"
