# Progress log

Newest entries on top. `/close-session` adds an entry here at the end of each work
session; `/start-session` reads it to remember where we left off. Each entry records
what we did, any decisions made, and the single most important next step.

---

## 2026-06-26 (later) — DEQ monitoring plan: the citable backing for model-to-model

Short session, run alongside a separate demo-rehearsal agent. Touched only docs and
references (no sim, no code), so nothing raced with the demo work.

**Did:**
- **Read the 2023 Oregon DEQ Annual Ambient Criteria Pollutant Air Monitoring Network
  Plan** (the `AnnualACPAMNPlan` PDF Darcy downloaded). Confirmed the key fact firsthand:
  the entire Portland-Vancouver-Hillsboro metro (2.5M people) runs exactly TWO regulatory
  NO2 monitors, the SE Lafayette community/NCore site (AQS 41-051-0080, 45.4966 -122.6029)
  and one I-5 freeway near-road site (AQS 41-067-0005, AADT 153,822, 27 m from the road,
  reading well below the NAAQS). Neither is on Powell.
- **Turned that into the project's citable model-to-model justification.** Replaced the
  vague `DATASETS.md` section 6 placeholder ("a handful of sites") with the confirmed
  specifics, and added the plan to `REFERENCES.md` as [6] under a new "Why model-to-model"
  heading. This upgrades the honesty framing from an assertion to a primary-source fact:
  Portland genuinely lacks the dense NO2 sensor data a surface would need to be validated,
  which is exactly why the comparison is model-to-model.
- **Closed a dangling TODO.** The thing that prompted Darcy to pull the PDF was the old
  `DATASETS.md` section 6 note asking to check the DEQ sites; that loop is now resolved.
- Saved memory `deq-no2-monitoring-sparse` so future sessions resurface it for the chapter
  and the SIGSPATIAL abstract.

**Decisions:**
- Use the DEQ plan strictly as a CITATION for the model-to-model framing, NOT as a
  validation track (sensor-validation-as-spine is out of scope per CLAUDE.md). The one
  middle option, a single-point magnitude sanity check against the nearest monitor
  (SE Lafayette), is left as a Christof decision and a footnote at most, not built.
- Noted that this PDF is a network PLAN (monitor locations + siting rules), not measured
  concentrations; actual values come from EPA AQS by site ID if ever needed.

**Next step:**
- Unchanged from the main thrust: after Monday's demo, do the pinned-seed `N_VEHICLES=240`
  rerun and apply the two held noise snippets. When drafting the SIGSPATIAL abstract /
  chapter limitations, cite REFERENCES.md [6] for the "only two NO2 monitors in the metro"
  sentence.

---

## 2026-06-26 — Noise surface (2nd output) + demand calibration; demo/SIGSPATIAL agent work also landed

This session ran two efforts in parallel in the same repo, kept from colliding by the
project's iron rules (one sim at a time, never two processes writing the same data files,
no concurrent edits to the same source file). The split was deliberate: a demo/SIGSPATIAL
agent owned the closure/forest/abstract work and the only simulation runs; this session
took two streams that need NO sim run and only new files, so nothing raced.

**Did (this session, verified firsthand):**
- **Built the project's SECOND output surface: a road-traffic NOISE surface (CNOSSOS-EU).**
  New `src/noise.py` + `src/visualize_noise.py`. It runs no simulation: it reads an existing
  run's saved per-segment results and turns them into a per-segment dB(A) surface using the
  EU CNOSSOS road source method (rolling + propulsion noise, 8 octave bands, A-weighted),
  then a deliberately simple line-source geometric-divergence propagation to a 10 m receiver
  (every dropped term, ground/barriers/atmospherics/heavy vehicles, is documented; that is
  where the future FHWA TNM comparison plugs in). The surface is congestion-aware: realized
  per-segment speed is recovered as v_mean = length * throughput / value, so jammed Powell
  segments correctly emit more. Result on `powell_no2`: 2,838 segments, dB(A) min/median/max
  26.5 / 39.6 / 59.4, loudest streets Powell and Division (59.4), arterials brightest, dead
  streets silent. Per-vehicle sanity (96 dB(A) at 50 km/h) matches CNOSSOS cat-1 literature.
