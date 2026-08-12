#!/bin/bash
# One task of the lever-A campaign (closure-aware corridor choice for through
# trips, pre-registered Aug 11; see src/freeway_corridor_levers.py docstring).
# Submit (metro graph must already be cached; --check verifies):
#   python src/freeway_corridor_levers.py --check
#   sbatch --array=0-23 orca/job_freeway_leverA.sh
# Same contract as the other array jobs: each task writes its own uniquely
# named parquet+summary under the fwla_ prefix, and run_task skips on an
# existing summary, so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=fwla
#SBATCH --partition=normal
#SBATCH --time=05:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwla_%A_%a.out
# time/mem from the fwms precedent (plain metro hour, ~2.5 h at 16G). Lever A
# adds one multi-source Dijkstra per through trip in place of the plain
# shortest-path call, a modest constant factor on spawn routing, so 5 h is a
# wide ceiling.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_corridor_levers.py --lever A --task "$SLURM_ARRAY_TASK_ID"
