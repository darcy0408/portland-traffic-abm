#!/bin/bash
# One task of the demand-magnitude (N vehicles) sensitivity sweep (metro scale).
# Submit (metro graph must already be cached, see orca/RUNBOOK.md):
#   python src/metro_demand_sweep.py --check          # refuses if anything is off
#   N=$(python src/metro_demand_sweep.py --count)
#   sbatch --array=0-$((N-1)) orca/job_demand_sweep.sh
# Same contract as the other array jobs: each task writes its own uniquely named
# parquet+summary under the dmsw_ prefix (one-writer rule; the metrocal_* runs
# that supply the joined 16,500 baseline can never be touched), and run_one
# SKIPS on an existing parquet, so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=dmsw
#SBATCH --partition=normal
#SBATCH --time=08:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/dmsw_%A_%a.out
# time/mem widened from the measured precedents: the patience sweep (118055)
# ran this realism stack at n=16,500 in 2:14-3:40 per task at 16G with no OOM,
# and the through sweep (118339) at up to 0.45 share ran under 2:10. The
# n=24,750 arm here carries 1.5x the vehicles of any of those, and congestion
# cost is superlinear near saturation, so the limit gets real headroom.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/metro_demand_sweep.py --task "$SLURM_ARRAY_TASK_ID"
