#!/bin/bash
# One task of the access-lane closure-geometry arm (prereg Appendix O, prefix
# fwrqa): the paired open/closed campaign of PREREG_I5_ROSEQUARTER.md run on
# the fwrqi stack VERBATIM (realism + corrected real lanes on the lane-tagged
# graph; MERGE_ENTRY_IMPROVED and REROUTE_ENABLED explicitly False), with one
# difference only: the closed arm keeps ODOT's announced local-access lane,
# I-405 junction to the Broadway/Weidler exit (302A), clamped to 1 lane, off-
# ramp kept, instead of the full-span shutdown the other arms model. The open
# arm is configured identically to fwrqi's open arm, so per-seed equality of
# the two open arms' summaries is a registered integrity check, and the
# fwrqa-vs-fwrqi closed-arm contrast isolates closure GEOMETRY with the
# behavioral stack held fixed. Registered as a dated public appendix BEFORE
# submission.
#
# Submit (the lane-tagged graph must already be cached on the cluster):
#   python src/freeway_rosequarter.py --check --accesslane   # span + clamp guard
#   sbatch --array=0-15 orca/job_fwrqa.sh
#
# Same contract as the other array jobs: each task writes its own uniquely
# named summary under the fwrqa_ prefix (one-writer rule) and skips if its
# summary exists, so resubmission after a partial failure is safe.
#
#SBATCH --job-name=fwrqa
#SBATCH --partition=normal
#SBATCH --time=16:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwrqa_%A_%a.out
# limits copied from job_fwrqi.sh (same graph, same demand, same stack); its
# tasks took 2:15-3:00 and closed arms run longer, 16 h holds.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_rosequarter.py --task "$SLURM_ARRAY_TASK_ID" --accesslane
