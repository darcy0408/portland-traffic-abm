#!/bin/bash
# One full-DAY job (24 simulated hours) of the metro calibrated experiment.
# Submit:
#   N=$(python src/metro_calibrated_experiment.py --count-day)
#   sbatch --array=0-$((N-1)) orca/job_day.sh
# Day jobs checkpoint every config.CHECKPOINT_EVERY steps, so a killed task
# resumes from its last checkpoint on re-submit instead of starting over.
# LODES demand is commute-shaped (flat over the day) -- the acknowledged caveat.
#
#SBATCH --job-name=metrocal-day
#SBATCH --partition=long
#SBATCH --time=48:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/metrocal_day_%A_%a.out
# time is a FIRST GUESS (~24x an hour job's stepping); tighten after task 0.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# the venv was built against the spack python module; load it so the compute
# node has the same interpreter + runtime libs (no-op if lmod is absent)
source /etc/profile.d/lmod.sh 2>/dev/null || true
module load python/3.12.12-gcc-13.4.0 2>/dev/null || true
source .venv/bin/activate
python src/metro_calibrated_experiment.py --day-task "$SLURM_ARRAY_TASK_ID"
