# Portland Traffic ABM

## What this project is

An agent-based model (ABM) of interacting vehicles on Portland's OSMnx street
network. Vehicles follow one another, queue at signals, and back up in
congestion. From those interactions the model produces street-segment surfaces
of traffic NO2 and noise. The contribution is that the agent simulation
generates the predictors, which are then fed into the same statistical method a
published baseline used, so the comparison isolates what source-based
interaction modeling adds over static estimation.

NSF REU "Computational Modeling Serving Portland," PSU Teuscher Lab. Mentor:
Christof Teuscher. Sole student on this project.

## The spec (do not drift from this)

- The method is an ABM with vehicles on an OSMnx network. It is not a
  statistics-first or ML-first project. The vehicle interactions (car-following,
  signal queueing, congestion) are what justify using an ABM at all.
- Outputs are two surfaces, NO2 and noise, at street-segment resolution.
- NO2 path: the agent simulation produces predictors that are fed into a random
  forest, the same method Rao et al. used, and compared against Rao's
  land-use-fed random forest. Per-vehicle NO2 emissions use HBEFA factors.
- Noise path: modeled mechanistically with CNOSSOS and compared against the FHWA
  Traffic Noise Model reference.
- The comparison is model-to-model, not model-to-ground-truth. Portland lacks
  dense sensor data, so success is a rigorous comparison between methods, not a
  claim of absolute accuracy. This is framed honestly as a feature, not hidden.
- Success is defined by doing the comparison rigorously, regardless of which
  method wins. The research question is falsifiable: the agent-fed forest may
  not beat the baseline, and that is still a valid result.
- Numeric calibration gates are set with Christof after seeing data, not invented
  in advance.
- Build order: the core vehicle model comes first. Car-following before anything
  else.

## Out of scope (removed or deferred, do not add back)

- No pollen layer. It was removed from the project entirely.
- No sensor ground-truth validation as the spine (no PurpleAir or DEQ validation
  framing). The project compares models, not measurements.
- No routing or "best route given exposure" feature as the core. Routing under
  constraints is a solved engineering problem and is not the research.
- No reservoir computing or ML-regression layer in the current scope. It is a
  possible later extension to raise with Christof, not something to build now.
- Heat and pollen reference layers are out. Noise and NO2 only.

If any planning document mentions pollen, sensor validation, or routing as the
core, it is a stale early draft. This file is the current truth.

## Architecture conventions

- Keep data generation and visualization in separate scripts. generate.py runs
  the simulation, checkpoints, and writes results to disk, and does no plotting.
  visualize.py reads those files and makes figures, and runs no simulation. This
  lets figures be redrawn without rerunning the expensive simulation.
- generate.py checkpoints so a crash or disconnect never loses more than a few
  minutes of work, and resumes from the last checkpoint.
- All parameters, paths, and the random seed live in config.py. The same config
  reproduces the same numbers.
- The seed in config.py is always pinned before any run whose numbers will be
  cited (a slide, the email to Christof, the chapter, the abstract). An unpinned
  seed makes each run produce different numbers, so a cited figure can never be
  reproduced. If two runs of the same experiment disagree, suspect the seed first.
- One simulation runs at a time. Never start a second generate.py run that writes
  the same data files while another is still running. Two programs writing the
  same file at once can corrupt it, with no warning.
- Figure, demo, and report work reads the existing data files. It never re-runs
  the simulation to make a picture. The simulation is run once by generate.py to
  produce the authoritative data files; everything downstream reads those files.
  This is the single-source-of-truth rule: compute the numbers once, then have
  every figure and document copy from that one result instead of recomputing.
- Do not commit generated data or figures. data/ and outputs/ are gitignored and
  get archived separately at the end.
- Cache the OSMnx graph once and reuse it, since downloads are slow.
- Add comments as code is written, not in a later cleanup pass.

## Current phase

