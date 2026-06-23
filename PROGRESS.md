# Progress log

Newest entries on top. `/close-session` adds an entry here at the end of each work
session; `/start-session` reads it to remember where we left off. Each entry records
what we did, any decisions made, and the single most important next step.

---

## 2026-06-22 — Week 3 kickoff: Jun 22 check-in tasks + first vehicles on the network

**Tasks/decisions from Christof's Jun 22 cohort check-in:**
- Parameterize the prototype (network size, vehicle count as config variables) so it
  scales. Christof: "valid for both of you."
- Get an early computational-complexity read this week: time small runs, watch how
  runtime grows. Front-loads part of the Week 4 runtime benchmark.
- Spend ~30% of time finding critical public datasets (traffic counts/AADT, emission
  factors, land cover, signal locations). Dispatched research agents; results go to
  DATASETS.md.
- Framework decision resolved: hand-roll on NetworkX now, switch to RePast/Mesa/
  NetLogo later only if needed. Christof endorsed.
- Correction noted: the "separate synthetic-data module / import real data" advice in
  that meeting was for Fatima's project, not this one.
- These are recorded in ROADMAP.md under "Week 3-4 additions from the Jun 22 check-in."

**Did (build):**
- Wired vehicles into `src/generate.py`: each vehicle gets a random origin,
  destination, and shortest-path route, then drives the OSMnx network one second at
  a time using the IDM kernel, following the car ahead on its segment. Vehicles
  respawn with a new trip on arrival so density stays steady. Per-segment activity
  (vehicle-seconds) accumulates as the slot where emissions/noise plug in later.
- Added `prepare_network` (desired speed per edge from maxspeed tags or a road-class
  default) and a `benchmark` mode (`python src/generate.py benchmark`).
- Sanity check: cars accelerate to ~their segment speed limit (mean ~23 mph), no
  NaNs, activity concentrates on busier edges.
