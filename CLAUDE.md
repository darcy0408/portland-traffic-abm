# Portland Traffic ABM

## What this project is

An agent-based model (ABM) of interacting vehicles on Portland's OSMnx street
network. Vehicles follow one another, queue at signals, and back up in
congestion. From those interactions the model produces street-segment surfaces
of traffic NO2 and noise. The contribution is that the agent simulation
generates the predictors, which are then fed into the same statistical method a
published baseline used, so the comparison isolates what source-based
interaction modeling adds over static estimation.

Built as an NSF REU project at Portland State University.

## The spec (do not drift from this)

- The method is an ABM with vehicles on an OSMnx network. It is not a
  statistics-first or ML-first project. The vehicle interactions (car-following,
  signal queueing, congestion) are what justify using an ABM at all.
- Outputs are two surfaces, NO2 and noise, at street-segment resolution.
- NO2 path: the agent simulation produces predictors that are fed into a random
  forest, the same method the land-use baseline used, and compared against that
  land-use-fed random forest. Per-vehicle NO2 emissions use HBEFA factors.
- Noise path: modeled mechanistically with CNOSSOS and compared against the FHWA
  Traffic Noise Model reference.
- The comparison is model-to-model, not model-to-ground-truth. Portland lacks
  dense sensor data, so success is a rigorous comparison between methods, not a
  claim of absolute accuracy. This is framed honestly as a feature, not hidden.
- Success is defined by doing the comparison rigorously, regardless of which
  method wins. The research question is falsifiable: the agent-fed forest may
  not beat the baseline, and that is still a valid result.
- Build order: the core vehicle model comes first. Car-following before anything
  else.

## Out of scope (removed or deferred, do not add back)

- No pollen layer. It was removed from the project entirely.
- No sensor ground-truth validation as the spine. The project compares models,
  not measurements.
- No routing or "best route given exposure" feature as the core. Routing under
  constraints is a solved engineering problem and is not the research.
- No reservoir computing or ML-regression layer in the current scope.
- Heat and pollen reference layers are out. Noise and NO2 only.

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
  cited. An unpinned seed makes each run produce different numbers, so a cited
  figure can never be reproduced. If two runs of the same experiment disagree,
  suspect the seed first.
- One simulation runs at a time. Never start a second generate.py run that writes
  the same data files while another is still running. Two programs writing the
  same file at once can corrupt it, with no warning.
- Figure, demo, and report work reads the existing data files. It never re-runs
  the simulation to make a picture. This is the single-source-of-truth rule:
  compute the numbers once, then have every figure and document copy from that
  one result instead of recomputing.
- Do not commit generated data or figures. data/ and outputs/ are gitignored.
- Cache the OSMnx graph once and reuse it, since downloads are slow.
- Add comments as code is written, not in a later cleanup pass.

## Tech stack

Python, OSMnx, NetworkX, NumPy, pandas, Matplotlib. Often run in Google Colab
with Drive mounted; config.py detects Colab and routes data to Drive.