- **Verified the CNOSSOS coefficients against the primary source.** A focused check confirmed
  every category-1 coefficient (AR, BR, AP, BP), the reference speed (70 km/h), the band
  ordering, and the A-weighting array match Directive (EU) 2015/996 Appendix F Table F-1
  element by element (pulled from the official EUR-Lex PDF). No transposed digits, no sign
  errors. The source coefficients are publication-safe; the only caveats are the documented
  simplifications (cars-only, simplified propagation, undercalibrated flow).
- **Calibrated absolute demand against ODOT AADT, and found a real structural limit.** New
  `src/calibrate_demand.py` (read-only, uses ODOT AADT 34,900 only, PBOT counts untouched).
  Powell AADT converts to ~727 veh/hr average-hour directional and ~1,400-1,745 veh/hr
  peak-hour directional. At N_VEHICLES=500 the busiest Powell segment carries 1,070 veh/hr,
  1.47x over the average-hour target. The 24-hour data confirms HARD saturation: in the loaded
  regime input +94% yields throughput only +3%, the busiest segment pegged at ~1,011 veh/hr.
  This is a structural per-segment capacity ceiling (one following lane per directed segment
  under the assumed 60 s / 50%-green signal), not a tuning error, and it sits BELOW Powell's
  real peak directional volume, so demand cannot be scaled up to reach the peak. Recommendation:
  N_VEHICLES = 240 so the daily-average matches AADT/24 directional. The 240 value is
  interpolated and needs ONE pinned-seed rerun to confirm (held until after Monday's demo so
  the demo's locked numbers do not shift mid-presentation).

**Did (demo/SIGSPATIAL workstream, numbers confirmed firsthand in this same session):**
- **The headline figure** (`src/static_vs_abm.py`, `outputs/demo/5_static_vs_abm_closure.png`):
  the same closure two ways on one shared red/blue change scale. A static land-use model is blank
  (zero NO2 change on every segment) next to the ABM lighting up with redistribution. The
  geospatial contribution in one glance, and it needs nothing from Rao.
- **Robustness + generality** (`src/closure_sweep.py` + `closure_robustness.py`,
  `outputs/demo/7_closure_robustness.png`): closed three arterials (Powell, Division, Holgate)
  under 6 seeds each, 36 sims run serially per the one-sim rule. Closing an arterial removes 68 to
  80% of its own NO2 every time, std only 2 to 7 points (not seed noise), and the pattern holds for
  all three (a method, not a one-off).
- **Population exposure** (`src/exposure.py`, `outputs/demo/6_exposure_change.png`): the closure
  raises modeled NO2 for ~11,060 residents and lowers it for ~12,488 (+9.2% population-weighted).
  The human stake. Labeled relative modeled output, not measured air quality.
- **Stronger static baseline** (`src/landuse_model.py`): a 29-predictor Rao-style land-use forest
  (road length by class, intersection density, distance-to-major-road, plus pop/jobs over Rao's
  buffers) fits the ABM open surface at out-of-bag R^2 = 0.51 (the pop/jobs-only version was -0.16).
  Held FIXED across the closure, so it is still blank: the contrast now rests on a GOOD baseline,
  not a strawman.
- **Proof, validation framing, `SIGSPATIAL_ABSTRACT_MATERIAL.md`:** the invariance proof and the
  two-pronged validation (spatial Spearman 0.33, p=1.3e-7, 95% CI [0.19, 0.44]; temporal 0.88),
  plus the rest of the 2-page abstract building blocks.
- **Demo deck reworked to `Powell_ABM_demo_v4.pptx` (13 slides):** removed all Rao mentions and
  second-person phrasing, added a blue title theme (was all black-and-white), fixed the cramped
  validation slide, and added three contribution slides (money shot, robustness, exposure).
  `DEMO.md` updated to match (sections 5, 5b, 5c). Deck and figures stay gitignored.

**Decisions:**
- Deconflicted the two efforts by stream, not by file: this session took noise + calibration
  (no sim, new files only); the demo agent took the closure sweep, forest baseline, exposure,
  and abstract. This avoided two agents building the same thing or racing on shared files.
- Noise model is cars-only category 1 for v1, matching the project's single PC_D_EU4 emission
  class. Heavy vehicles are a documented limitation and a calibration knob for Christof.
- (demo workstream) Lead with the pinned seed-42 closure numbers as the reproducible
  representative (Division +132%, Powell -82%), and present the 6-seed ensemble (Division
  +93% +/- 41) as the robustness check. State both; never silently lead with the biggest number.
- (demo workstream) The static land-use model is held FIXED across the closure (a regression is
  not refit for a one-day event), which keeps the invariance argument airtight while the baseline
  stays genuinely well-fit. The closure contribution stands without Rao's sampler data, so the
  SIGSPATIAL story is not blocked on a data request that likely will not come.
- HOLD two convenience edits (a `noise` mode in visualize.py, a noise-knobs block in config.py)
  rather than apply them now, because the demo agent could still touch those shared files and
  the noise scripts run standalone without them. Apply next quiet session.
- HOLD the N_VEHICLES=240 rerun until after Monday's demo, so the demo's cited numbers stay
  frozen. Only one sim runs at a time regardless.

**Next step:**
- After Monday's demo (when the sim is free and the demo numbers no longer need freezing): do
  the single pinned-seed rerun to confirm N_VEHICLES = 240 (`generate.py` then
  `calibrate_demand.py`, expect busiest Powell 654-800 veh/hr), then apply the two held noise
  snippets. Raise with Christof the lane-capacity fork (lower demand to 240 vs model multi-lane
  capacity) and that the noise surface now exists with the FHWA TNM comparison as its next step.

---

## 2026-06-25 (demo prep) — Monday demo deck, locked results, Christof's results-first email

**Did:**
- **Decoded Christof's Jun 25 email.** He flagged that he has not seen results yet, wants
  the model validated with real data, and finds the GIS/geospatial contribution unclear.
  He is out starting Jul 4, so any SIGSPATIAL SRC submission (2-page abstract, Jul 10
  deadline) has to come together next week, with a go/no-go mid-week. Takeaway: Monday's
  demo is the moment to SHOW results.
- **Built the Monday demo deck** (PowerPoint, `C:\Users\Darcy\Downloads\Powell_ABM_demo_v3.pptx`,
  10 slides, outside the repo). Darcy wrote the speaker notes in their own voice; the deck
  carries those forward. New slides: a geospatial-contribution slide (answers "what's the
  GIS contribution": a network-responsive exposure surface, not a static map) and a
  quantified-closure slide.
- **Generated demo figures** (in gitignored `outputs/demo/`): a validation scatter (model
  vs real counts) plus a spatial agreement map, and a closure top-streets bar chart. Two
  read-only figure tasks were delegated to subagents, then everything was regenerated from
  locked data for consistency.
- **Locked the numbers (single source of truth).** The deck's numbers were stale. Did a
  clean deterministic run (deleted the checkpoint first) and settled the authoritative
  values: traffic validation Spearman rho = 0.33 (model throughput vs real PBOT/county ADT,
  n=247); closure shifts NO2 off SE Powell (-82%) onto the parallel arterial SE Division
  (+132%, the clean headline), SE Holgate (+54%), and residential side streets. Total NO2
  barely changes; the result is the spatial redistribution.
- **Kept Rao off the demo slide** at Darcy's request: the NO2 forest comparison is framed
  as "built and ready, runs if/when the target data arrives", not an active ask.

**Decisions:**
- **Monday's goal is a convincing demo, not a finished project.** Christof's bar is results
  he can see; his decision point is mid-next-week.
- **Single-source-of-truth for numbers:** run the sim once, lock the data, and have every
  figure and slide read from that one result. Codified in CLAUDE.md this session.

**Next step (IMPORTANT consistency check):**
- Parallel commits today (gravity-model spatial demand, 24-hour time-of-day) may have
  changed the DEFAULT simulation. Before Monday, re-verify the demo's numbers (Spearman
  0.33, SE Division +132%, and the "demand is still uniform random" claim on the slide)
  against the final committed code, and update the deck if they shifted. Then rehearse the
  v3 deck end to end. Optional upside: a second closure scenario and a demand-weighting
  attempt.

---

## 2026-06-25 (later) — Temporal dimension: 24-hour NO2 surfaces and their validation

**Did:**
- **Brainstormed where to take the project** now that the code is ahead of schedule, and
  picked the **temporal dimension** as the highest-leverage next move: in-spec (it deepens
  the core ABM, not scope creep), already half-built (demand_data.py existed), and it
  strengthens the exact model-to-model comparison the project rests on. The ABM can
  produce an NO2 surface PER HOUR; Rao's single static surface cannot. (Pairs with the
  spatial-demand work logged in the entry below, done the same day.)