- **Runtime read (Christof's ask):** on the 978-node Powell network, runtime is
  linear in vehicle count at ~335k vehicle-steps/s. 500 vehicles x 3600 steps is
  ~6 s. The approach is comfortably viable at this scale; room to grow the network.
- Dataset research compiled into `DATASETS.md` (PORTAL + ODOT AADT for volumes,
  NLCD for land-use predictors, SUMO-HBEFA3 for emissions, PBOT for signals).
- Heat-map visualization: upgraded `plot_segment_map` in `visualize.py` to a proper
  normalized colormap (sqrt color scale, width by activity, dark bg, colorbar).
  Powell and the arterials light up; activity concentrates on main roads as expected.
- **Week 4 brought forward, done: traffic signals + queueing.** Signalized
  intersections come from real OSM `traffic_signals` node tags (21 on the Powell
  network), each running a simple two-phase cycle (E-W vs N-S alternate green, with
  a per-node offset). A red light is modeled as a stopped virtual leader at the stop
  line, so cars brake smoothly via IDM and wait at the line until green. Congestion
  emerges: with signals on, mean speed drops (~10.1 -> ~9.1 m/s) and queues of
  several cars stack behind reds. Timing is a documented assumption (per-signal plans
  are not public). Re-ran as `powell_signals`; the earlier `powell_baseline` is the
  no-signals before/after.

**Known simplifications (next to address):**
- A car only sees the leader on its own segment, so a queue longer than a block does
  not yet spill back through the upstream intersection (cross-edge spillback).
- Signal timing is a uniform assumed cycle, not real per-signal plans, and demand is
  uniform random trips, not real time-of-day volumes from PORTAL/ODOT.
- Segment totals are vehicle-seconds, a placeholder where per-vehicle NO2 (HBEFA)
  plugs in next.

**Next step (options for next session):**
- Cross-edge spillback so queues can back up across intersections (sharpens the
  congestion dynamics).
- Or jump to the week-5 NO2 path: per-vehicle emissions via the SUMO-HBEFA3 NOx(v,a)
  coefficients (DATASETS.md), accumulated per segment instead of vehicle-seconds.
- Calibration data: pull a PORTAL volume/speed profile and an ODOT AADT for Powell to
  start grounding the synthetic demand.

---

## 2026-06-20 — Car-following kernel, project planning, and Rao talk prep

**Did:**
- Built the IDM (Intelligent Driver Model) car-following function in
  `src/generate.py` and sanity-checked it: a lone car accelerates to the speed
  limit and flattens; a car approaching a stopped car brakes smoothly to a clean
  stop at the minimum gap. Put the IDM parameters in `config.py`.
- Added a sim-free network map (`python src/visualize.py network`) and confirmed
  the study area by eye (Ladd's Addition starburst is the giveaway landmark).
- Created `ROADMAP.md`: a real week-by-week schedule (weeks 3-10, Jun 22 to the
  Aug 14 symposium) with hard deadlines and recurring program obligations.
- Upgraded `/start-session` to run a drift + schedule + loose-ends health check
  each session, measured against the spec and the (gitignored) class reference.
- Saved class reference material privately (REU_reference.md and two lecture PDFs
  in reference/, both gitignored). Added `REFERENCES.md` (public bibliography) for
  the four papers Christof sent.
- Replied to Christof's email (sound-wall fact sheet, references, Powell data).
- Did a full first pass on the Rao baseline paper and wrote a complete 12-slide
  talk with speaker notes for the Jun 23 key-paper presentation (saved in
  Downloads, outside the repo).

**Decisions:**
- Use IDM for car-following (not a cell-based model) because per-vehicle NO2
  emissions depend on acceleration, which IDM gives at every step.
- Open question to raise with Christof: build the ABM directly on NetworkX (as we
  are) vs the Mesa framework the training suggested. Hand-rolled is defensible
  since we need continuous acceleration and are not doing reservoir computing.

**Next step:**
- Finish prepping the Jun 23 Rao paper talk (build the actual slides from the
  speaker notes), since that deadline is fixed and closest. Then start the week-3
  build: vehicles moving on the real network with routes, driven by the IDM
  kernel.

---

## 2026-06-17 — Environment + network download working

**Did:**
- Installed the Python stack: added osmnx and pyarrow (networkx, numpy, pandas, matplotlib were already present).
- Replaced the canonical `CLAUDE.md` with Darcy's authoritative spec; added private `CLAUDE.local.md` and gitignored it.
- Downloaded and cached the Powell street network: 978 intersections, 2,838 segments, ~4 seconds. Verified the disk cache reloads in 0.1 s.

**Decisions:**
- Define the study area by an explicit center point and radius, not a place-name string. The name "SE Powell Blvd" geocoded to a tiny wrong fragment and the download failed. Center is on Powell by Cleveland High School, radius 1.5 km. This is reproducible and tunable for the runtime benchmark.
- First runtime data point: 1.5 km radius is effectively instant, so the area has room to grow later.

**Next step:**
- Build car-following vehicle movement inside the marked stub in `src/generate.py` `run_simulation()`. Optional quick win first: draw a map of the downloaded network in `visualize.py` to confirm the study area by eye.

---

## 2026-06-17 — Project setup

**Did:**
- Cloned the repo and added the scaffold (config, requirements, `src/` modules, `.gitignore`).
- Added `CLAUDE.md` (project brief, auto-read each session) and this `PROGRESS.md`.
- Added `/start-session` and `/close-session` slash commands.
- Granted Claude read access to Downloads and Screenshots folders (on-demand only).

**Decisions:**
- Keep generation and visualization in separate scripts (re-plot without re-running the sim).
- Baselines fixed: Rao-style land-use random forest (NO2) and FHWA reference (noise).
- If full-city sim is too slow, fall back to the Powell Boulevard corridor (Plan B).

**Next step:**
- Build **car-following vehicle movement** (Week 2 milestone) inside the marked stub
  in `src/generate.py` `run_simulation()`. No simulation code exists yet.
