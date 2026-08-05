#!/bin/bash
# F6 rerun: one paired freeway-closure task WITH the realism stack on.
# Submit (metro graph must already be cached, see orca/RUNBOOK.md):
#   N=$(python src/freeway_multiseed.py --count)
#   sbatch --array=0-$((N-1)) orca/job_freeway_realism.sh
# Same contract as job_freeway.sh: each task writes its own uniquely named
# parquet+summary (one-writer rule, prefix fwmsr so the base campaign's fwms_*
# files can never be touched) and finished tasks SKIP on their summary, so
# resubmitting after a partial failure is safe.
#
#SBATCH --job-name=fwmsr
#SBATCH --partition=normal
#SBATCH --time=04:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwmsr_%A_%a.out
# time/mem MEASURED, not guessed: ablation array 115208 ran the same realism
# stack on the same graph at the same demand for one simulated hour in
# 1:01-1:56 per task with 16G and no OOM, so 4 h is a wide ceiling.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_multiseed.py --realism --task "$SLURM_ARRAY_TASK_ID"
