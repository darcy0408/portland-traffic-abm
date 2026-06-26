# SIGSPATIAL SRC: abstract building blocks

Working material for the 2-page extended abstract. This is a draft to move into the
writing project; it lives here next to the code so the numbers stay traceable to the
runs that produced them. No em dashes by request.

## The contribution, in one sentence

A source-based agent simulation produces a street-resolution NO2 exposure surface
that responds to changes in the road network (a closure), which a static land-use
regression structurally cannot do. The claim needs no external baseline data: the
closure result stands on its own.

## The headline figure

`outputs/demo/5_static_vs_abm_closure.png`: the same closure, the same color scale,
two methods side by side. The static land-use model is blank (zero change on every
segment); the agent model redistributes NO2 off the closed arterial onto the
parallels. A dead panel next to a vivid one.

## (#4) Why a static model cannot do this: a short proof

Plain version: when you close a road, the land use does not change. Population, jobs,
land cover, and the road GIS layers are all the same the day after as the day before,
and a static model is not rebuilt for a one-day event. A model that reads only those
unchanged inputs must return the same answer. So its predicted surface cannot move.

Formal version:

- A static land-use model predicts NO2 at a location as `f(x)`, where `x` is a fixed
  vector of land-use and built-environment predictors at that location (population,
  jobs, land cover, road-network descriptors) and `f` is any learned function.
- Premise 1: a temporary road closure (a marathon, a bridge or lane closure) changes
  no land-use predictor, and a static model is not refit for the event. So the input
  is unchanged: `x_closed = x_open` at every location.
- Conclusion: `f(x_closed) = f(x_open)` everywhere, so the predicted change is exactly
  zero. This holds for ANY `f`, so no static land-use model, however well tuned,
  including Rao's, can produce a nonzero closure response.

