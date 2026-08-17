#!/bin/bash
# One task of the lane-capacity sweep: does correcting the OSM lane counts move
# the metro throughput ceiling? Predictions are registered in the harness
# docstring and were committed before this was ever submitted.
#
# Submit (the WIDENED graph must already be cached on the cluster, see below):
#   python src/lane_capacity_sweep.py --check      # refuses if anything is off
#   N=$(python src/lane_capacity_sweep.py --count)
#   sbatch --array=0-$((N-1)) orca/job_lane_capacity.sh
#
# The widened graph is data/network/graph_metro20k_lanes.graphml, produced by
# src/build_capacity_graph.py and copied up rather than downloaded here: --check
# and --task both REFUSE to fetch it mid-experiment, so no task can silently run
# against a different network than its siblings.
#
# Same contract as the other array jobs: each task writes its own uniquely named
# parquet+summary under the lcap_ prefix (one-writer rule; nothing already cited
# shares that prefix), and run_one SKIPS an existing parquet, so resubmitting
# after a partial failure is safe.
#
#SBATCH --job-name=lcap
#SBATCH --partition=normal
#SBATCH --time=16:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/lcap_%A_%a.out
# time/mem widened well past the demand sweep's 08:00:00 / 16G, which covered
# demands up to 24,750 in 1:18-3:00 per task. This sweep goes to 41,250, which
# is 1.67x that vehicle count, and congestion cost is superlinear near
# saturation, so both limits get real headroom rather than a tight estimate.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/lane_capacity_sweep.py --task "$SLURM_ARRAY_TASK_ID"
