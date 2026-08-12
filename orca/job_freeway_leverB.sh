#!/bin/bash
# One task of the lever-B campaign (congestion-aware initial routing via one
# iterated-assignment pass, pre-registered Aug 11; see
# src/freeway_corridor_levers.py docstring). Submit (--check verifies inputs):
#   python src/freeway_corridor_levers.py --check
#   sbatch --array=0-23 orca/job_freeway_leverB.sh
# Same contract as the other array jobs: each task writes its own uniquely
# named parquet+summary under the fwlb_ prefix, and run_task skips on an
# existing summary, so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=fwlb
#SBATCH --partition=normal
#SBATCH --time=10:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwlb_%A_%a.out
# time/mem from the fwms precedent (~2.5 h at 16G for one plain metro hour).
# Lever B runs the WHOLE simulation twice (pass 1 measures, pass 2 reports),
# so the ceiling is doubled and widened to 10 h.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_corridor_levers.py --lever B --task "$SLURM_ARRAY_TASK_ID"
