#!/bin/bash
# One paired multi-seed freeway-closure run as a SLURM array task.
# Submit (metro graph must already be cached, see orca/RUNBOOK.md):
#   N=$(python src/freeway_multiseed.py --count)
#   sbatch --array=0-$((N-1)) orca/job_freeway.sh
# Same contract as job_ablation.sh: each task writes its own uniquely named
# parquet+summary (one-writer rule) and finished tasks SKIP on their summary,
# so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=fwms
#SBATCH --partition=normal
#SBATCH --time=04:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwms_%A_%a.out
# time/mem copied from job_ablation.sh. These runs are the plain metro hour
# (16,500 vehicles, no realism stack), which measured ~25 min locally, so 4 h
# is a wide ceiling.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_multiseed.py --task "$SLURM_ARRAY_TASK_ID"
