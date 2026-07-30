# The virtual-lane capacity experiment (worktree only)

**Date:** Jul 10, 2026. **Branch:** `worktree-lanes-experiment`. **Status:** complete,
worktree-only. Nothing here merges to `main` unless Christof calls for it; the
committed project spec stays the single-lane model. Built to answer, with evidence,
the question Nik (Jul 8 email) and Christof (Jul 8 meeting) both asked: why validate
on rank instead of absolute counts, and does the single-lane capacity ceiling matter?

## What was built

`config.LANES_ENABLED` (off by default) gives each segment its real OSM-tagged lane
count as VIRTUAL lanes: a car follows the car N positions ahead in its segment's
queue, so N cars move abreast and signal discharge scales with N. No lane-change or
merge behavior; lane use is perfect and frictionless, so the capacity gain is an
upper bound. Parsing rules (all a priori from map data, in `_parse_lanes`): list
tags take the minimum (bottleneck rule), two-way streets halve the OSM both-direction
total, untagged edges default to 1, clamp to [1, LANES_MAX=3]. On the Powell network,
209 of 2,838 segments get more than one lane, and the list reads like the real
arterials: Powell, Cesar Chavez, Holgate, McLoughlin, the 11th/12th couplet.
Division stays mostly single (its road diet is real).

## Verification before any result was read

- `src/lanes_scenarios.py` (hand-checkable, same discipline as scenarios.py):
  - EQUIVALENCE: with all lane counts 1, trajectories are bitwise identical to the
    base kernel.
  - DISCHARGE: 40 cars queued at a red; one 30 s green passes 11 cars single-lane
    vs 22 with two lanes (exactly 2.00x), nobody runs the red, and the front two
    cars queue abreast at the stop line under red.
- Full-model regression: rerunning the committed config (flag off, seed 42)
  reproduces `powell_through_segments.parquet` bit-for-bit, all 2,838 segments.
- The original 4/4 scenario test-bench still passes.

## Results (seed 42, same demand model as every cited number)

| run                | N    | lanes | Powell max veh/hr | rank rho (throughput) |
|--------------------|------|-------|-------------------|-----------------------|
| powell_through     | 500  | off   |   987             | 0.590                 |
| powell_lanes       | 500  | on    | 1,060             | 0.591                 |
| powell_n1200_1lane | 1200 | off   | 1,106             | 0.580                 |
| powell_n1200_lanes | 1200 | on    | 1,388             | 0.579                 |

Real Powell targets from ODOT AADT 34,900 (calibrate_demand.py): ~727 veh/hr
average-hour directional, ~1,400-1,745 veh/hr peak-hour directional.

Three findings:

1. **The single-lane ceiling is real.** Demand rising 2.4x (N=500 to 1200) moves
   Powell's busiest segment only 987 to 1,106 veh/hr: saturated, right at the
   ~1,070 structural cap predicted by calibrate_demand.py, and below Powell's real
   peak. No amount of demand can push the single-lane model to the real peak.
2. **Real lane counts lift the ceiling into the real range.** Same demand, lanes
   on: 1,388 veh/hr, through the old cap and reaching the bottom of Powell's real
   peak-hour range. Network throughput rises 20% at N=1200. (Per-vehicle NOx falls
   slightly, about 2-3%, because less queueing means less idling: the same
   congestion interaction the ABM exists to capture.)
3. **The ranking does not care.** Across a 2.4x demand range and a structural
   capacity change, the rank correlation stays 0.579-0.591, and turning lanes on
   changes it by at most 0.001. The rank validation was never hiding a capacity
   problem, and the capacity ceiling was never the reason the rank agreement is
   what it is (that lever is demand structure, per McDonald 2026).

## What this means for the rank-vs-absolute question

Matching absolute counts requires (a) calibrating the demand dial (N_VEHICLES) and
(b) removing the capacity cap: (b) is now demonstrated feasible with a priori map
data, and neither (a) nor (b) changes where the model puts traffic (the ranking).
So rank agreement and absolute-scale matching are separable problems: rank measures
the traffic pattern, absolute scale measures calibration of knobs. The closure
result depends on the pattern. This is the evidence-based version of the answer
sent to Nik on Jul 10, ready for the Jul 19 conversation with Christof.

## Files

- `config.py`: LANES_ENABLED / LANES_MAX block (off by default).
- `src/generate.py`: `_parse_lanes`, `n_lanes` in prepare_network, and the
  three-rule generalization in step_vehicles (leader N-ahead, spillback
  Nth-rearmost, entrance-hold Nth-rearmost). Flag off is provably the base model.
- `src/lanes_scenarios.py`: the hand-checkable evidence.
- Runs live only in this worktree's `data/processed/` (gitignored as always):
  powell_lanes, powell_n1200_1lane, powell_n1200_lanes, powell_lanes_offcheck.
