#!/bin/bash
# One task of the merge-fix re-validation: the lcap_realism_reallanes_n16500
# configuration with config.MERGE_ENTRY_IMPROVED = True, 8 seeds, graded by
# the frozen 91-station PORTAL harness. Predictions are registered in
# src/mergefix_runs.py and were committed before this was ever submitted.
#
# Submit (the widened graph must already be cached on the cluster):
#   python src/mergefix_runs.py --check      # refuses if anything is off
#   sbatch --array=0-7 orca/job_mergefix.sh
#
# Same contract as the other array jobs: each task writes its own uniquely
# named parquet+summary under the mfix_ prefix (one-writer rule; nothing
# already cited shares that prefix), and run_one SKIPS an existing parquet,
# so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=mfix
#SBATCH --partition=normal
#SBATCH --time=16:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/mfix_%A_%a.out
# limits copied from job_lane_capacity.sh, whose 16,500-demand tasks fit them
# with headroom; this campaign runs the same demand on the same graph.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/mergefix_runs.py --task "$SLURM_ARRAY_TASK_ID"
