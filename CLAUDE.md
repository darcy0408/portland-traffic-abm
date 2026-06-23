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

Week 3 (started Mon Jun 22), and ahead of schedule. The core ABM now runs end to
end on the cached Powell network (978 nodes, 2,838 edges): vehicles get random
origin/destination routes and drive segment by segment using the IDM kernel,
following the car ahead. Week-4 work is already done too: 21 real OSM-tagged
signalized intersections run a two-phase cycle, cars queue at red lights, and
congestion emerges (mean speed drops and queues stack up), which is the
interaction-driven behavior that justifies the ABM. Runtime scales linearly with
vehicle count and is fast (~6-9 s for 500 vehicles over a simulated hour), so
full-city is plausible; Powell stays the proof-of-concept and Plan B. Vehicle count
and network size are config parameters (Christof's Jun 22 ask to make it scalable).
A heat-map visualization is in visualize.py. Public-data sources are scouted in
DATASETS.md (PORTAL and ODOT for volumes, NLCD for land-use predictors,
SUMO-HBEFA3 for emissions, PBOT for signals); nothing is downloaded yet, synthetic
demand is fine for now. The Jun 23 key-paper talk on the Rao baseline is built and
ready (lives on Drive, outside the repo).

Open simplifications: queues do not yet spill back across intersections; signal
timing is an assumed uniform cycle; demand is random trips, not real counts; and
per-segment totals are vehicle-seconds, the placeholder where per-vehicle NO2
(HBEFA) plugs in. Next build step is the week-5 NO2 path: per-vehicle emissions via
SUMO-HBEFA3 NOx(v,a) accumulated per segment, feeding toward the Rao comparison.

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