The agent model's predictors are the vehicle trajectories themselves, which DO change
when the network changes, so it can and does respond. That is the whole argument, and
it pre-empts the "is your static model a strawman" objection: even a perfectly tuned
static model gives zero, by the proof above. (We also show a well-fit static model
empirically, see #6.)

## (#5) Validation: two independent axes, not one number

The traffic layer is validated two ways, against two different real datasets, on two
different axes. Reporting both is stronger than leaning on the single moderate spatial
number.

- Spatial (does the model put traffic WHERE the city measures it?). Held-out PBOT and
  Multnomah County counts, n = 247 model segments. Spearman rho = 0.33, highly
  significant (p = 1.3e-7; bootstrap 95% CI [0.19, 0.44]). Held out means the gravity
  demand is built from Census population and LODES jobs and never sees these counts, so
  the test is honest. The value is moderate because the metric is dominated by network
  structure (betweenness on the arterials), which even uniform demand captures; we
  report 0.33 for the full model rather than switching to the config that happens to
  score highest, which is the honest read.

- Temporal (does the model reproduce the real daily RHYTHM?). Driven by the real PORTAL
  hourly profile, the realized per-hour throughput tracks the input demand shape at
  Spearman 0.88 (n = 24 hours), confirming face validity. This axis also surfaces a
  result a static flow-times-a-factor surface cannot produce: a car at the 08:00 peak
  emits +43% more NO2 than at the 01:00 quiet hour (11.6 vs 8.1 g per vehicle) purely
  from queueing, the congestion nonlinearity that is the reason to use an agent model.

Spatial placement (where) plus temporal dynamics (when): two independent validations.

## (#1, #2) Robustness and generality of the closure result

From `python src/closure_robustness.py`: 3 scenarios (close Powell, Division, Holgate
in turn) x 6 seeds. Each cell is mean % NO2 change across seeds (std).
Figure: `outputs/demo/7_closure_robustness.png`.

| closed \ NO2 on | SE Powell | SE Division | SE Holgate | network total |
|---|---|---|---|---|
| close Powell   | -80% (4)  | +93% (41)   | +50% (11)  | -2% (2) |
| close Division | +16% (22) | -68% (7)    | +5% (2)    | -2% (1) |
| close Holgate  | +34% (21) | -43% (4)    | -70% (2)   | +4% (1) |

Robustness (#1): the headline is the diagonal. Closing an arterial removes 68 to 80%
of its own NO2, and that drop is rock-stable across seeds (std of only 2 to 7 points).
The result is not seed noise. The redistribution magnitudes onto the parallels vary
more by seed (which detour dominates shifts run to run), but the direction is
consistent: the parallels go up.

Generality (#2): the pattern flips sensibly across all three scenarios. Close any one
arterial and its NO2 collapses while traffic reroutes onto the others. It is a method,
not a one-off. (One honest nuance: closing Holgate pulls some NO2 OFF Division, -43%,
because that traffic climbs to Powell, +34%, instead. The redistribution follows the
geometry, it is not a uniform "everything else goes up".)

Honesty note on the headline number: the deck and DEMO.md cite the closure under the
pinned default seed 42 (SE Division +132%, SE Powell -82%, SE Holgate +54%), which is
the reproducible run every map is rendered from. The 6-seed ensemble mean for Division
is +93% (std 41), so seed 42 sits near the top of the range. Recommended framing:
keep seed 42 as the cited representative run (it is the pinned, reproducible one), and
present the ensemble as the robustness check ("closing Powell removes 80% +/- 4% of its
NO2 and roughly doubles Division on average"). State both; do not silently lead with the
highest single number.

## (#3) Population exposure under the closure

From `python src/exposure.py` (19 block groups, 23,548 residents, 400 m local buffer).
For each block group we sum modeled NO2 over the street segments within 400 m of its
centroid, open vs closed.

- Population-weighted mean local exposure rises +9.2% (open 338 to closed 369, modeled
  units). Larger than the +2.1% network total, because the weighting emphasizes where
  residents actually are relative to where the detour traffic lands.
- 11,060 residents live where modeled NO2 RISES; 12,488 where it FALLS. The closure
  does not just change total pollution, it moves whose air it lands in.
- Sharpest increases are the block groups on the parallel detour routes north and east
  (two of them more than quadruple); sharpest drops are right at the closed Powell
  stretch (down 60 to 76%).

The "who cares" in one line: closing one block of one arterial shifts modeled NO2 onto
roughly eleven thousand residents' neighborhoods. Figure: `outputs/demo/6_exposure_change.png`.
Honest framing: this is modeled NO2 (HBEFA NOx times the literature primary-NO2
fraction), a relative open-vs-closed comparison, not measured air quality.

## (#6) A well-fit static model, so the baseline is not a strawman

From `src/landuse_model.py`. A richer Rao-style land-use random forest, 29 predictors:
population and jobs, major- and minor-road length, intersection density (all over Rao's
100 to 1200 m buffers), distance to the nearest major road, and three own-segment
built-environment terms (road class, length, is-major). Fit on log NO2 (the standard
land-use-regression convention for skewed pollution concentrations).

- Out-of-bag R^2 = 0.51 on the log scale, a genuinely good static baseline (the
  pop/jobs-only version scored -0.16). Top predictors: own road-class rank, population
  within 1200 m, own road length, minor-road length within 1200 m.
- Honest sub-result: on the RAW grams scale the static R^2 is only 0.03, because no
  static model can reproduce the extreme arterial peaks. That is itself part of the
  contrast: the agent model concentrates NO2 on exactly those peaks.
- This model is held FIXED across the closure (a static model is not refit for a
  one-day event), so it predicts exactly zero change. Now wired into the headline
  figure: the left panel is labeled "fits at R^2 = 0.51" and is still blank.

The payoff: the contrast is no longer "weak static model vs agent model." It is "a
GOOD static model, R^2 = 0.51, still completely blind to the closure," exactly as the
proof in #4 requires.

## What this is, honestly (for the abstract's limitations)

- Model-to-model comparison, not model-to-ground-truth: Portland lacks dense NO2 sensor
  data, so success is a rigorous method comparison, framed as a feature not hidden.
- The novelty is the framing and the closure demonstration, not new algorithms (the
  car-following, emission factors, and network are established tools).
- Single emission class, assumed uniform signal timing, a-priori gravity decay scale:
  the calibration knobs flagged in config.py to set with the mentor.