Week 3 (started Mon Jun 22), and ahead of schedule (weeks 4 and 5 are already
done). The core ABM runs end to end on the cached Powell network (978 nodes, 2,838
edges): vehicles get random origin/destination routes and drive segment by segment
using the IDM kernel, following the car ahead. Week-4 work is done: 21 real
OSM-tagged signalized intersections run a two-phase cycle, cars queue at red
lights, and queues now spill back across intersections (a car with no leader on its
own segment brakes for a queue backed up on the next segment and holds at the stop
line instead of overlapping into it). Congestion emerges (mean speed drops, queues
stack), the interaction-driven behavior that justifies the ABM. Week-5 work is also
done: the NO2 path. Per-vehicle NOx comes from SUMO's HBEFA3 NOx(v,a) polynomial
(diesel Euro 4, PC_D_EU4; src/emissions.py), fed by each car's instantaneous speed
and acceleration and accumulated as grams per segment. The sim stores NOx; the NO2
surface is NO2 = F_NO2 * NOx, applied in visualization so the fraction (0.30,
literature range 0.20-0.30) retunes without rerunning. visualize.py renders an
activity map, an NO2 map, and a before/after closure-difference map. Runtime stays
fast and linear (~10 s for 500 vehicles over a simulated hour). Vehicle count and
network size are config parameters (Christof's Jun 22 ask). Powell stays the
proof-of-concept and Plan B. The Jun 23 key-paper talk on the Rao baseline is built
and ready (on Drive, outside the repo).

Jun 24 redirect (Christof, surprise meeting): forget the rigid week plan and focus on
producing evidence the model works, via simple human-checkable test scenarios, plus a
prototype demo for the next meeting. Built src/scenarios.py, a validation test-bench
that runs four scenarios through the real kernel (one car to the speed limit, two cars
following without collision, one car stopping at a red light, 1,500-car saturation);
all four pass with values predictable by hand. visualize.py gained a `scenarios` mode
(a four-panel evidence sheet), and DEMO.md is a runbook mapping each of Christof's asks
to one command and one talking point. This validation/demo work is now the near-term
priority; the week-6 Rao forest is deferred behind it and behind getting Rao's
sampler-site data. The ABM-side predictors are already scaffolded (src/predictors.py:
per-segment activity aggregated over config.BUFFER_RADII_M buffers, matching Rao's
setup, with NOx excluded so the ABM's own NO2 answer cannot leak into the features).

Closure experiment is built and run (Christof's Jun 23 idea, the case where the ABM
beats a static land-use surface). config.CLOSURE defines a (lat, lon, radius) zone;
generate.py runs the same demand twice (open, then with the zone's segments removed
so vehicles reroute) and visualize.py differences the two NO2 surfaces (python
src/generate.py closure, then python src/visualize.py closure). Result on Powell
(under the gravity-demand + time-routing model, refreshed Jun 25): closing a 150 m
zone (24 segments) raises the network NO2 total a little (+2.1%, because the detours
are longer and slower) and redistributes it onto the parallel routes the detour
traffic picks up: SE Powell drops about 82% in the closed stretch, while SE Division
roughly doubles (+132%), SE Holgate about +54%, SE Gladstone about +140%, and
low-baseline side streets rise several-fold. That redistribution, not the net change,
is what Rao's static surface cannot produce.

Real public data is now pulled (DATASETS.md): a real PORTAL hourly volume+speed
profile (nearest open station to Powell), the verified ODOT AADT for Powell (34,900
in 2018 at SE 26th), and, for spatial demand, Census 2020 block-group population and
LODES8 jobs near Powell (src/landuse_data.py; both no-key and independent of the held-out
PBOT counts). src/demand_data.py turns the PORTAL sample into 24 normalized hourly demand
fractions, now wired into the sim via the `day` experiment (python src/generate.py day),
which runs one steady-state hour per hour-of-day scaled by that profile. visualize.py
renders the day as a network-total NO2 curve, a 24-panel shared-scale map grid, and a
looping GIF (python src/visualize.py day / day-anim). src/validate_day.py checks it:
realized throughput tracks the input demand shape (Spearman 0.88), confirming face
validity, and it quantifies the congestion nonlinearity, a car at the 08:00 peak emits
about +43% more NO2 than at the 01:00 quiet hour (11.6 vs 8.1 g per vehicle) purely from
queueing, the interaction effect a static flow-times-a-factor surface cannot produce. The
check also surfaced capacity saturation (per-hour throughput flattens from about 6am at
the current 500 daily-average vehicles), a signal that the absolute demand magnitude
needs calibrating against ODOT AADT. NLCD land-use predictors and the Rao comparison are
still ahead (week 6).

Demand calibrated against ODOT AADT (Jun 26, src/calibrate_demand.py, read-only, AADT only
so the PBOT counts stay held out). Powell AADT 34,900 converts to ~727 veh/hr average-hour
directional and ~1,400-1,745 veh/hr peak-hour directional. At N_VEHICLES=500 the busiest
Powell segment carries 1,070 veh/hr, 1.47x over the average-hour target. The saturation is a
real STRUCTURAL ceiling, not a bad parameter: one following lane per directed segment under
the assumed 60 s / 50%-green signal caps each segment around 1,070 veh/hr, which sits below
Powell's real peak, so demand cannot be scaled up to reach the peak (that would need
multi-lane segments or higher signal capacity). Recommendation is N_VEHICLES = 240 (matches
AADT/24 directional); the exact value is interpolated and awaits one pinned-seed rerun to
confirm, held until after the Monday demo so its cited numbers do not shift. The lane-capacity
fork (lower demand vs model multiple lanes) is a Christof decision.

Traffic-layer validation against real data (Christof's Jun 25 ask): src/traffic_counts.py
pulls the PBOT Traffic Volume Counts and src/validate_traffic.py snaps ~2,221 count points
onto 247 model segments and computes a Spearman rank correlation of real ADT vs the model's
per-segment throughput (the apples-to-apples match for ADT). Two changes were tested this
session. (1) Routing vehicles by travel TIME instead of distance raised the correlation
from 0.26 to 0.38, a principled win (real drivers minimize time, which favors arterials);
it is kept. (2) Adding a population->jobs gravity demand model (src/landuse_data.py +
build_demand_weights) did NOT improve it (0.38 -> 0.345, and 0.328 with distance decay).
That is an honest negative result: this metric is dominated by network structure, which
uniform demand already captures via betweenness on the arterials. Gravity demand is kept on
by default (config.DEMAND_GRAVITY) because the closure and time-of-day experiments need
realistic destinations; its decay scale was set a priori (1.5 km), NOT tuned against the
held-out PBOT counts, so the test stays honest. CI (GitHub Actions) runs the scenario
test-bench on push.

Open simplifications: signal timing is an assumed uniform cycle, not real per-signal
plans (and confirmed Jun 26 that Powell's real plans are NOT gettable: it runs SCATS
adaptive control, so there is no fixed published cycle to calibrate against); demand now
has a real spatial pattern (population/jobs gravity) and a real time-of-day shape (the
`day` mode), but the gravity decay scale is an a-priori value not yet calibrated and trips
are not split into directional AM/PM commute flows; the live emission fleet is still a
single PC_D_EU4 (all-diesel) class. As of Jun 26 src/fleet.py provides a calibrated
mixed-fleet alternative (40 HBEFA3 classes + a sourced Multnomah County mix with a
PBOT-derived Powell heavy-vehicle share) and an offline preview on the existing NO2 surface
(no sim run, src/fleet_preview.py); it shows the all-diesel assumption overstates NOx by
roughly 2 to 4x (the network preview gives ~4x once the Powell truck share is calibrated to
real PBOT layer-253 class counts, which found Powell's "trucks" are ~99% two-axle light
commercial, not heavy diesel; the exact factor is sensitive to the heavy-diesel/bus share,
the key remaining knob), so the current NO2 surface is an honest upper bound. Whether to
switch the live sim to the mixed fleet is a Christof calibration decision. Calibration knobs flagged in config.py to
set with Christof: F_NO2, the fleet class, signal timing, and now the gravity decay scale.

Noise path (week 8): a FIRST version of the second output surface is now built (Jun 26,
src/noise.py + src/visualize_noise.py). It reads an existing run's saved per-segment results
(no simulation) and produces a per-segment dB(A) road-traffic noise surface with the EU
CNOSSOS method: rolling + propulsion sound power over 8 octave bands, A-weighted, then a
deliberately simple line-source geometric-divergence propagation to a 10 m receiver. It is
congestion-aware: realized speed is recovered as v_mean = length * throughput / value, so
jammed segments emit more. Result on powell_no2: dB(A) 26.5 / 39.6 / 59.4 (min/median/max),
loudest on Powell and Division, arterials brightest, dead streets silent. The category-1
coefficients, reference speed, band order, and A-weighting were verified element-by-element
against Directive (EU) 2015/996 Appendix F Table F-1, so they are publication-safe. Documented
v1 simplifications: cars only (no heavy vehicles), and propagation drops ground/barriers/
atmospherics/meteorology; those are exactly where the FHWA Traffic Noise Model (TNM) reference
comparison plugs in next. Two convenience edits are intentionally NOT yet applied (a `noise`
mode in visualize.py, a noise-knobs block in config.py); the scripts run standalone meanwhile.
Christof (Jun 23) could not find Powell-specific noise data
from the city, which confirms the model-to-model framing (no clean noise ground
truth) and Plan B. Two leads to chase for the noise comparison: the OSU / Multnomah
County Portland noise study (Bozigar and Mowrer, OSU College of Health; a citywide
10 m noise surface and a county interactive map are forthcoming) and a county
PowerBI noise dashboard.

SIGSPATIAL contribution, made undeniable (Jun 26): the headline is now a single figure
(src/static_vs_abm.py) showing the same closure two ways on one change scale, a static
land-use model blank (zero change on every segment) beside the ABM redistributing. It
rests on a strong, well-fit static baseline (src/landuse_model.py, out-of-bag R^2 0.51,
so it is not a strawman) and a short invariance proof (a static model's land-use inputs
do not change when a road closes, so its prediction cannot move). The closure result was
hardened: robustness across 6 seeds and generality across three arterials
(src/closure_sweep.py, src/closure_robustness.py) show closing an arterial reliably
strips 68 to 80% of its own NO2 and reroutes it onto the parallels; population exposure
(src/exposure.py) states it in human terms (~11,000 residents' modeled NO2 rises).
SIGSPATIAL_ABSTRACT_MATERIAL.md collects the 2-page abstract building blocks. The demo
deck is built (Powell_ABM_demo_v4.pptx, 13 slides). All of this needs nothing from Rao,
so the contribution is not blocked on the sampler data.

Next build step: rehearse the built demo (Powell_ABM_demo_v4.pptx, DEMO.md) and get
Christof's SIGSPATIAL go/no-go at Monday's meeting. Week-6 groundwork exists:
src/predictors.py builds Rao-style multi-buffer (100 to 1200 m) ABM traffic predictors
(config.BUFFER_RADII_M). UPDATE Jun 28-29: Rao's NO2 sampler data ARRIVED (she sent it
directly; banked at data/rao/no2_for_Darcy.xlsx, gitignored, never commit). It is 603
readings at 352 unique sites across the whole Portland metro (measured NO2, 4 rounds, 521
summer / 82 winter), so the long-standing "not public, must come from Rao" block is
resolved. The full comparison pipeline is now built and committed (src/rao_data.py loader,
a land-use site-feature builder, src/forest_compare.py: land-use vs ABM vs both forests with
Roberts spatial block cross-validation, reads saved surfaces, runs no sim). It is PARKED, not
yet run, for one reason: only 5 sites fall in the 1.5 km Powell window (too few to train and
test a forest), so running it for real means widening the study area (~67 sites at 5 km, ~158
at 8 km), which is a Powell-focus-vs-wider-network scope decision for Christof. Darcy emailed
him to decide whether the comparison is even worth pursuing; until he replies, do not widen
the network or run it. The closure result and the noise path remain the headline contributions
and need nothing from Rao. Alternatives still open: wire
the PORTAL+ODOT demand into generate.py, or grow the closure experiment into a planned
multi-scenario comparison once Christof weighs in.

## Tech stack

Python, OSMnx, NetworkX, NumPy, pandas, Matplotlib. Often run in Google Colab
with Drive mounted; config.py detects Colab and routes data to Drive.

## People

- Christof Teuscher: faculty mentor. Draws a hard line between research and
  engineering, asks what tools were used, pushes models toward interesting
  dynamics, wants plain-language explanations, frames work around the Heilmeier
  questions.
- Nik Anderson: grad-student mentor.
- Fatima Asghar: Christof's other student.

## Deliverables

Documented code and pipeline, street-segment maps of noise and NO2, the
model-versus-baseline comparison, a sole-author proceedings chapter, and the
August 14 symposium talk. Program policy: acknowledge AI assistance on
deliverables.
