# Orca runbook — metro calibrated experiment

The metro-scale calibrated-demand experiment (CALIBRATED_DEMAND_PLAN.md
Phase 3/4) on PSU's Orca cluster. Account verified live Jul 27:
`ssh darcy-csuglobal@login.orca.pdx.edu` (SLURM; partitions short / normal /
long / osg).

Everything below runs ON ORCA unless marked [laptop].

## 1. Clone the repo and check out this branch

```bash
git clone https://github.com/darcy0408/portland-traffic-abm.git
cd portland-traffic-abm
git checkout experiment/traffic-realism
mkdir -p logs
```

## 2. Python environment (one-time)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

(If `python3` is too old — need 3.9+ — try `module avail python` and load a
newer one first.)

## 3. Demand input data

[laptop] Copy the three Census/LODES inputs from the local worktree so the run
uses byte-identical inputs to every prior run (they would auto-download from
Census otherwise, which is a silent version risk):

```powershell
scp C:\dev\pta-realism\data\raw\cenpop2020_bg_or.txt `
    C:\dev\pta-realism\data\raw\or_od_main_2021.csv.gz `
    C:\dev\pta-realism\data\raw\or_wac_2021.csv.gz `
    darcy-csuglobal@login.orca.pdx.edu:portland-traffic-abm/data/raw/
```

## 4. Cache the metro graph (one-time, ~minutes)

The 20 km graph is not in the repo (data/ is gitignored) and the Jul 6-7 metro
cache lives only on Colab's Drive. Download a fresh one on Orca:

```bash
python src/metro_calibrated_experiment.py --cache-graph
```

Prints node/edge counts and the number of Powell edges (must be nonzero).
HONEST NOTE: this is today's OSM, not the graph behind the M20.* numbers —
this experiment stands on its own graph and never re-cites M20 results.
(Alternative, only if graph identity with M20 matters: download
`abm/data/network/graph.graphml` from the Colab Google Drive by hand and scp it
into `data/network/`.)

## 5. Smoke one task interactively before the array

```bash
srun --partition=short --time=01:00:00 --mem=16G \
     python src/metro_calibrated_experiment.py --task 0
```

Watch it print the one-line summary. Note its wall time and peak memory
(`sacct -j <jobid> --format=Elapsed,MaxRSS`) and adjust `orca/job_hour.sh`
if the 4 h / 16 G first guesses are off.

## 6. Submit the hour-job array (48 jobs)

```bash
N=$(python src/metro_calibrated_experiment.py --count)
sbatch --array=0-$((N-1)) orca/job_hour.sh
squeue -u darcy-csuglobal          # watch
```

Finished jobs write `data/processed/metrocal_*_segments.parquet`; re-submitting
the array is safe (each task SKIPs if its parquet exists), so a partial failure
is fixed by just submitting again.

## 7. Submit the day jobs (2 jobs, long partition)

```bash
N=$(python src/metro_calibrated_experiment.py --count-day)
sbatch --array=0-$((N-1)) orca/job_day.sh
```

Day jobs checkpoint, so a wall-clock kill resumes on resubmit.

## 8. Bring results home and read them out

[laptop]

```powershell
scp "darcy-csuglobal@login.orca.pdx.edu:portland-traffic-abm/data/processed/metrocal_*" `
    C:\dev\pta-realism\data\processed\
python src\metro_calibrated_readout.py
```

(That glob brings both the `_segments.parquet` files and the `_summary.json`
headline files; the readout needs only the summaries, the parquets feed later
figure/map work. Map figures additionally need the metro graph — scp
`data/network/graph.graphml` home too before drawing maps.)

The readout (analysis-only, reads the summaries, never re-runs) prints the Phase 3
table: per arm x demand, mean +/- SD over seeds of busiest-Powell veh/hr vs the
real 1,400-1,745 band, Powell vehicle-hours, stuck vehicle-hours, and NOx.

## Discipline notes

- Every task sets its own seed and RUN_NAME (in the name), writes its own file:
  parallel array tasks never violate the one-writer-per-file rule.
- The seed list, demand levels, and arms live in
  `src/metro_calibrated_experiment.py` — the single source of truth.
- The graph guard refuses corridor-sized graphs for metro jobs, so a wrong or
  missing cache fails loudly instead of mislabeling a corridor run.