- **Built the 24-hour time-of-day experiment** (`python src/generate.py day`,
  `run_day_experiment`). Each hour is an independent steady-state run whose vehicle count
  is scaled by the real PORTAL hourly profile, with config.N_VEHICLES kept as the
  daily-average population. Writes 24 hourly surfaces to one file with an `hour` column.
  Result: a clean two-peak commuter day, AM peak at 08:00 (~10,000 g network NO2) vs
  ~440 g at the 01:00 quiet hour. The gravity spatial demand rides along automatically.
- **Visualization** (`python src/visualize.py day` and `day-anim`): a network-total NO2
  curve, a 24-panel shared-scale hourly map grid, and a looping GIF (1.7 MB). The
  animation was delegated to a sub-agent and verified.
- **Wrote `src/validate_day.py`.** Two checks. (1) Face validity: realized throughput
  tracks the input demand shape (Pearson 0.90 / Spearman 0.88), so the model reproduces
  the shape it was driven with. (2) The congestion finding: a car at the 08:00 peak emits
  **+43% more NO2** than at the quiet hour (11.6 vs 8.1 g/car) purely from queueing, the
  interaction effect a static flow-times-a-factor surface cannot produce. The check also
  surfaced **capacity saturation**: per-hour throughput flattens from ~6am, because at 500
  daily-average vehicles the peak hours saturate the network. That is realistic congestion
  AND a calibration signal that the absolute demand magnitude is set too high.
