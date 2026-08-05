#!/bin/bash
# One task of the peak-vs-quiet freeway closure campaign (metro scale).
# Submit (metro graph and PORTAL csv must be present, --check verifies):
#   python src/freeway_peak_quiet.py --check
#   N=$(python src/freeway_peak_quiet.py --count)
#   sbatch --array=0-$((N-1)) orca/job_freeway_peakquiet.sh
# Same contract as the other array jobs: each task writes its own uniquely
# named parquet+summary under the fwpq_ prefix, and run_task skips on an
# existing summary, so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=fwpq
#SBATCH --partition=normal
#SBATCH --time=08:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwpq_%A_%a.out
# time/mem from measured precedent, widened for the peak arms: the fwmsr
# campaign at flat 16,500 ran 2:12-2:24 per task at 16G; the peak level
# carries roughly 1.5x that demand plus a closure, and congestion cost is
# superlinear near saturation. The quiet arms are small and fast.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_peak_quiet.py --task "$SLURM_ARRAY_TASK_ID"
