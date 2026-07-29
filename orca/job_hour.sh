#!/bin/bash
# One HOUR-job of the metro calibrated experiment, as a SLURM array task.
# Submit (after orca/RUNBOOK.md setup is done):
#   N=$(python src/metro_calibrated_experiment.py --count)
#   sbatch --array=0-$((N-1)) orca/job_hour.sh
# Each task runs exactly one job from the harness's job list and writes its own
# uniquely named parquet, so parallel tasks never share a file (CLAUDE.md
# one-writer rule). Re-submitting is safe: finished jobs SKIP on their parquet.
#
#SBATCH --job-name=metrocal
#SBATCH --partition=normal
#SBATCH --time=04:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/metrocal_%A_%a.out
# time/mem are FIRST-GUESS values (metro runtime never measured on Orca); check
# the first finished task with `sacct -j <jobid> --format=Elapsed,MaxRSS` and
# tighten. If tasks hit the wall, raise --time or move to a longer partition.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# the venv was built against the spack python module; load it so the compute
# node has the same interpreter + runtime libs (no-op if lmod is absent)
source /etc/profile.d/z00_lmod.sh 2>/dev/null || true
module load python/3.12.12-gcc-13.4.0 2>/dev/null || true
source .venv/bin/activate
python src/metro_calibrated_experiment.py --task "$SLURM_ARRAY_TASK_ID"
