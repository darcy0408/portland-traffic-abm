#!/bin/bash
# One ablation job (realism-stack feature attribution) as a SLURM array task.
# Submit (after orca/RUNBOOK.md setup; the metro graph must already be cached):
#   N=$(python src/metro_ablation_experiment.py --count)
#   sbatch --array=0-$((N-1)) orca/job_ablation.sh
# Same contract as job_hour.sh: each task writes its own uniquely named
# parquet+summary (one-writer rule), finished jobs SKIP on their parquet, so
# re-submitting after a partial failure is safe.
#
#SBATCH --job-name=aba
#SBATCH --partition=normal
#SBATCH --time=04:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/aba_%A_%a.out
# time/mem copied from job_hour.sh, where the metrocal hour runs measured
# ~1 h (base) to ~2 h (realism); every ablation arm is a subset of the
# realism stack, so 4 h is a comfortable ceiling.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/metro_ablation_experiment.py --task "$SLURM_ARRAY_TASK_ID"