- **Committed today's work as clean, logically-separate commits**: temporal dimension
  (6e48163), gravity demand (a3aad93), and a docs cleanup (5eb78fb: DATASETS.md 5b plus a
  fix to a stale landuse_data.py docstring that said decay was omitted when the code
  implements it).

**Decisions:**
- Build the temporal dimension now, and do NOT send Christof a third email about it this
  week (two are already pending). Show the artifact at the next meeting instead.
- Use the simple "24 independent hourly runs, count scaled by profile" design (Option A)
  rather than one continuous 24-hour run, so the validated car-following kernel is reused
  untouched.
- Co-Authored-By trailer included on the Claude-authored commit, omitted on the
  Darcy-authored ones (pending Darcy's call on the AI-acknowledgment policy).

**Next step:**
- Bring the temporal-dimension figures (day profile, map grid, GIF) and the honest "what
  worked / what didn't" gravity result to the next small-group meeting (the prototype-demo
  venue). After Christof replies to the two pending emails, calibrate the absolute demand
  magnitude (the saturation finding points to lowering the daily-average count / anchoring
  it on ODOT AADT) and re-check. If SIGSPATIAL is cleared, draft the 2-page abstract before
  the Jul 10 deadline.

---

## 2026-06-25 — Routing by travel time (win), gravity spatial demand (honest negative result), closure refreshed

