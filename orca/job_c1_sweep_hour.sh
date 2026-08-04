#!/bin/bash
# C1 SWEEP HOUR jobs: band regression across REROUTE_STUCK_S, 4 values x 8 seeds.
# Submit:
#   N=$(python src/metro_c1_sweep.py --count)
#   sbatch --array=0-$((N-1)) orca/job_c1_sweep_hour.sh
# A longer patience means fewer re-plans and a shorter one means more, and either
# could push busiest Powell out of the real ODOT band of 1,400-1,745 veh/hr. The
# a-priori 120 s point is NOT re-run here: the existing c1_hour_* runs are it.
# Each task writes its own uniquely named parquet+summary (one-writer rule) and
# finished tasks SKIP on their existing parquet, so resubmitting is safe.
#
#SBATCH --job-name=c1sw-hour
#SBATCH --partition=normal
#SBATCH --time=06:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/c1sw_hour_%A_%a.out
# time/mem: identical shape to job_c1_hour.sh (same graph, demand, one simulated
# hour, rerouting on), whose tasks ran inside 6 h at 16G with no OOM. Patience
# changes only how OFTEN the re-plan pass fires, and it is capped by
# REROUTE_MAX_PER_STEP either way, so the 30 s arm cannot cost more per step than
# the 120 s arm already did -- the cap, not the trigger, sets the ceiling.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python -u src/metro_c1_sweep.py --task "$SLURM_ARRAY_TASK_ID"
