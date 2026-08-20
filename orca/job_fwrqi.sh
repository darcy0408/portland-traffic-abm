#!/bin/bash
# One task of the improved-model Rose Quarter arm (prereg Appendix K, prefix
# fwrqi): the paired open/closed campaign of PREREG_I5_ROSEQUARTER.md run on
# the PORTAL-validated stack (realism + corrected real lanes on the
# lane-tagged graph; MERGE_ENTRY_IMPROVED and REROUTE_ENABLED explicitly
# False). Registered as a dated public appendix BEFORE submission.
#
# Submit (the lane-tagged graph must already be cached on the cluster):
#   python src/freeway_rosequarter.py --check --improved   # frozen-span guard
#   sbatch --array=0-15 orca/job_fwrqi.sh
#
# Same contract as the other array jobs: each task writes its own uniquely
# named summary under the fwrqi_ prefix (one-writer rule) and skips if its
# summary exists, so resubmission after a partial failure is safe.
#
#SBATCH --job-name=fwrqi
#SBATCH --partition=normal
#SBATCH --time=16:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwrqi_%A_%a.out
# limits copied from job_reroute.sh (same graph, same demand); recent runs on
# this stack took 2:15-3:00 per task and closed arms run longer, 16 h holds.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_rosequarter.py --task "$SLURM_ARRAY_TASK_ID" --improved
