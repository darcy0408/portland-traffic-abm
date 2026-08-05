#!/bin/bash
# C1 x closure: one paired freeway-closure task with the realism stack on PLUS
# en-route rerouting (config.REROUTE_ENABLED), asking whether the I-5 diversion
# null survives when stuck cars can re-plan around congestion.
# Submit (metro graph must already be cached, see orca/RUNBOOK.md):
#   N=$(python src/freeway_multiseed.py --reroute --count)   # 24, block-1 seeds
#   sbatch --array=0-$((N-1)) orca/job_freeway_reroute.sh
# Same contract as job_freeway_realism.sh: each task writes its own uniquely
# named parquet+summary (one-writer rule, prefix fwrr so the fwms/fwmsr
# campaigns' files can never be touched) and finished tasks SKIP on their
# summary, so resubmitting after a partial failure is safe.
#
#SBATCH --job-name=fwrr
#SBATCH --partition=normal
#SBATCH --time=08:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=1
#SBATCH --output=logs/fwrr_%A_%a.out
# time/mem MEASURED, not guessed: the C1 hour runs (realism + rerouting, same
# graph, same demand) took 2:14-3:40 per task with 16G and no OOM, and the
# closed arms here are MORE congested than C1's open network (more stuck cars,
# so more Dijkstra calls), so 8 h widens the measured ceiling instead of
# trusting it to transfer.

set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
# system-python venv, not the spack modules (they SIGILL on the login node)
source .venv/bin/activate
python src/freeway_multiseed.py --reroute --task "$SLURM_ARRAY_TASK_ID"
