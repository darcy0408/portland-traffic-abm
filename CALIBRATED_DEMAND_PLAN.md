# Calibrated real-demand experiment (the Aug 14 spine)

**Goal (Darcy's, stated Jul 28):** run the model at *real Portland street
demand* — real lane counts, Powell carrying its real peak-hour volume
(~1,400–1,745 veh/hr directional, from ODOT AADT 34,900) — and report, for
1-lane vs real-lanes: **how much pollution, how many cars are on the corridor,
and how many are stuck in jams**, validated against the real counts. The
overnight lanepoll sweep compared *model* demand levels; this compares at
*reality's* demand level. That distinction is the point.

**Key diagnostic fact the sweep exposed:** with real lanes (Powell = 2–3 lanes
in-model, matching OSM), the busiest segment peaks ~1,270 veh/hr at N=1500 and
*declines* at N=1800 — the model gridlocks *below* real Powell peak volume.
Real Powell carries 1,400–1,745 at peak *while flowing* (~600–700/lane, under
saturation). So the binding constraint is NOT lanes — it is **how demand loads
onto the corridor** (routing/structure), consistent with every standing
finding. Phase 1 finds the mechanism; Phase 2 fixes the dial; Phase 3 measures
the answer.

## Phase 0 — Pin the targets (read-only, ~30 min)
- Pull the real numbers from `calibrate_demand.py` (main) + the PBOT counts
  parquet: Powell busiest-segment peak-hour target (1,400–1,745) and
  average-hour (~727); grab targets for Division/César Chávez/Holgate too if
  counts exist (calibrate on Powell, sanity-check the others).
- Decide the calibration split honestly: the dial is tuned to the ODOT Powell
  AADT (already the project's calibration source); the held-out PBOT counts
  stay validation-only. Write this down in the results doc.

## Phase 1 — Diagnose why the model gridlocks early (mostly read-only, ~1 evening)
Read the existing 96 lanepoll parquets + 2–3 instrumented diagnostic runs:
- Where are cars stuck at N=1500–1800? (speed-moments → mean speed per segment;
  map the low-speed segments — is the jam ON Powell, on its cross streets, or
  network-wide spillback from side streets?)
- How much of Powell's flow is through-traffic vs local gravity trips? (The
  through-context assigns cordon trips; count them.) Hypothesis: at
  THROUGH_TRAFFIC_FRACTION=0.30, Powell's arrival rate is capped well below
  real peak — real Powell is through-dominated; the model's demand isn't.
- Deliverable: one sentence naming the binding constraint, with evidence.

## Phase 2 — Calibrate the demand dial (runs: a sweep, multi-seed)
- Sweep the demand-structure levers with real lanes ON until the busiest
  Powell segment ≈ real peak while the network still flows:
  N_VEHICLES × THROUGH_TRAFFIC_FRACTION (and, if Phase 1 implicates it,
  through-trip arterial weighting). A-priori structure, ONE dial calibrated to
  the observed Powell volume — documented, not hidden.
- Accept honestly reporting failure if no setting reaches real peak without
  gridlock: "the model cannot yet carry real Powell demand, and here is the
  structural reason" is a real result (and the metro/LODES lever is the known
  fix — corridor gravity demand was always the weak link).

## Phase 3 — THE experiment, at calibrated demand (8 seeds)
At the calibrated setting, 1-lane vs real-lanes:
- **Pollution:** corridor + network NOx (per-second emission = idling counts).
- **Cars on the corridor:** vehicle-hours on Powell (existing `value` column).
- **Cars stuck:** add a small OPT-IN stopped-time accumulator (pattern:
  `speed_stats` — keyword-only, off by default, kernel-regression bit-identical
  proof) so "vehicle-hours below 5 km/h" is measured, not inferred.
- **Validation:** modeled busiest-segment veh/hr vs the real count, said
  plainly ("model carries X vs real Y").
- Deliverables: the two-panel figure at calibrated demand, a stuck-cars map,
  and the numbers table (mean ± SD over seeds).

## Phase 4 — Orca (the parallel + metro stretch)
- Account is live (`ssh darcy-csuglobal@login.orca.pdx.edu`, SLURM).
- Clone the public repo on Orca, `scp` the cached corridor graph, submit the
  Phase 2/3 sweeps as `sbatch --array` jobs (the harness already takes
  `--task N`).
- Stretch: the metro-scale calibrated version with LODES OD on (the demand
  structure that actually has real origin–destination information).

## Governance (unchanged)
One sim at a time; every run a unique RUN_NAME; seeds pinned & recorded; new
accumulators opt-in + provably inert off; figures/readouts read parquets only;
nothing merged to main without an explicit decision.
