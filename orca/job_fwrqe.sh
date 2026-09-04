#!/bin/bash
# One task of the en-route rerouting arm (prefix fwrqe, prereg Appendix T):
# the paired open/closed campaign of PREREG_I5_ROSEQUARTER.md on the fwrqi
# stack and the FULL closure VERBATIM, with one mechanism change only:
# config.REROUTE_ENABLED on the "on" cells (a car stuck below the stuck speed
# for 120 s re-plans to its unchanged destination on congestion-aware
# weights; cooldown 300 s, <= 20 re-plans/step, all registered constants).
#
# DISCLOSURE (travels with every fwrqe number): the C1 mechanism FAILED its
# registered acceptance gate (ledger RR35.1, Burnside 1.88x vs the 2x bar,
# replicated in the combined arm) and is NOT part of the citable model. This
# arm runs it as a disclosed exploratory fidelity axis, registered pre-run.
#
# Four cells in one flat 32-task array (one-writer rule, no races):
#   tasks  0-7   rerouting OFF, open    (fwrqeoff_open_s*)
#   tasks  8-15  rerouting OFF, closed  (fwrqeoff_rosequarter_s*)
#   tasks 16-23  rerouting ON,  open    (fwrqe_open_s*)
#   tasks 24-31  rerouting ON,  closed  (fwrqe_rosequarter_s*)
# The OFF pair reruns fwrqi with measurement-only stuck instrumentation (the
# fwrq/fwrqi campaigns never saved the stuck_sum column): its per-seed
# equality with the banked fwrqi summaries is a registered integrity check
# (--readout runs it and refuses to grade past a mismatch), and it supplies
# the paired baseline for the stuck vehicle-hour predictions (T1/T2).
#
# Submit (the lane-tagged graph must already be cached on the cluster):
#   python src/freeway_rosequarter.py --check --reroute   # span + context
#   python src/reroute_scenarios.py                       # the 6-check gate
#   sbatch --array=0-31 orca/job_fwrqe.sh
#
# Same contract as the other array jobs: each task writes its own uniquely
# named summary (one-writer rule) and skips if its summary exists, so
# resubmission after a partial failure is safe.
#
#SBATCH --job-name=fwrqe
#SBATCH --partition=normal
#SBATCH --time=16:00:00
#SBATCH --mem=40G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwrqe_%A_%a.out
# limits from job_fwrqc.sh (same graph, same demand, same stack). The "on"
# cells add Dijkstra calls (<= 20/step by the registered compute budget); the
# rrt re-validation ran the same mechanism at this scale in under 3 h, so the
# fwrqi-sized 16 h window holds with a wide margin.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_rosequarter.py --task "$SLURM_ARRAY_TASK_ID" --reroute