**Did:**
- **Routing by travel time, not distance.** Real drivers minimize time, which favors
  faster arterials, exactly where real counts concentrate. One-line change (every edge
  got a `travel_time_s` weight; `make_vehicle` routes on it). It raised the PBOT rank
  correlation (real ADT vs model throughput, 247 segments) from **0.26 to 0.38**. Kept.
- **Gravity spatial demand model.** Built `src/landuse_data.py` to pull two real,
  no-key, PBOT-independent sources: Census 2020 Centers of Population (19 block groups,
  23,548 residents, with centroids) for the home end, and LODES8 jobs (12,389 jobs) for
  the work end. `generate.py:build_demand_weights` snaps that mass to network nodes
  (Voronoi split, so it is a smooth density, not point sources), and `make_vehicle` now
  draws origins proportional to population and destinations proportional to jobs, with an
  exponential distance-decay pull toward nearer jobs. New config knobs: `DEMAND_GRAVITY`,
  `LODES_YEAR`, `GRAVITY_DECAY_SCALE_M`.
- **Honest negative result.** The gravity demand did NOT improve the PBOT match
  (0.38 -> 0.345 no decay, 0.328 with 1500 m decay). Worked out why: this metric is
  dominated by network structure, which uniform-random demand already captures via
  betweenness on the arterials. Adding home-work structure just makes traffic lumpier.
  Deliberately stopped tuning the decay scale, because sweeping it to beat 0.38 would be
  quietly fitting the held-out PBOT counts and would wreck the test.
- **Refreshed the closure experiment** under the new demand+routing model and verified it
  firsthand from the saved files. Closing the 150 m Powell zone now raises total NO2
  +2.1% (was -0.4%, because detours are genuinely longer/slower) and redistributes it:
  SE Powell -82% in the closed stretch, SE Division +132% (more than doubles), SE Holgate
  +54%, SE Gladstone +140%, side streets multi-fold. Figure re-rendered.
- **Documented** both data sources and the validation finding in `DATASETS.md` (new
  section 5b); updated the `CLAUDE.md` current-phase status (validation, closure numbers,
  simplifications). Survived a parallel-editing collision that briefly clobbered the
  `generate.py` routing/gravity edits, then merged cleanly with the new `day`-mode work
  and confirmed the merged file reproduces the numbers.

**Decisions:**
- Keep routing-by-time (principled, and a clear win).
- Keep `DEMAND_GRAVITY = True` by default, even though it slightly lowers the static rank
  metric, because the closure and time-of-day experiments need realistic destinations.
  Report BOTH numbers (0.38 structure-only benchmark, 0.35 full model) with the
  explanation, which is exactly the honest, Occam-vs-realism nuance Christof wants.
- Decay scale fixed a priori at 1.5 km, NOT tuned against PBOT, to keep the test honest.
- No second email to Christof today: SIGSPATIAL already went out this morning. Fold the
  routing win, the gravity negative result, and the demand-design answer into the single
  later update once he replies, so questions do not land on him all at once.

**Next step:**
- Refresh and rehearse the prototype demo (`DEMO.md`) for Monday's (Jun 29) small-group
  meeting, updating the closure talking points to the new numbers (SE Division +132%,
  total +2.1%). Hold the combined Christof update until his replies (Rao site data,
  SIGSPATIAL clearance, demand design); send nothing new today.

---

## 2026-06-25 — Real-world traffic validation (PBOT), the SIGSPATIAL SRC email, and chapter logistics

