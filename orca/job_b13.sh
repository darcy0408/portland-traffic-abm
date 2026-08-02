#!/bin/bash
# One HOUR-job of the Phase B1 x B3 experiment (turn pockets x non-work demand),
# as a SLURM array task.
#
# BEFORE SUBMITTING, run the prerequisite check on the login node -- both
# features refuse loudly at run time by design, and finding that out in 24
# failed tasks is a waste:
#   source .venv/bin/activate
#   python src/metro_b13_experiment.py --check
# It verifies the turn:lanes sidecar exists AT THE METRO RADIUS
# (data/network/turn_lanes_20000m.json -- data/ is gitignored, so it must be
# scp'd from the workstation), the LODES WAC file the non-work service-job
# table reads, the metro graph, and the 8 control summaries the readout joins.
#
# Submit:
#   N=$(python src/metro_b13_experiment.py --count)
#   sbatch --array=0-$((N-1)) orca/job_b13.sh
# Each task runs exactly one job and writes its own uniquely named parquet, so
# parallel tasks never share a file (CLAUDE.md one-writer rule). Re-submitting
# is safe: finished jobs SKIP on their parquet.
#
#SBATCH --job-name=b13
#SBATCH --partition=normal
#SBATCH --time=04:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/b13_%A_%a.out
# time/mem are MEASURED, not guessed: the Jul 31 ablation array (job 115208,
# same graph, same 16,500 demand, same one simulated hour, 16G) ran its tasks
# in 1:01-1:56 with no OOM and no wall hit. These arms add a turn-pocket queue
# and a second demand layer, both small, so 4 h and 16G keep the same headroom.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# the venv is built on the SYSTEM python3 (3.9), which runs on every node --
# the spack python modules are compiled for a newer microarch and SIGILL on
# the login node, so we deliberately do not use them.
source .venv/bin/activate
python src/metro_b13_experiment.py --task "$SLURM_ARRAY_TASK_ID"
