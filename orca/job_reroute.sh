#!/bin/bash
# One task of the rerouting re-validation: the lcap_realism_reallanes_n16500
# configuration with config.REROUTE_ENABLED = True (constants pinned to the
# committed defaults), 8 seeds, graded by the frozen 91-station PORTAL
# harness. Predictions are registered in src/reroute_runs.py and were
# committed before this was ever submitted.
#
# Submit (the widened graph must already be cached on the cluster):
#   python src/reroute_runs.py --check      # refuses if anything is off
#   sbatch --array=0-7 orca/job_reroute.sh
#
# Same contract as the other array jobs: each task writes its own uniquely
# named parquet+summary under the rrt_ prefix (one-writer rule; nothing
# already cited shares that prefix), and run_one SKIPS an existing parquet,
# so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=rrt
#SBATCH --partition=normal
#SBATCH --time=16:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/rrt_%A_%a.out
# limits copied from job_mergefix.sh (same demand, same graph). Rerouting adds
# up to 20 congestion-weighted Dijkstra calls per step; the C1 hour runs on a
# graph this size took 2:14-3:40, so 16 h holds ample headroom.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/reroute_runs.py --task "$SLURM_ARRAY_TASK_ID"