**Did:**
- **Traffic-layer validation against real PBOT counts (Christof's Jun 25 ask).** New
  `src/traffic_counts.py` (pulls the PBOT Traffic Volume Counts layer, clean API, no
  scraper needed) and `src/validate_traffic.py` snap ~2,221 real count points onto the
  model's streets (1,654 within 40 m, landing on 247 distinct segments) and compute a
  Spearman rank correlation of real ADT vs the model. Rank, not raw levels, because
  demand is still uniform random. **Honest correction along the way:** the first pass
  used vehicle-seconds (which over-counts queued blocks); a new per-segment throughput
  counter (true vehicle count, the apples-to-apples match for ADT) raised the
  correlation from **0.16 to 0.26**, a moderate positive match. So the road structure
  is partly right before any demand calibration. Re-ran it this session to confirm the
  numbers firsthand before they went in an email (+0.158 activity, +0.261 throughput).
  GitHub Actions CI now runs the scenario test-bench on every push (README badge).
- **SIGSPATIAL 2026 SRC email finalized.** Verified the facts before drafting: undergrad
  Student Research Competition, 2-page extended abstract, due **Jul 10**, conference in
  Riverside in November, and the lead author must be an ACM student member (Darcy joined,
  so that gate is cleared). Reframed the contribution to lead with the **road-closure
  scenario** (the case Christof flagged, where the ABM beats a static land-use model),
  with NO2 framing rather than noise. Email is ready, pending Christof's OK on three
  questions: permission, proceedings/ACM double-submission conflict, and NSF REU travel
  funding.
- **Traffic-validation email finalized.** Tightened the result email (leads with +0.26,
  states the n=247, one demand-design question) and verified every number against a live
  run first.
- **Summer Proceedings chapter logistics (Christof's Jun 24 email).** The chapter is a
  mandatory, sole-author deliverable. Added to `ROADMAP.md`: sign up with a tentative
  title by **Sun Jul 12**, and the three chapter-writing lectures (Jul 1 sources/lit
  review, Jul 8 title/abstract/intro, Jul 22 methods/results/discussion/conclusion) are
  the Wednesday research slots, not optional. Editors-in-chief Fatima and Muhammad.
  Recommended tentative title saved. New memory `proceedings-chapter-deadlines`.
- **Reading.** Roberts 2017 notes done (logged Jun 24); Michanowicz is next.

**Decisions:**
- Send the two Christof emails separately and **spaced** (validation now, SIGSPATIAL at
  4pm via a calendar reminder) so several questions do not land on him at once.
- Proposed demand-calibration plan (pending Christof's read): set demand from sources
  independent of the PBOT counts (ODOT AADT as a volume anchor + a population/employment
  gravity model for the spatial pattern) and **hold the PBOT counts out as the test set**.
  This is the same independent-test-set discipline as the Roberts paper.
- Pursue the SIGSPATIAL SRC submission, contingent on Christof clearing the three questions.

**Next step:**
- After Christof replies: calibrate demand from the independent sources, hold PBOT out,
  and re-check the rank correlation. If SIGSPATIAL is cleared, draft the 2-page abstract
  from the chapter material before the Jul 10 deadline.

---

## 2026-06-24 — Surprise-meeting redirect: validation test-bench, demo figures, week-6 predictor groundwork

**Did:**
- **Surprise Zoom with Christof (Jun 24).** He redirected the focus: forget the
  rigid week-by-week plan and make progress day to day; the job now is to produce
  EVIDENCE the model works via simple, human-checkable test scenarios, and to build
  a prototype demo for the next meeting (ideally alongside Fatima). His framing:
  treat Claude as a collaborator you supervise and verify, not a black box to read
  line by line. He also addressed the imposter feeling directly: building checkable
  scenarios is exactly what lets you own and vouch for the model.
- **Validation test-bench (`src/scenarios.py`).** Runs four scenarios through the
  REAL kernel (idm_acceleration + step_vehicles, never a reimplementation): one car
  accelerating to the limit, two cars following without collision, one car stopping
  at a red light, and 1,500-car saturation. All four pass, with numbers predictable
  by hand: follower gap settles to 9.58 m vs 9.5 m by formula; the car stops exactly
  s0 = 2 m short of the stop line; under load mean speed drops 9.3 -> 4.5 m/s and
  ~31% of cars are stopped. Controlled runs save a per-second trace.
- **Scenario evidence plots.** Added a `scenarios` mode to `visualize.py`: a
  four-panel evidence sheet (speed-to-limit, gap settling, speed convergence,
  stop-at-line). Fixed panel 4 to plot cumulative route distance so the line stays
  monotonic across the segment crossing (pos alone resets to 0 on each new segment).
- **Full demo figure set + runbook.** Rendered the activity, NO2, and before/after
  closure figures, and wrote `DEMO.md`: each of Christof's asks mapped to one
  command and one talking point, with a setup block so the whole demo runs live in
  under a minute (figures also pre-saved as backup).
- **Week-6 predictor groundwork (`src/predictors.py`).** Turns an ABM run's
  per-segment output into Rao-style multi-buffer (100 to 1200 m) traffic predictors;
  added `BUFFER_RADII_M` to `config.py`. This is the decision-independent machinery
  both forests need, built ahead of the comparison itself.
- **Rao data request sent.** Asked Christof for Rao et al.'s NO2 sampler site
  coordinates and values (the shared target the forest comparison needs). Confirmed
  firsthand (from the open-access paper) the buffer recipe is 100-1200 m in 100 m
  steps, 174 summer / 82 winter Ogawa sites, authors Rao/George/Shandas/Rosenstiel.
  The per-site coords+values are NOT public (not in the supplement or dissertation,
  only a site map), so they must come from the authors; Christof thinks the data
  traces to a past student.
- **Git housekeeping.** Consolidated three feature branches onto `main` via a clean
  fast-forward and deleted the merged branches, so `main` is the single source of
  truth again.
- **Weather second surface started privately** (gitignored `sandbox/`, not in the
  repo). `sandbox/weather/fetch_weather.py` pulls real Portland hourly rain/wind from
  the Open-Meteo API for the study coordinates; `sandbox/weather/rain.py` builds a
  rain-adjusted NO2 surface driven by the real rainy-hour fraction (~10% in June 2024,
  so the monthly-average NO2 is only ~3% lower). Scoped as future work per Christof,
  kept out of the repo until ready to promote.
- **Confirmed the meeting picture from transcripts.** The Jun 24 cohort meeting was a
  general grad-school session (no project feedback). The next small-group meeting
  (Darcy + Fatima + Christof) is Monday and is the venue for the prototype demo; the
  formal cohort presentation slot is July 7.
- **Reading (the 30% paper time).** Read Roberts 2017 (spatial cross-validation) and
  wrote independent reading notes in my own words (claim, method, relevance to the ABM,
  citable lines with page/figure pointers, questions for Christof/Nik), then sharpened
  them through feedback. Project takeaway: evaluate the ABM forest and the Rao baseline
  with the SAME spatial block cross-validation, matched to the prediction goal, so the
  comparison is not inflated by spatial autocorrelation (nearby segments are not
  independent, so random CV would let a test segment lean on its training-set neighbor).
  This is also deliberate practice at the paper-reading and notetaking skill itself, not
  just the content. Michanowicz is next. Drafted the REUnite daily blurb.

**Decisions:**
- Pivot the near-term priority from the week-6 Rao forest to validation + the demo,
  per Christof's redirect. The forest is deferred behind the demo and behind getting
  Rao's site data.
- Test scenarios must call the real simulation functions, never a reimplementation,
  or they prove nothing.
- Do not re-hunt Rao's per-site data online; it is confirmed not public.
- **Plan for not getting Rao's site data** (Christof thinks it unlikely). Fallbacks,
  simplest first: (1) ask for Rao's modeled NO2 *surface* instead of raw sites, a
  lower-friction ask that enables a surface-to-surface comparison; (2) lean on the
  parts that need no external data (the closure result and the noise path) as the
  headline contribution; (3) build the full forest pipeline as a validated method,
  ready to run when any target appears. The Powell-only vs wider-network and raw-data
  vs modeled-surface forks are explicitly Christof's call.

**Next step:**
- Assemble and rehearse the prototype demo for the next meeting (run `DEMO.md` end
  to end). Once Christof replies with Rao's site data (or an agreed substitute
  target), resume the random-forest comparison using the predictor groundwork in
  `src/predictors.py`.

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
