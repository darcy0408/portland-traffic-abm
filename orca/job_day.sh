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
#SBATCH --time=120:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/metrocal_day_%A_%a.out
# time: measured hour-jobs ran 1h (base) / 2h (realism), so a day run is
# ~24-48h of stepping; 120h leaves honest headroom (long partition caps at 7d).

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# the venv is built on the SYSTEM python3 (3.9), which runs on every node --
# the spack python modules are compiled for a newer microarch and SIGILL on
# the login node, so we deliberately do not use them.
source .venv/bin/activate
python src/metro_calibrated_experiment.py --day-task "$SLURM_ARRAY_TASK_ID"
