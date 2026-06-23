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
literature range 0.20-0.30) retunes without rerunning. visualize.py renders both an
activity map and an NO2 map. Runtime stays fast and linear (~10 s for 500 vehicles
over a simulated hour). Vehicle count and network size are config parameters
(Christof's Jun 22 ask). Powell stays the proof-of-concept and Plan B. The Jun 23
key-paper talk on the Rao baseline is built and ready (on Drive, outside the repo).

Real public data is now partly pulled (DATASETS.md): a real PORTAL hourly
volume+speed profile (nearest open station to Powell) and the verified ODOT AADT
for Powell (34,900 in 2018 at SE 26th). src/demand_data.py turns the PORTAL sample
into 24 normalized hourly demand fractions, but it is not wired into the sim yet
(time-of-day spawning changes the experiment, and demand calibration is set with
Christof). NLCD land-use predictors and the Rao comparison are still ahead (week 6).

Open simplifications: signal timing is an assumed uniform cycle, not real per-signal
plans; demand is still uniform random trips (the real time-of-day profile is pulled
but not wired in); the emission fleet is a single PC_D_EU4 class. Calibration knobs
flagged in config.py to set with Christof: F_NO2, the fleet class, signal timing.

Noise path (week 8): Christof (Jun 23) could not find Powell-specific noise data
from the city, which confirms the model-to-model framing (no clean noise ground
truth) and Plan B. Two leads to chase for the noise comparison: the OSU / Multnomah
County Portland noise study (Bozigar and Mowrer, OSU College of Health; a citywide
10 m noise surface and a county interactive map are forthcoming) and a county
PowerBI noise dashboard.

Next build step: wire the PORTAL+ODOT demand into generate.py (the four-step plan is
in demand_data.py), or move to week-6 predictors + the Rao random-forest comparison.

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
