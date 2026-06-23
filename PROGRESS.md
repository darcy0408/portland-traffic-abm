# Progress log

Newest entries on top. `/close-session` adds an entry here at the end of each work
session; `/start-session` reads it to remember where we left off. Each entry records
what we did, any decisions made, and the single most important next step.

---

## 2026-06-23 — Closure experiment built and run, plus the validation/closure/weather email to Christof

**Did:**
- **Closure experiment (Christof's Jun 23 idea) is built and run.** New code in
  `src/generate.py`: `config.CLOSURE` defines a (lat, lon, radius) zone,
  `closed_edges_in_zone` and `apply_closure` remove those segments, and
  `run_closure_experiment` runs the same demand twice (open, then closed) and saves
  both result files. `src/visualize.py` gained `plot_closure_diff`, which differences
  the two NO2 surfaces and colors each segment by the change (red = up, blue = down,
  closed segments highlighted). Run with `python src/generate.py closure` then
  `python src/visualize.py closure`.
- **Verified the closure result firsthand from the saved files** (joined the open and
  closed parquet files on segment id, then joined to the cached graph for street
  names). Closing a 150 m zone (24 segments) on Powell moves the network NO2 total by
  only -0.4% (4240.3 g -> 4222.4 g), but redistributes it onto the parallel detour
  routes: SE Holgate about +96% (nearly double), SE Division about +44%, and some
  low-baseline residential blocks (SE Gladstone, SE 22nd, SE 29th) rising several-fold.
  The redistribution, not the net change, is the thing Rao's static surface cannot
  produce. The before/after figure (`outputs/figures/powell_no2_closure_diff.png`)
  renders with a title and labeled colorbar; checked it against the numbers and the
  pattern agrees (blue along the closed Powell stretch, red on the parallel routes).
- **Finalized the email to Christof** (the post-Rao-talk follow-up: closures,
  validation, weather), ground-truthed every factual claim against the repo before
  sending. Three corrections from the verification pass: (1) upgraded the closure
  paragraph from "I think I can have a first version soon" to past tense with the real
  numbers, since it is done; (2) kept the precise ODOT AADT (34,900, 2018, 0.02 mi E of
  SE 26th) with its source, because DATASETS.md has full provenance; (3) corrected the
  PORTAL claim, Powell has no PORTAL volume loop, so the email anchors daily volume on
  ODOT AADT and uses the nearest freeway station only for the time-of-day shape. Email
  is sendable with no attachment (the figure is offered, to walk through live).
- **Saved a standing communication note.** Darcy strongly prefers email over in-person
  or live conversation (panics and goes mute when put on the spot; the same validation
  question that froze them in person got a sharp written answer). Recorded as a memory
  (communication-prefers-email) and as a standing note in `/start-session` so future
  sessions default to drafting emails rather than suggesting Darcy talk in person.
- Tightened `/close-session` step 4 so it flags a stale `CLAUDE.md` status when planned
  work gets *completed*, not only when direction changes (which is exactly what
  happened with the closure experiment this session).

**Decisions:**
- Closure zone left at the Powell center, 150 m radius, in `config.py`. The experiment
  can grow into a multi-scenario comparison later, but the scenario set is a "raise with
  Christof" decision, not something to expand unilaterally.
- Send the email with no attachment: the offer to show the closure figure live is a
  stronger move than sending a map Christof has to decode alone, and it suits Darcy's
  preference to communicate in writing and narrate the result when asked.

**Next step:**
- Send the email, then (unchanged from before) either wire the PORTAL+ODOT demand into
  `generate.py` or move to the week-6 land-use predictors + Rao random-forest
  comparison. Raise the closure experiment, the `F_NO2`/fleet-class calibration knobs,
  and the two noise leads with Christof.

---

## 2026-06-23 — Cross-edge spillback, the NO2 path (HBEFA3), and real demand data

**Did:**
- **Cross-edge spillback** in `src/generate.py`. A car with no leader on its own
  segment now looks across the downstream intersection to the next segment on its
  route. If cars are backed up there, the rearmost one acts as a leader sitting past
  the boundary, so the IDM brakes for it; a car is also held at the stop line instead
  of piling into a segment with no room. Verified on a dense run: mean speed ~4.8 m/s,
  ~21% of cars stopped, and max overshoot past any segment end = 0.0000 m (no
  overlaps). Jams now back up through intersections instead of vanishing at the block.
- **NO2 path (week-5 milestone, brought forward).** New `src/emissions.py` implements
  SUMO's HBEFA3 NOx(v, a) polynomial for a diesel Euro 4 passenger car (`PC_D_EU4`);
  the formula and coefficients were pulled from the SUMO source and cross-checked by a
  research agent against two release tags. `generate.py` now accumulates NOx grams per
  segment from each car's instantaneous speed and acceleration, alongside the old
  vehicle-seconds. `save_results` writes a `nox_g` column; `visualize.py` gained an NO2
  surface map (`python src/visualize.py no2`). Verified: the emission function
  reproduces the reference value exactly (6.140 mg/s cruising), no negative emissions,
  and the NO2 map concentrates on Powell and the arterials. A useful emergent result:
  the HBEFA3 idle term means a stopped car emits ~13 mg/s vs ~6 cruising, so congestion
  raises NOx, which is exactly the interaction effect the ABM exists to show.
- **Real demand data (option 3).** Pulled a real PORTAL hourly volume+speed profile
  (station 3032 on NB I-5, the nearest open volume station to Powell, ~2.8 km; no
  account needed) and verified the ODOT AADT for Powell (34,900 in 2018 at MP 2.09 by
  SE 26th, from the published 2018 report). New `src/demand_data.py` turns the PORTAL
  sample into 24 normalized hourly demand fractions (loads real data, sums to 1.0, AM
  peak 08:00, PM bump 15:00). `DATASETS.md` updated with the PORTAL API recipe and the
  verified AADT. The loader is NOT wired into the sim yet, on purpose.
- **Christof email (Jun 23).** He could not find Powell-specific noise data from the
  city, so that open request is effectively closed. This confirms Plan B and the
  model-to-model framing (no clean noise ground truth). He flagged two noise leads for
  the week-8 noise path: the OSU / Multnomah County Portland noise study (Bozigar and
  Mowrer, OSU College of Health; field measurements Aug 2023 to Aug 2024; a citywide
  10 m noise surface and a county interactive map are forthcoming) and a PowerBI
  dashboard (app.powerbigov.us).
- **Drafted the reply to Christof and verified every claim firsthand before sending.**
  Confirmed the OSU study's specifics against the published paper (Bozigar et al.
  2025, J. Expo. Sci. Environ. Epidemiol.: real Class 1 sound measurements, an
  ML-based noise surface, metrics DNL/Lden/L10; traffic proximity the biggest driver).
  Confirmed via screenshots that Christof's PowerBI link is the **City of Portland**
  Noise Complaints Dashboard (Title 18 complaints + 311 requests), which is complaint
  data, not measured levels, and is City of Portland, not Multnomah County. Corrected
  the draft to drop an unsupported "traffic complaints along Powell" claim and the
  county misattribution. Email is assembled and ready to send: it frames the OSU
  surface as the noise analog of the Rao comparison (their statistical ML surface vs
  the ABM's mechanistic one), with the ABM adding the rush-hour/queueing/time-of-day
  dynamics their long-term-average surface misses.
- **Added the OSU paper to `REFERENCES.md`** under a new "noise comparison (week 8)"
  section, tagged to read at the week-8 noise layer (commit f1b2293). Also saved as a
  memory (noise-data-leads) so `/start-session` resurfaces it.

**Decisions:**
- Store NOx in the sim and apply the NO2 fraction downstream (`NO2 = F_NO2 * NOx`,
  `F_NO2 = 0.30`), so the fraction is a tunable calibration knob that does not require
  rerunning the expensive run. Literature range is 0.20 to 0.30 (EMEP/EEA; Carslaw).
- Use HBEFA3 `PC_D_EU4` (diesel Euro 4) as the prototype fleet class. Both `F_NO2` and
  the fleet class are flagged in `config.py` to set with Christof at the calibration gate.
- Pulled demand data but did not wire time-of-day spawning into the sim this session:
  that changes the experiment structure and demand calibration is a "set with Christof"
  decision. New run renamed `RUN_NAME = "powell_no2"` so it keeps the earlier
  `powell_signals` before/after intact.

**Next step:**
- Wire the PORTAL profile + ODOT AADT into `generate.py` so the spawn rate follows the
  time of day (the four-step plan is in `demand_data.py`'s docstring), or move to the
  week-6 predictors + Rao random-forest comparison. Either way, raise the `F_NO2` /
  fleet-class calibration knobs and the two noise leads with Christof.

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
