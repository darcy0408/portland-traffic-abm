#!/bin/bash
# One task of the pre-registered Rose Quarter I-5 SB closure campaign.
# Submit (run --check FIRST; it verifies the frozen span on this graph):
#   python src/freeway_rosequarter.py --check
#   N=$(python src/freeway_rosequarter.py --count)
#   sbatch --array=0-$((N-1)) orca/job_freeway_rosequarter.sh
# Same contract as the other array jobs: each task writes its own uniquely
# named parquet+summary under the fwrq_ prefix, and run_task skips on an
# existing summary, so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=fwrq
#SBATCH --partition=normal
#SBATCH --time=06:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwrq_%A_%a.out
# time/mem from measured precedent: fwms/fwmsr tasks at the same flat 16,500
# vehicles ran 2:12-2:24 at 16G; 6 h is that with headroom, no peak-demand
# arms in this campaign.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_rosequarter.py --task "$SLURM_ARRAY_TASK_ID"
