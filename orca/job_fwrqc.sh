#!/bin/bash
# One task of the signed-detour compliance arm (prefix fwrqc): the paired
# open/closed campaign of PREREG_I5_ROSEQUARTER.md run on the fwrqi stack and
# the FULL closure VERBATIM, with one difference only: each through trip (its
# OPEN-network route crosses the closed span's south exit) follows ODOT's
# official I-405 detour with a registered probability instead of picking its
# own fastest route. Three a-priori compliance levels (25 / 50 / 75%) rather
# than one guess; the open arm is share-independent, so ONE shared set of open
# tasks serves all three levels, in a single 32-task array so no two levels
# ever race to write the same open summary:
#   tasks  0-7   open      (fwrqc_open_s*)
#   tasks  8-15  closed at 0.25 (fwrqc25_*)
#   tasks 16-23  closed at 0.50 (fwrqc50_*)
#   tasks 24-31  closed at 0.75 (fwrqc75_*)
# Per-seed equality of fwrqc_open with fwrqi_open is a registered integrity
# check (--readout runs it). Registered as a dated public appendix BEFORE
# submission.
#
# Submit (the lane-tagged graph must already be cached on the cluster):
#   python src/freeway_rosequarter.py --check --compliance     # span + guards
#   python src/freeway_rosequarter.py --selftest --compliance  # spawn identity
#   sbatch --array=0-31 orca/job_fwrqc.sh
#
# Same contract as the other array jobs: each task writes its own uniquely
# named summary (one-writer rule) and skips if its summary exists, so
# resubmission after a partial failure is safe.
#
#SBATCH --job-name=fwrqc
#SBATCH --partition=normal
#SBATCH --time=16:00:00
#SBATCH --mem=40G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwrqc_%A_%a.out
# limits from job_fwrqa.sh (same graph, same demand, same stack) with memory
# raised 32G -> 40G: the closed tasks hold a SECOND copy of the metro graph
# (the open network the eligibility test routes on), and each spawn pays one
# extra shortest-path call there. fwrqi tasks took 2:15-3:00; 16 h holds.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_rosequarter.py --task "$SLURM_ARRAY_TASK_ID" --compliance
