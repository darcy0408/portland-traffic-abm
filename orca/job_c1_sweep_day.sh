#!/bin/bash
# C1 SWEEP DAY jobs: does the cleared freeze survive a different driver patience?
# 4 new REROUTE_STUCK_S values x seed 42 x 86,400 steps.
# Submit:
#   N=$(python src/metro_c1_sweep.py --count-day)
#   sbatch --array=0-$((N-1)) orca/job_c1_sweep_day.sh
# This is the arm that protects the Aug 3 headline (freeze clears, stuck -84.7%),
# which currently rests on a 120 s constant with no direct source.
# Needs data/portal_powell_sample.csv on this machine (data/ is gitignored) or
# the profiled arms silently fall back to a synthetic hourly shape and stop being
# comparable to A2 or C1; --check verifies this before any time is spent.
# Checkpoints every config.CHECKPOINT_EVERY steps, so a killed task resumes.
#
#SBATCH --job-name=c1sw-day
#SBATCH --partition=long
#SBATCH --time=120:00:00
#SBATCH --mem=24G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/c1sw_day_%A_%a.out
# time/mem: same shape as job_c1_day.sh, whose realism task (array 117851_1) ran
# 23:52 at 24G with no OOM. Budget generously rather than tightly -- a run that
# CLEARS the freeze completes trips and keeps stepping a busy network all day,
# whereas a run that freezes stops doing work, so the fast/slow ordering here is
# not the usual one. 120 h is the same wide ceiling C1 used; long caps at 7 d.
# mem is 24G, not 16G, because "segments" hour buckets hold a sparse dict of up
# to ~0.9M entries (~150 MB, measured).

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python -u src/metro_c1_sweep.py --day-task "$SLURM_ARRAY_TASK_ID"
