#!/bin/bash
# One task of the combined-arm re-validation: the lcap_realism_reallanes_n16500
# configuration with BOTH config.MERGE_ENTRY_IMPROVED and config.REROUTE_ENABLED
# (reroute constants pinned to committed defaults), 8 seeds, graded by the
# frozen 91-station PORTAL harness. Predictions are registered in
# src/combo_runs.py and were committed before this was ever submitted.
#
# Submit (the widened graph must already be cached on the cluster):
#   python src/combo_runs.py --check       # refuses if anything is off
#   sbatch --array=0-7 orca/job_combo.sh
#
# Same contract as the other array jobs: each task writes its own uniquely
# named parquet+summary under the cmb_ prefix (one-writer rule; nothing
# already cited shares that prefix), and run_one SKIPS an existing parquet,
# so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=cmb
#SBATCH --partition=normal
#SBATCH --time=16:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/cmb_%A_%a.out
# limits copied from job_reroute.sh (same demand, same graph). The rrt tasks
# ran 2:34-2:55 and mfix ~2:15; the combo should land in the same range, and
# 16 h holds ample headroom.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/combo_runs.py --task "$SLURM_ARRAY_TASK_ID"
