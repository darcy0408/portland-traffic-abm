# Pre-registration: the Rose Quarter I-5 SB closure (Sept 11 2026)

Timestamped by this file's first commit to the public repository, before any
campaign task runs. Author: Darcy Van Pelt. Advisor: Christof Teuscher (PSU).

ODOT's Rose Quarter project (no. 19071, i5rosequarter.org) closes I-5
SOUTHBOUND completely, 24/7, for up to 5 weeks starting Sept 11 2026, between
the I-405 and I-84 interchanges, with a signed detour to I-405 SB and regional
traffic directed to I-205. This is a real network-edge-removal event of
exactly the kind this project's closure experiments simulate, and public loop
detectors (PORTAL) will record what real traffic does. This document freezes
the model scenario, metrics, verdict rules, and validation protocol BEFORE
the campaign runs and before the real closure begins, so the model's
predictions are provably predictions.

## 1. The model scenario (frozen)

- Closure spec: `SCENARIOS["rosequarter"]` in `src/freeway_runs.py`
  (ref "I 5", center 45.5355 -122.6690, radius 800 m, close_ramps,
  direction "S"). The directional selector removes only the southbound
  carriageway; northbound stays open.
- Frozen span, verified on the metro graph before this registration:
  exactly 5 edges, the 3 SB mainline edges
  (40382443, 40397036, 0), (40397036, 40413533, 0), (40413533, 3427976322, 0)
  (1,628 m, the I-405 to I-84 stretch) plus the 2 ramp edges stranded
  interior to them. Every campaign task re-verifies this span against the
  graph it loads and refuses to run on any mismatch
  (`src/freeway_rosequarter.py`).
- Arms: open vs rosequarter-closed, same demand, paired by seed.
- Campaign: `src/freeway_rosequarter.py`, prefix fwrq. 8 pinned seeds
  (42, 7, 13, 99, 314, 777, 2024, 8; the project's standing block-1 set),
  2 arms, 16 tasks. Base model stack (the same configuration as the
  project's prior freeway campaigns, for comparability), mixed fleet for
  absolute grams. Tracked routes: I 5, I 405, I 205, OR 213, OR 99E, US 26.
- Known model limits, stated up front: a single steady-state simulated hour
  vs a 24/7 five-week closure; the real one local-access lane to
  Broadway/Weidler is not modeled (the span closes fully); the modeled
  stranded-ramp set approximates ODOT's announced ramp closures; demand is
  LODES 2021 commuting plus a fixed 15% through share, so it has no
  non-work trips, no demand evaporation, no time-shift, no mode shift;
  vehicles route once at spawn at free-flow times and never replan.

## 2. Trip-level diversion metrics (frozen)

- AFFECTED trip: a trip whose OPEN-arm planned route includes at least one
  edge of the frozen span above.
- PAIRING rule: the open-arm spawn population is drawn once per seed, and
  the SAME origin-destination pairs are routed on the closed graph. ODs
  with no path on the closed graph are dropped and their count reported
  (expected 0: the SB detour path exists, verified).
- D1: share of affected trips whose planned route includes any mainline
  edge of a named detour freeway (I-405; separately I-205), open vs
  closed, per seed, paired.
- D2: share of affected trips that INCREASE their mainline distance on
  that detour freeway under the closure.
- D3: added mainline vehicle-km per seed on each detour freeway (paired,
  same OD population).
- Secondary: per-route corridor NOx/throughput totals from the campaign
  summaries (the standing readout). Corridor totals are secondary because
  a prior analysis showed they cannot certify a small diversion against
  seed noise at feasible replication.

## 3. Verdict rules (frozen)

8 paired seeds; a directional claim is SUPPORTED only with unanimous sign
across seeds AND |t| > 3 on the paired relative differences (the project's
standing campaign bar). Trip-level shares are reported as mean and standard
deviation. No parameter is tuned after seeing results. A null result is
reported as a null result.

## 4. Predictions

Direction of change, banked now: the closed I-5 SB span goes to zero in the
model (removed); I-405 SB mainline totals go UP; I-205 totals go UP. The
rank order of relative gains across detour corridors and the numeric D1-D3
values will be computed from the campaign and appended to this file BEFORE
Sept 11 2026, dated, without changing anything above.

## 5. Validation against reality (PORTAL, protocol frozen)

PORTAL archives ODOT hourly loop-detector volumes on I-5, I-405, and I-205.
Rules set a priori:

1. Compare direction of change per corridor, before vs during closure.
2. Compare the RANK of relative gains across detour corridors.
3. Never compare absolute volumes: model demand is fixed and cannot
   evaporate, shift in time, or change mode the way five weeks of real
   drivers will. Prefer the closure's first days, before adaptation
   accumulates.
4. Each station is compared against ITSELF (before vs during), never
   cross-station, because detector lane coverage differs by station.

Frozen mainline station set (verified reporting on live data Aug 13 2026;
mainline "2DS" stations only, ramp-meter stations excluded because their
lane semantics are unreliable):

- In-span I-5 SB (prediction: down to about the local-access residual):
  3121 (Broadway), 10642 (Russell).
- Upstream I-5 SB approach: 3172 (I-405 split), 10640 (Alberta).
- Downstream I-5 SB, south of the I-84 merge: 3120 (N. Morrison Br),
  3185 (Madison).
- I-405 SB, the signed detour (prediction: up): 3122 (the SB I-5 to SB
  I-405 transfer movement itself), 3196 (Broadway), 3110 (Jefferson).
- I-205 SB north end, the regional detour (prediction: up): 10579
  (Government Island), 3107 (Prescott), 10582 (Maywood Park), 3105 (Halsey).

If a frozen station stops reporting before Sept 11 it is dropped by
re-running the coverage check on a pre-closure baseline day, before any
during-closure data is seen. Baseline days: same weekday, pre-Sept-11,
avoiding Labor Day week.

## 6. Model-variant clause

A demand-realism variant of the model (adding non-work trips such as
shopping and errands from public data) is under construction. If it is
ready before Sept 11, its predictions will be added as a separately labeled
pre-registered arm in a dated appendix to this file BEFORE the closure
begins. The primary registered predictions are the base-model campaign
above, and they do not change.

## Appendix A (2026-08-14): the numeric predictions, computed and banked

Nothing above this appendix changes. This fulfills section 4's promise: the
campaign has run (SLURM array 126285, 16/16 tasks, Aug 13 2026) and the
trip-level instrument defined in section 2 has run (src/rosequarter_d123.py,
Aug 14 2026, routing analysis only, no simulation). These are the model's
numeric predictions for the Sept 11 closure, banked before it begins.

### A.1 Corridor route totals (campaign, paired per-seed, closed minus open)

Frozen verdict bar: unanimous sign across the 8 paired seeds AND |t| > 3 on
the paired relative differences. Values are per-route NOx totals, percent.

| route | mean % | sd | range | signs | verdict |
|-------|--------|----|-------|-------|---------|
| I 405 (signed detour) | +84.9 | 16.7 | +55.6 to +108.3 | 8/8 | SUPPORTED, t=14.4 |
| I 205 (regional detour) | +3.1 | 8.1 | -4.1 to +17.7 | 4/8 | not supported, t=1.1 |
| I 5 (route total, both directions) | -0.8 | 2.0 | -5.0 to +1.8 | 3/8 | not supported, t=1.1 |
| OR 213 | +2.9 | 10.9 | -10.4 to +26.9 | 5/8 | not supported, t=0.8 |
| US 26 | -0.6 | 3.6 | -6.0 to +3.9 | 4/8 | not supported, t=0.4 |

Absolute companions, because these percentages sit on very different bases
and are never to be cited alone: I-405 gains +813 +/- 159 g NOx per
simulated hour on an open-arm base of 959 g; I-205 gains +450 +/- 1,249 g
on a base of 16,333 g. The I-405 percentage is large because its base is
small; the closed span's own volume goes to zero by construction.

Predicted rank order of relative gains across detour corridors, for the
frozen PORTAL comparison (section 5, rule 2): I-405 first, I-205 second and
weak, surface alternates indistinguishable from seed noise. Predicted
directions per frozen station group (section 5): in-span I-5 SB down to the
local-access residual, upstream I-5 SB down, I-405 SB up, I-205 SB up
weakly.

### A.2 Trip-level D1-D3 (instrument, 8 seeds, mean +/- sd)

Affected trips (open-arm planned route touches the frozen span): 575 to 667
per seed, 4,962 total, 3.8% of the 16,500 spawned per seed.

| metric | I 405 | I 205 |
|--------|-------|-------|
| D1 share of affected trips on detour mainline, open | 0.164 +/- 0.020 | 0.075 +/- 0.008 |
| D1 same share, closed | 0.584 +/- 0.017 | 0.101 +/- 0.009 |
| D2 share increasing detour mainline distance | 0.489 +/- 0.021 | 0.058 +/- 0.007 |
| D3 added detour mainline veh-km per seed | +1,187 +/- 117 | +132 +/- 56 |

The D1 movement (closed above open) and D3 sign are positive in every seed
on both detours, and the trip-level rank order matches A.1 in every seed:
the smallest I-405 D3 (+1,010 veh-km) exceeds the largest I-205 D3 (+223).
Affected trips lengthen by 0.9 min free-flow travel time on average.

Dropped ODs: 55 of 4,962 affected trips (1.1%), where section 2 expected 0.
All 55 share one mechanism, found on inspection: the trip's endpoint is on
the closed roadway itself, either on a span node (47 trips) or on the short
SB mainline stretch immediately downstream of the closure that the closure
leaves with no feeding edge before the next merge (8 trips, all one node).
Such endpoints have no closed-graph path by construction. The frozen rule
(drop and report the count) is applied unchanged; no rule or parameter was
altered after seeing results.

### A.3 Model-variant clause status

As of this appendix the non-work demand variant (section 6) is built and
gated off, and has NOT been evaluated against held-out counts; it has
therefore earned no second pre-registered arm. If it earns one before
Sept 11 it will be added as its own dated appendix below this one.

### A.4 Provenance

Instrument: src/rosequarter_d123.py in this repository. Population
identity with the campaign is checked, not assumed: the instrument runs on
the campaign's own graph file (md5 6707ddf25d63f2b5b4d2948b37cdb783), and
refuses to run unless the demand context it builds matches the campaign
log's fingerprint (215,655 placeable OD pairs, 531,245 commuters, 20,857
boundary entry nodes; SLURM log fwrq_126285_7.out). Per-seed outputs
(rqd123_s{seed}.json, rqd123_affected_s{seed}.parquet) are data files,
banked with the campaign summaries, not committed.

## Appendix B (2026-08-14): two additional arms, registered before their campaigns run

Nothing above changes. Appendix A's base-model predictions remain the
primary registration. The two arms below are registered BEFORE any of
their tasks run; their numeric results will be appended in a dated
appendix, before Sept 11, whatever they show. Further dated appendices
(noise-change predictions computed from the Appendix A campaign, and a
protocol for a measured-NO2 monitor comparison if a suitably placed
regulatory monitor exists) may follow before Sept 11 under the same rule:
registered or computed before the closure, nothing above ever edited.

### B.1 Realism-stack robustness arm (prefix fwrqr)

- Same frozen scenario, span, seeds, pairing, routes, and verdict bar as
  sections 1-3. Model variant: the project's realism stack (MOBIL lane
  changing, per-vehicle driver heterogeneity, Webster signal timing,
  green-wave coordination), mixed fleet. Runner already committed:
  `python src/freeway_rosequarter.py --realism`, 16 tasks.
- Purpose: does Appendix A's supported I-405 corridor result survive the
  realism dynamics.
- Stated now, before running: vehicles route once at spawn at free-flow
  times in every model variant, so the trip populations and planned
  routes, and therefore D1-D3, are identical to the base arm by
  construction. This arm tests realized flow and emission totals only.
- Prediction: I-405 NOx up, the closed span down; rank of relative gains
  I-405 above I-205.

### B.2 Peak and quiet time-of-day arm (prefix rqpq)

- Script src/rosequarter_peak_quiet.py in this repository. 2 demand
  levels x 2 arms (open, closed) x the standing 8 block-1 seeds = 32
  tasks. BASE stack and mixed fleet, identical to the Appendix A
  campaign, so the demand level is the only new variable. The frozen-span
  guard runs in every closed task.
- Levels: hour 8 (peak) and hour 1 (quiet), the same two hours the
  project's day experiment fixed long before this registration; demand is
  round(16,500 x profile[hour] x 24) with the PORTAL-derived hourly
  profile that day experiment already uses.
- Metrics and verdict: the same paired per-seed route-total rules as
  section 3, applied per level. Citation rule, frozen now: quiet-hour
  route bases are small, so absolute grams lead and a percentage is never
  cited alone.
- PORTAL comparison addition (extends section 5 without changing it):
  the peak/quiet predictions are compared against PORTAL by hour band
  (peak morning hours vs overnight hours), each station against itself,
  direction and rank only, same as rules 1-4.
- Predictions, banked now: I-405 goes UP at both levels; the rank of
  relative gains is I-405 above I-205 at both levels; the ABSOLUTE added
  I-405 NOx (grams) is larger at peak than at quiet. Whether the added
  grams are SUPER-proportional to the peak/quiet demand ratio (congestion
  amplification) is the registered open question; either answer is
  reported.

## Appendix C (2026-08-14): measured-NO2 monitor protocol and predictions

Nothing above changes. The Portland metro has exactly two regulatory NO2
monitors (Oregon DEQ, 2023 Annual Ambient Criteria Pollutant Air
Monitoring Network Plan, Table 2 and Appendix C):

- SE Lafayette NCore station, AQS 41-051-0080, 5824 SE Lafayette St,
  Portland (45.4966, -122.6029), hourly NO2 since 1984, urban scale,
  80 m from its nearest major road (SE Powell Blvd).
- Portland Near Roadway station, AQS 41-067-0005, 6745 SW Bradbury Ct,
  Tualatin, 27 m from I-5 at milepost 290.14, hourly NO2 since 2015,
  microscale, purpose "Source (Freeway)". (The DEQ table prints latitude
  45.8992, which contradicts the site's own address, county, and
  milepost; the address places it near 45.384, -122.747.) Milepost
  290.14 is NORTH of the I-205 rejoin (exit 288) and SOUTH of the I-405
  rejoin, so traffic passing this monitor keeps the I-405-detoured
  through trips and loses only the I-205-diverted share.

Protocol, frozen before the closure: hourly NO2 from the public DEQ/EPA
records for both monitors; each monitor compared against ITSELF, before
vs during the closure; direction of change only; the closure's first days
preferred, before adaptation accumulates; baseline days are the same
weekday before Sept 11, avoiding Labor Day week (the section 5 rules,
applied to monitors). Absolute concentrations are never compared to the
model: the model produces per-segment NOx mass, and chemistry, background,
and meteorology sit between that and an ambient ppb reading. If the
second near-road site DEQ has planned for the CBSA becomes active before
Sept 11, it is added under these same rules before any during-closure
data is seen.

Model predictions at the monitors, computed from the Appendix A
campaign's saved per-segment results (src/rosequarter_monitors.py; edges
within an a-priori 500 m radius of each site; 8 paired seeds; output
banked as rosequarter_monitors.json):

- Near Roadway (Tualatin): the SB I-5 carriageway past the monitor loses
  -2.6% of its throughput (sd 1.0), negative in 8 of 8 seeds, t = 7.1;
  all traffic within 500 m: -1.0% (sd 0.4), negative in 8 of 8, t = 7.6.
  The modeled NOx change at this site is not distinguishable from seed
  noise. Prediction, direction only: a SMALL decrease in traffic-driven
  NO2, plausibly below meteorological variance; no large change. A LARGE
  observed drop would indicate real-driver adaptation (canceled, shifted,
  or re-moded trips) that the fixed-demand model explicitly excludes, and
  would be reported as a limitation confirmed, not explained away.
- SE Lafayette: no detectable change predicted. Local NOx within 500 m
  moves -1.2% (sd 27), signs 4 of 8; local traffic -0.3% (sd 0.3), 7 of
  8 seeds negative but not unanimous. Consistent with Appendix A's null
  on the US 26 route total.

Stated plainly: neither monitor sits where the model predicts its largest
signal (the I-405 SB detour through downtown has no NO2 monitor), so the
monitor comparison tests the model's null and small-decrease predictions,
not the headline diversion. The PORTAL traffic comparison (section 5)
remains the primary scoring; this appendix adds measured pollution as a
secondary, direction-only check.

## Appendix D (2026-08-14): noise-change predictions (CNOSSOS v1)

Nothing above changes. This appendix banks the closure's predicted effect
on the project's second output surface, road-traffic noise, computed from
the same Appendix A campaign runs (src/rosequarter_noise.py, reading the
saved per-segment results; no simulation). The noise model is the
project's verified CNOSSOS v1 (Directive (EU) 2015/996 category-1
coefficients, verified element-by-element; congestion-aware speeds
recovered per segment; geometric divergence to a 10 m receiver). The
corridor metric is the length-weighted acoustic energy total over the
corridor's mainline segments, paired closed minus open per seed, in dB.

| corridor | mean dB | sd | signs | note |
|----------|---------|----|-------|------|
| I-405 | -0.39 | 0.13 | 8/8 down | quieter DESPITE more traffic |
| I-205 | -0.04 | 0.02 | 8/8 down | negligible |
| I-5 (whole route) | -0.41 | 0.03 | 8/8 down | span removed + upstream slowing |
| closed SB span | to silence | | 8/8 | the SB source vanishes; NB unchanged |

The I-405 row is the registered headline: the SAME closure that raises
modeled I-405 NOx by 84.9% (Appendix A) LOWERS modeled I-405 noise by
0.4 dB. Mechanism, stated before any data: the diverted traffic adds
vehicles to I-405 but slows them, and CNOSSOS rolling noise falls
steeply with speed at freeway speeds, so the per-vehicle quieting
outweighs the added vehicle density. The two exposure surfaces this
project produces move in OPPOSITE directions on the same corridor under
the same intervention.

Honest bounds on this prediction:

1. All corridor-level changes are far below the roughly 3 dB difference
   people reliably notice; no one standing beside I-405 would hear this.
   The one humanly perceptible change is at the closed span itself,
   where the southbound source vanishes entirely.
2. The prediction is CONDITIONAL on the v1 cars-only source model.
   Heavy vehicles (CNOSSOS categories 2 and 3) are propulsion-dominated
   with a weaker speed dependence, so a mixed-category model could
   attenuate or even reverse the I-405 sign. If the category upgrade is
   completed before Sept 11, its numbers are added as a separately dated
   appendix; this one does not change.
3. The v1 jammed-segment speed treatment deviates from textbook CNOSSOS
   deliberately (documented in src/noise.py).
4. No noise measurement network exists along these corridors, so unlike
   the PORTAL and monitor comparisons this prediction has no scheduled
   grader during the closure. It is banked for the record, dated, so a
   future comparison (a field measurement, or another group's surface)
   meets a prediction that provably predates the closure.

## Appendix E (2026-08-14): the non-work demand arm, registered before it runs

This is the arm section 6 reserved. The demand-realism variant is ready:
the non-work (shopping/errand) trip layer is committed
(config.DEMAND_NONWORK_ENABLED; 38.6% of internal trips draw destinations
from retail/service employment under a 5.9 km decay, both constants a
priori from the 2022 NHTS, nothing tuned to counts), and it has now
passed its evaluation against the held-out PBOT counts. Evaluation
result, stated before this arm runs: one flagged-on metro run (seed 42,
identical configuration to the flag-off baseline in every other respect)
scores Spearman rho 0.636 against the counts where the baseline scores
0.614, and puts model traffic on 273 of the 372 counted street segments
where the baseline covers 248. One seed, a modest gain, reported as
such; the direction is right and the mechanism (commute-only demand
leaves retail streets empty) is exactly what the layer was built to fix.

- Arm: prefix fwrqn, `python src/freeway_rosequarter.py --nonwork`.
  Identical to the Appendix A campaign (same frozen span, guard, seeds,
  arms, routes, verdict bar, base stack, mixed fleet) except
  DEMAND_NONWORK_ENABLED is True in every task. 16 tasks.
- Predictions, banked now: same directions as Appendix A (the closed
  span down, I-405 up, I-205 up weakly, rank I-405 above I-205). The
  registered open question: whether adding non-commute trips CHANGES the
  diversion shares (shoppers make shorter, more local trips, so the
  affected population may lean more heavily commuter than the network
  average); whatever it shows is reported.
- The primary registered predictions remain Appendix A's and do not
  change. This arm's numeric results will be appended, dated, before
  Sept 11.

## Appendix F (2026-08-14): results of the three registered arms

Nothing above changes. All three arms registered in Appendices B and E
ran to completion the same day they were registered (SLURM arrays 126757,
126758, 126805; 64 of 64 tasks COMPLETED; readouts by the committed
scripts). Registration provably preceded every run.

### F.1 Realism-stack arm (fwrqr, registered in B.1)

| route | mean % | sd | signs | verdict |
|-------|--------|----|-------|---------|
| I-405 | +35.6 | 10.9 | 8/8 | SUPPORTED, t = 9.3 |
| I-205 | +2.3 | 6.0 | 5/8 | not supported, t = 1.1 |
| I-5 (route total) | -2.6 | 3.6 | 1/8 | not supported, t = 2.0 |
| OR-213 | +0.8 | 11.6 | 2/8 | not supported, t = 0.2 |
| US-26 | -3.9 | 3.5 | 0/8 | clears the bar, see note |

The registered predictions hold: I-405 up (at reduced magnitude, +35.6%
under realism dynamics vs +84.9% in the base arm), rank I-405 above
I-205. The US-26 row clears the numeric bar (unanimous down, t = 3.2)
but was NOT a registered prediction; it is reported as an exploratory
finding only and claims nothing.

### F.2 Peak and quiet arm (rqpq, registered in B.2)

Peak (hour 8, demand 28,595): I-405 +730 g NOx, +59.4% (sd 13.8), 8/8,
t = 12.1, SUPPORTED. No other route reaches the bar.

Quiet (hour 1, demand 1,780): I-405 +51 g NOx, +21.9% (sd 17.2), 8/8,
t = 3.6, SUPPORTED (grams lead per the frozen citation rule; the
percentage sits on a small base). No other route reaches the bar.

Registered predictions hold at BOTH levels: I-405 up, rank I-405 above
I-205. The registered open question is answered: the added I-405 grams
ratio peak/quiet is 14.4 against a demand ratio of 16.1, so the absolute
diversion is NOT super-proportional to demand; it scales slightly under
it. The RELATIVE concentration of diversion is higher at peak (+59.4%
vs +21.9%), but the congestion-amplification hypothesis in absolute
grams is not supported, and is reported as such.

### F.3 Non-work demand arm (fwrqn, registered in E)

| route | mean % | sd | signs | verdict |
|-------|--------|----|-------|---------|
| I-405 | +75.8 | 19.1 | 8/8 | SUPPORTED, t = 11.2 |
| I-205 | -4.2 | 3.3 | 1/8 | not supported, t = 3.6 |
| I-5 (route total) | -3.1 | 2.6 | 1/8 | not supported, t = 3.4 |
| OR-213 | -5.8 | 5.8 | 2/8 | not supported, t = 2.8 |
| US-26 | +6.0 | 8.9 | 5/8 | not supported, t = 1.9 |

The registered predictions hold: I-405 up, rank I-405 above I-205. The
registered open question (does adding non-commute trips change the
diversion): at corridor level the story is unchanged and modestly
attenuated (+75.8% vs the base arm's +84.9%); the weak I-205 mean flips
sign and remains unresolvable, consistent with the dilution result that
motivated the trip-level metrics.

### F.4 Summary

The headline registered prediction, I-405 absorbs the diversion and its
relative gain outranks I-205, is SUPPORTED in the base arm, the realism
arm, the non-work arm, and at both the peak and quiet demand levels:
five of five tests, every one registered before it ran. The
corridor-level I-205 signal reached the bar in none of them, which is
why the pre-registered trip-level D1-D3 metrics (Appendix A) carry that
part of the prediction.

## Appendix G (2026-08-15): trip-level D1-D3 for the non-work arm, registered before it runs

Nothing above changes. Appendix E registered the non-work arm (fwrqn) at
the corridor level only, and Appendix F reported those results: I-405
+75.8% SUPPORTED, the I-205 corridor mean unresolvable. Appendix E's
registered open question, whether adding non-commute trips changes the
diversion shares, is a trip-level question, and section 2's D1-D3 are the
instrument built for exactly that case. This appendix registers that
application, with its predictions, before any of it runs.

Why this arm needs D1-D3 recomputed when B.1 said the realism arm did
not: vehicles route once at spawn at free-flow times in every model
variant, so a variant that changes only DYNAMICS leaves the trip
population and its planned routes identical, and D1-D3 are inherited.
fwrqn changes DEMAND. 38.6% of internal trips draw destinations from
retail/service employment under a 5.9 km decay instead of the commute
distribution, so the drawn population and its routes genuinely differ and
the metrics must be recomputed rather than carried over.

- Instrument: `src/rosequarter_d123.py`, metric definitions unchanged,
  run in a new `--nonwork` mode. The mode flips the config guard to
  DEMAND_NONWORK_ENABLED = True and adds the fwrqn campaign's own
  non-work fingerprint (1,003 block groups, 161,304 retail/service jobs,
  share 0.386, decay 5,900 m; campaign log, job 126805) to the existing
  LODES identity guard, which the campaign log shows the layer leaves
  unchanged (215,655 placeable pairs, 531,245 commuters, 20,857 boundary
  nodes). Same 8 block-1 seeds, same frozen 5-edge span, same graph
  (md5 6707ddf25d63f2b5b4d2948b37cdb783). Outputs take a separate
  `rqd123n_` prefix so the base arm's files cannot be overwritten.
- Verdict bar: section 3 unchanged. Unanimous sign across the 8 paired
  seeds AND |t| > 3.

Predictions, banked now:

- G1. The registered direction holds under non-work demand: D1 for I-405
  higher closed than open, and D3 for I-405 positive, in all 8 seeds,
  with I-405 ranked above I-205 on D3. Base arm for reference
  (Appendix A.2): D1 I-405 0.164 -> 0.584, D3 +1,187 +/- 117 veh-km.
- G2. The AFFECTED share falls below the base arm's 0.039 of spawned
  trips, because non-work trips are shorter and more local, so a smaller
  fraction of the population routes over a downtown freeway span at all.

Registered open question: whether the CONDITIONAL magnitudes among the
affected trips move, and in which direction. Two mechanisms point
opposite ways and I am deliberately not predicting which wins.
DILUTION: if the non-work trips that do cross the span are short and
local, they would detour onto surface streets rather than commit to a
freeway, pushing D1 and D2 down. SELECTION: if non-work trips mostly drop
out of the affected set, what remains leans more heavily on through
traffic and commuting, which are already freeway-committed, pushing D1
and D2 up. Whatever it shows is reported.

Citation rule, frozen now: D3 is a per-seed total over the affected
population, so it falls mechanically if the affected count falls. For
this arm D3 is never cited without the affected count beside it, and the
per-affected-trip value (added veh-km per affected trip) is reported with
it, so a smaller D3 cannot be misread as weaker diversion.

Correction to G2, same day, BEFORE the arm was run (2026-08-15): the 0.039
quoted above is seed 42's affected share alone. The base arm's 8-seed mean
is 0.0376 +/- 0.0016, which is the like-for-like comparison and the
stricter one, so G2 is scored against 0.0376. Nothing else changes. This
is recorded rather than edited away because the two values can give
opposite verdicts for a result landing between them, and the fwrqn D1-D3
run had not yet been started when this was written; the base numbers it
comes from are the already-published Appendix A.2 outputs.

Results will be appended, dated, before Sept 11 2026, whatever they show.

## Appendix H (2026-08-15): the section 2 "expected 0" dropped-OD count is wrong as written

Nothing above is edited. This corrects an EXPECTATION stated in section 2,
not a result, and it is written before the fwrqn D1-D3 run of Appendix G
has produced its own dropped count, so it cannot be a post-hoc reading of
that number.

Section 2 says ODs with no path on the closed graph are "expected 0". The
base arm's published outputs do not show 0: across the 8 seeds, 55
affected trips were dropped (5 to 9 per seed, about 1.1% of the roughly
620 affected trips per seed). The instrument reported this honestly all
along; the expectation beside it was simply wrong.

Cause, from a read-only comparison of each seed's open-pass affected list
against the routed rows that survived: 45 of the 55 have a DESTINATION
that is a head node of a removed span edge (40413533, 3427976322,
1343610044, 40397036). Those trips terminate inside the closed stretch.
Removing the edges leaves the destination with no inbound path, so no
closed-graph route can exist for them. That is a property of closing a
road, not a defect in the routing. The remaining 10 land on three other
nodes (256180952 with 8, plus two singletons) and are most likely
stranded pockets reachable only through the span; that is stated as
unconfirmed and a reachability check will be reported with the Appendix G
results.

Corrected expectation, replacing "expected 0" for all future scoring
including the fwrqn arm and the September comparison: zero dropped trips
whose destination lies OUTSIDE the closed stretch. Trips destined into
the closed stretch are expected to drop, and their count is reported.

Effect on the D-metrics: none that favors the registered claim. Dropped
trips are excluded from the paired set entirely, in both arms, so the
pairing stays valid on what remains. The excluded trips are the ones most
disrupted by the closure, so omitting them is conservative for a
diversion claim rather than generous to it. No published D1-D3 value
changes as a result of this appendix.

## Appendix I (2026-08-15): results of the non-work trip-level D1-D3 arm

Nothing above changes. Appendix G registered these predictions before this
run existed; this reports what they showed, supported or not. Instrument:
`src/rosequarter_d123.py --nonwork`, 8 paired seeds, same frozen 5-edge
span, same graph (md5 6707ddf25d63f2b5b4d2948b37cdb783), outputs under the
`rqd123n_` prefix. Affected trips per seed: 597, 630, 596, 606, 617, 586,
558, 565.

### I.1 G1 is SUPPORTED

| metric (8 paired seeds) | mean | sd | signs | t |
|---|---|---|---|---|
| D1 I-405, closed minus open | +0.4115 | 0.0229 | 8/8 | 50.7 |
| D3 I-405 added veh-km | +1,141 | 77 | 8/8 | 42.2 |
| D3 I-405 minus D3 I-205 (the rank) | +958 | 109 | 8/8 | 24.9 |

Underlying shares: D1 I-405 0.155 open to 0.566 closed; D1 I-205 0.073 to
0.101; D2 I-405 0.478; D2 I-205 0.059; D3 I-205 +183 +/- 62 veh-km. The
smallest I-405 D3 in any seed (1,010) exceeds the largest I-205 D3 in any
seed (298), so the registered rank order never rests on a marginal seed.

### I.2 G2 is NOT SUPPORTED

Affected share of spawned trips: base 0.0376 +/- 0.0016, non-work 0.0360
+/- 0.0015. The mean falls in the predicted direction, but the paired
per-seed difference is negative in only 5 of 8 seeds and |t| = 1.76,
under the frozen bar of 3. Recorded as NOT SUPPORTED. The reasoning behind
G2, that shorter and more local non-work trips less often cross a downtown
freeway span, may still be correct; this replication cannot certify it and
the prediction is not claimed.

### I.3 The registered open question: answered, and the answer is a null

Neither of the two named mechanisms dominates. Non-work minus base, paired
per seed: D1 I-405 closed share -0.0176 (t -1.56, lower in 5 of 8 seeds);
D2 I-405 -0.0106 (t -0.82, 4 of 8); D1 I-205 closed share -0.0003
(t -0.05); D2 I-205 +0.0010 (t +0.27). Nothing clears the bar. Adding
non-commute demand does not measurably change the diversion shares among
affected trips at this replication, so dilution and selection either
cancel or are both small. Reported as the null it is.

### I.4 The Appendix G citation rule was necessary, not decorative

D3 for I-405 fell from +1,187 veh-km in the base arm to +1,141 here. Read
alone that looks like weaker diversion under non-work demand. Per affected
trip it is 1.911 to 1.918 veh-km (t +0.14): unchanged. The whole of the
difference in the total is the smaller affected population, exactly the
misreading the rule was frozen to prevent, and it would have happened.
I-205 per affected trip rose 0.215 to 0.308 (t +2.24, up in 5 of 8), which
does not clear the bar and is not claimed.

### I.5 Appendix H completed, and one of its guesses corrected

The non-work arm dropped 45 ODs against the base arm's 55. Both arms were
then diagnosed on the closed graph. All 100 dropped trips across the two
arms are accounted for, with none left over:

- 80: the destination is a span head with in-degree 0 once the span is
  removed, so the trip ends inside the closed stretch.
- 13: the destination is node 256180952, which exactly 1 node can still
  reach, a pocket the closure seals off.
- 7: the ORIGIN is sealed off, with 0 nodes reachable from it. Every one of
  these origins is itself a span node (40382443, 40413533), so the trip
  starts on the closed stretch.

Appendix H guessed the non-span-head cases were "most likely stranded
pockets". That is right for the 13 and wrong for the 7, which are stranded
at the ORIGIN end, not the destination end. Corrected here rather than left
standing.

Appendix H's corrected expectation holds exactly: every dropped trip either
starts or ends inside the closed stretch, and no dropped trip has both ends
outside it. That is the condition future scoring should check, including in
September.

## Appendix J (2026-08-19): the scoring pipeline, its measured null floor, and the interpretation rule

Nothing above changes. Section 5 froze WHAT October compares (direction of
change per corridor group, the rank of relative gains, each station against
itself) but not the implementation, and not how large a change must be
before a direction label means anything. Both are pinned here, before the
closure.

The pipeline: `src/rosequarter_score.py` (committed 2026-08-19, before any
closure data exists). Implementation choices pinned in that commit: a
station's volume is its full-day total (the closure is 24/7); only
detectors that report in BOTH periods count toward a station, so a detector
dying between periods cannot masquerade as a traffic change; a station-day
with fewer than 20 of 24 reporting hours is dropped and said so; a corridor
group's change is the mean of its stations' relative changes, with the
per-station values always printed beside it. Coverage as of today: all 13
frozen stations active and usable (the drop rule fired once, station 3105
on Aug 13 with 11 of 24 hours, and was handled).

The null floor, measured: the pipeline was run on three disjoint pairs of
ordinary pre-closure Tue-Thu weeks, scored exactly as October will be,
with no closure anywhere in the data (`--null` for the first pair;
`--score --before ... --during ...` reproduces the other two).

| null pair (A vs B)      | in-span | upstream | downstream | I-405 | I-205 | detour gap | rank |
|-------------------------|--------:|---------:|-----------:|------:|------:|-----------:|------|
| Aug 4-6 vs Aug 11-13    |   -0.8% |    -2.4% |      -3.1% | +1.1% | +2.9% |    1.8 pts | I-205 first |
| Jul 7-9 vs Jul 14-16    |   +5.1% |    +3.2% |      +6.8% | +2.3% | +6.3% |    4.0 pts | I-205 first |
| Jul 21-23 vs Jul 28-30  |   -3.4% |    -2.5% |      -0.5% | +2.7% | -3.5% |    6.2 pts | I-405 first |

Group means on pure noise reach 6.8% in magnitude; a single station
reaches 11.2% (3110 Jefferson, third pair); the detour rank FLIPPED
across draws; and every registered direction label fired on noise at
least once. The second pair sits one week after July 4 and likely carries
vacation-recovery drift; it is kept anyway, because dropping the largest
draw after seeing it would defeat the purpose of a floor.

The interpretation rule, registered now, with an a-priori 2x safety
margin on the largest observed null values:

1. A corridor-group direction verdict is worded by where its change falls
   against the largest null group magnitude (6.8%): at or under 6.8%,
   "within the measured null floor, no evidence either way"; over 6.8% up
   to 13.6%, "direction consistent, weak evidence"; over 13.6%, "clear of
   the null floor".
2. The detour rank verdict (registered in Appendix A: I-405 above I-205)
   is worded by the gap between the two groups' changes against the
   largest null gap (6.2 points): at or under 6.2, the rank is reported
   as meaningless; over 6.2 up to 12.4, weak; over 12.4, clear.
3. These floors govern the wording of verdicts, not the frozen metrics:
   every number is still computed and reported.

One expected consequence, stated up front: Appendix A registers the I-205
gain as weak. If the real I-205 change lands under the floor, it is
reported as "no evidence either way", not as support and not as failure.
The in-span collapse and the signed I-405 detour are expected to clear
these floors by an order of magnitude.

Caveats registered with the rule: three draws is a small sample of weekly
variability, so the floor is a measured minimum, not a distribution
quantile, which is why the 2x margin is applied; and the null pairs are
adjacent or near-adjacent weeks, matching section 5's same-weekday
pre-closure baseline rule.

## Appendix K (2026-08-19): the improved-model arm (fwrqi), registered before it runs

This is the arm section 6's variant clause anticipated, in its validated
form. Since Appendix A was registered, the model's freeway layer has been
validated directly against reality: 91 active PORTAL mainline stations on
I-5, I-205, I-405, US-26 and OR-217, three pre-closure weekdays (Aug 11-13
2026), median model-to-real daytime speed ratio 0.97, nothing fitted to any
speed or count data. The configuration that earned that number is the
realism stack (explicit MOBIL lanes, driver heterogeneity, Webster signal
timing with green-wave coordination) plus a corrected per-direction real
lane model on a re-downloaded 20 km graph that keeps the OSM lane tags the
original cache dropped. This appendix registers that exact configuration as
a separately labeled arm, so October can grade the base model and the
validated model head to head.

- Arm: prefix fwrqi, `python src/freeway_rosequarter.py --improved`
  (branch commit 0f4ed3a, committed and pushed before this appendix).
  Identical to the Appendix A campaign in design: same frozen span
  specification, same guard, same 8 paired seeds, same open/closed arms,
  same tracked routes, same verdict rules, mixed fleet. Differences, all
  stated: the realism stack is on, the corrected real-lane model is on,
  and the campaign runs on the lane-tagged graph. Two experimental
  mechanisms that exist on the same branch (an improved merge-entry rule
  and en-route rerouting) are explicitly OFF: both failed parts of their
  own registered re-validations this week and neither is accepted into the
  citable model.
- The frozen span was re-verified on the lane-tagged graph before this
  registration: the scenario selects exactly 5 edges, the same 3 SB
  mainline edges registered in section 1 plus the 2 stranded ramps.
- Predictions, banked now: same directions as Appendix A (the closed span
  down to zero in the model, I-405 up, I-205 up weakly, rank I-405 above
  I-205), graded by the standing bar (unanimous sign across 8 paired seeds
  and |t| > 3 on the paired relative differences). The registered open
  question: whether the validated stack changes the MAGNITUDE of the
  I-405 gain relative to the realism arm's +35.6% (the corrected lanes
  raise freeway capacity, which could carry more diverted traffic at
  speed); whatever it shows is reported.
- The primary registered predictions remain Appendix A's and do not
  change. This arm's numeric results will be appended, dated, before
  Sept 11.

## Appendix L (2026-08-20): results of the improved-model arm (fwrqi)

Nothing above changes. The Appendix K campaign ran overnight: SLURM array
129864, 16 of 16 tasks COMPLETED (submitted Aug 19 after commit 3236d00
pushed, last task finished 00:46 Aug 20), readout by the committed script
(`--readout --improved`). The frozen-span guard passed in all 8 closed
tasks: exactly 5 edges removed in every run. Registration provably
preceded every run.

### L.1 Corridor route totals (paired per-seed, closed minus open)

Same frozen verdict bar as Appendix A: unanimous sign across the 8 paired
seeds and |t| > 3 on the paired relative differences.

| route | mean % | sd | signs | verdict |
|-------|--------|----|-------|---------|
| I-405 | +37.7 | 9.7 | 8/8 | SUPPORTED, t = 11.1 |
| I-205 | +0.2 | 2.6 | 4/8 | not supported, t = 0.2 |
| I-5 (route total) | +2.3 | 5.8 | 5/8 | not supported, t = 1.1 |
| OR-213 | +0.1 | 6.7 | 2/8 | not supported, t = 0.0 |
| US-26 | -1.7 | 7.0 | 4/8 | not supported, t = 0.7 |

Absolute companions, per the standing rule that these percentages are
never cited alone: I-405 gains +644 +/- 163 g NOx per simulated hour on
an open-arm base of 1,708 g; I-205 gains +33 +/- 486 g on a base of
18,451 g. The I-405 base differs from Appendix A's 959 g because this arm
runs the realism stack with corrected real lanes on the lane-tagged
graph; bases are only comparable within an arm. The closed span's own
volume goes to zero by construction (the edges are removed).

The registered predictions hold: I-405 up, rank of relative gains I-405
above I-205. Corridor-level I-205 stays unresolvable, as in every other
arm, which is why the trip-level D1-D3 metrics carry that part of the
prediction. The I-5 route-total mean flips positive here (+2.3%, 5/8)
where other arms leaned negative; it is inside seed noise, reaches no
bar, and claims nothing. US-26, which cleared the numeric bar as an
unregistered exploratory finding in the realism arm (F.1), does not
clear it here (4/8, t = 0.7).

### L.2 The registered open question, answered

Appendix K registered one open question: whether the validated stack
changes the MAGNITUDE of the I-405 gain relative to the realism arm's
+35.6%. It does not: +37.7% vs +35.6%, a 2.1-point difference against
per-arm seed sds of about 10 points. The corrected real-lane model, the
piece the PORTAL validation added on top of the realism stack, leaves
the diversion magnitude essentially unchanged. The magnitude split in
this campaign is between the base model (+84.9%) and everything running
the realism dynamics (+35.6% and +37.7%); the lane correction moves
model-to-real speed agreement, not the closure response.

### L.3 Standing

The headline registered prediction, I-405 absorbs the diversion and its
relative gain outranks I-205, is now SUPPORTED in six of six registered
tests: base, realism, non-work, peak, quiet, and the PORTAL-validated
improved model. October grades the base arm (Appendix A, the primary
registration) and this arm head to head against the real closure, under
the Appendix J null-floor wording rules.

## Appendix M (2026-08-20): arterial travel-time predictions against the public logger, registered before the instrument runs

Nothing above changes. PORTAL grades the freeway predictions (section 5),
but the model's most distinctive closure predictions are about SURFACE
streets, and nobody archives surface travel times. Since Aug 18 a public
companion repository, github.com/darcy0408/portland-traveltime-log, has
logged live TomTom travel times hourly for 12 frozen OD pairs (its commit
history is the timestamp; its pairs.json is frozen; two far-field control
pairs included). This appendix registers the model-side instrument, its
rules, the directional expectations, and the October grading protocol,
all BEFORE the instrument first runs on campaign data.

### M.1 The instrument

`src/rosequarter_traveltime.py`, branch commit b6c215a, committed and
pushed before this appendix. Read-only on the finished campaigns' saved
per-segment results (base arm fwrq, job 126285; improved arm fwrqi, job
129864), no simulation. Its mechanics were verified on a synthetic toy
graph only; as of this registration it has never been run on campaign
data. Rules pinned in that commit:

- Realized edge travel time = value / throughput (vehicle-seconds per
  traversing vehicle), floored at free-flow time. An edge that carried
  vehicles but discharged none inside the simulated hour gets the 3,600 s
  horizon as its time; untraveled edges get free-flow.
- The model quantity per pair, seed, and arm is the FASTEST-PATH travel
  time under those realized times, open network vs closed network. This
  is the model analog of the logger's live router (fastest route under
  current conditions), deliberately not the sim's own spawn router.
- A pair is model-gradeable only if both endpoints snap within 500 m of
  a graph node. Known at registration: ctrl_west's Hillsboro endpoint
  sits about 7 km outside the 20 km graph, so ctrl_west is expected to
  be excluded on both arms; it remains a logger-side control.
- Verdict bar: the standing campaign bar, unanimous sign across the 8
  paired seeds and |t| > 3 on the paired relative differences.
- A route SWITCH is flagged when the closed-arm path length differs from
  open by more than 10%, the model analog of the logger's length_m jump.

### M.2 Directional expectations, banked now

The instrument's numeric output, appended in a dated results appendix,
becomes the graded prediction (the same relationship section 4 has to
Appendix A). Directions expected now, before any run:

- UP: i5sb_span, vanc_pdx, i5sb_detour (these three normally use or feed
  the closed span; route switches expected), interstate_sb (the surface
  parallel), mlk_sb (the eastside surface alternative), i84wb_feeder
  (the severed WB-to-SB movement's approach).
- UP weakly, may not clear the bar: i205_sb (the corridor-level I-205
  signal cleared the bar in no arm).
- ABOUT NO CHANGE (direction controls; northbound is untouched):
  williams_nb, grand_nb.
- NO CHANGE (far-field model control): ctrl_se. A unanimous move here
  would flag a network-boundary artifact, stated now.
- OPEN QUESTION, either answer reported: powell_wb (Powell may absorb
  eastside diversion; the corridor-level US-26/Powell signal stayed
  inside noise in every arm).

### M.3 October grading protocol against the logger, frozen now

Extends section 5 without changing it; the section 5 discipline carries
over (direction and rank, never absolute magnitudes; each pair against
itself; prefer early-closure days before adaptation accumulates).

1. Logger rows with status ok only; the graded quantity is travel_s per
   pair. Rows are assigned to hours in Pacific time.
2. Daytime rows only, 06:00 to 20:00: the model is a steady-state
   average daytime hour, and overnight free-flow rows would dilute every
   change toward zero by construction.
3. Before = Tue-Thu days from the pre-closure logging period, avoiding
   Labor Day week (Sept 7-11). During = Tue-Thu days inside the closure,
   preferring the first two closure weeks.
4. Per pair: percent change in mean daytime travel_s, before vs during.
   Direction verdicts per pair, plus the RANK of gains across the
   model-gradeable surface pairs, graded against the model's registered
   rank. Model magnitudes are reported for honesty, never graded: the
   model's demand is fixed and cannot evaporate, shift in time, or
   change mode the way five weeks of real drivers will.
5. Null floor: the Appendix J procedure, applied to the logger's own
   pre-closure data (disjoint before-period week pairs scored exactly as
   October will be, no closure anywhere in the data), with the same
   a-priori 2x safety margin and the same tiered wording rule. The floor
   will be measured and appended in a dated addendum before Sept 11,
   after enough pre-closure weeks exist and before any closure data is
   seen. The two real-side control pairs must sit inside the floor for
   the comparison to be clean; if they do not, region-wide drift is
   reported, per-pair changes are additionally reported net of the mean
   control change, and direction verdicts use the raw values with the
   floor wording regardless.

One honest limitation, stated now: TomTom travel_s is a routing
engine's live estimate, not a probe-vehicle measurement, and its
internals can change without notice. That is exactly why the control
pairs and the measured null floor exist, and why direction and rank are
graded rather than minutes.

## Appendix N (2026-08-20): arterial travel-time results, both arms

Nothing above changes. The Appendix M instrument ran on Orca the same
day M was registered, base arm and improved arm, on the campaigns' saved
parquets (no simulation; base graph md5 re-verified against the Appendix
A fingerprint before the run). Outputs banked: rqtt_fwrq.json and
rqtt_fwrqi.json; the tables below were recomputed locally from those
banked files and match the run logs. ctrl_west was excluded by the snap
rule on both arms, exactly as M predicted. All 11 remaining pairs
resolved on all 8 seeds in both arms, no disconnections.

Columns: mean one-way minutes (open, closed), then the paired per-seed
percent change; bar = unanimous sign + |t| > 3; switch = seeds where the
closed-arm path length moved more than 10% (the logger's length_m
signal). Minutes are reported for honesty and are never graded (M.3).

### N.1 Base arm (fwrq, the primary registration)

| pair | open min | closed | mean % | sd | signs | switch | verdict |
|------|---------|--------|--------|----|-------|--------|---------|
| i5sb_span | 17.7 | 18.9 | +6.9 | 2.5 | 8/8 | 0/8 | SUPPORTED, t=7.8 |
| vanc_pdx | 21.0 | 22.1 | +5.4 | 1.4 | 8/8 | 0/8 | SUPPORTED, t=10.7 |
| i5sb_detour | 12.4 | 15.6 | +25.7 | 4.3 | 8/8 | 1/8 | SUPPORTED, t=16.7 |
| interstate_sb | 10.1 | 10.2 | +1.0 | 2.0 | 6/8 | 1/8 | not supported, t=1.5 |
| williams_nb | 7.7 | 7.5 | -2.7 | 3.2 | 2/8 | 0/8 | not supported, t=2.4 |
| mlk_sb | 13.9 | 14.3 | +3.3 | 2.0 | 8/8 | 2/8 | SUPPORTED, t=4.7 |
| grand_nb | 9.7 | 9.8 | +0.5 | 1.0 | 6/8 | 0/8 | not supported, t=1.5 |
| i205_sb | 16.3 | 16.4 | +0.3 | 1.4 | 4/8 | 0/8 | not supported, t=0.7 |
| i84wb_feeder | 15.6 | 15.8 | +1.3 | 1.4 | 7/8 | 2/8 | not supported, t=2.5 |
| powell_wb | 13.6 | 13.6 | +0.4 | 0.8 | 4/8 | 0/8 | not supported, t=1.4 |
| ctrl_se | 20.6 | 20.6 | -0.1 | 0.3 | 5/8 | 0/8 | not supported, t=0.5 |

### N.2 Improved arm (fwrqi, the PORTAL-validated stack)

| pair | open min | closed | mean % | sd | signs | switch | verdict |
|------|---------|--------|--------|----|-------|--------|---------|
| i5sb_span | 12.3 | 16.3 | +32.9 | 4.3 | 8/8 | 0/8 | SUPPORTED, t=21.6 |
| vanc_pdx | 14.0 | 17.3 | +23.5 | 2.3 | 8/8 | 0/8 | SUPPORTED, t=29.0 |
| i5sb_detour | 10.5 | 14.4 | +37.0 | 3.1 | 8/8 | 7/8 | SUPPORTED, t=34.2 |
| interstate_sb | 7.7 | 8.8 | +14.6 | 3.4 | 8/8 | 0/8 | SUPPORTED, t=12.1 |
| williams_nb | 8.5 | 8.5 | -0.1 | 1.3 | 3/8 | 1/8 | not supported, t=0.3 |
| mlk_sb | 11.5 | 12.7 | +10.7 | 6.8 | 7/8 | 7/8 | not supported, t=4.5 |
| grand_nb | 12.2 | 12.4 | +1.5 | 3.3 | 5/8 | 3/8 | not supported, t=1.3 |
| i205_sb | 11.2 | 11.1 | -1.0 | 2.0 | 3/8 | 0/8 | not supported, t=1.4 |
| i84wb_feeder | 14.5 | 14.5 | -0.6 | 2.0 | 2/8 | 0/8 | not supported, t=0.8 |
| powell_wb | 11.5 | 11.6 | +0.6 | 1.6 | 6/8 | 0/8 | not supported, t=1.0 |
| ctrl_se | 18.9 | 18.8 | -0.7 | 0.6 | 2/8 | 0/8 | not supported, t=3.0 |

### N.3 Grading against M.2, honest

- The three closed-span pairs (i5sb_span, vanc_pdx, i5sb_detour) go UP
  at the bar in BOTH arms: 6 of 6. The signed-detour reroute M expected
  shows as route switching on i5sb_detour in the improved arm (7/8
  seeds), the length-jump signature the logger can verify directly.
- interstate_sb: supported in the improved arm (+14.6), MISSED in the
  base arm (+1.0, 6/8). mlk_sb: supported in the base arm (+3.3, 8/8),
  missed the unanimity half in the improved arm (+10.7, 7/8).
- i84wb_feeder: the registered UP direction FAILED in both arms (flat).
  Reported as a failed prediction wherever this instrument is discussed.
- i205_sb stayed under the bar in both arms, as registered (weak).
- powell_wb, the registered open question, answers NO CHANGE both arms.
- Every control held: williams_nb and grand_nb (direction controls) and
  ctrl_se (far-field) reached the bar nowhere, so the network-boundary
  artifact M warned about did not appear.

### N.4 The registered rank for October (M.3 rule 4)

Both arms agree on the top of the rank: i5sb_detour first, i5sb_span
second, vanc_pdx third. The arms swap the next two (improved:
interstate_sb then mlk_sb; base: mlk_sb then interstate_sb); both
orderings are registered, arm-labeled, and October reports which arm's
rank the logger matched. All remaining pairs are declared
indistinguishable from seed noise and take no rank.

A magnitude contrast, reported not graded: the improved arm prices the
closure two to five times higher on the closed-span pairs (+32.9 vs
+6.9 on i5sb_span) and is the arm that actually reroutes the signed
detour trip. The head-to-head October grading (Appendix L) therefore
has real discriminating power on the surface pairs, not only on the
freeway corridors.

## Appendix O (2026-08-23): the access-lane closure-geometry arm (fwrqa), registered before it runs

Every arm so far models the span as fully closed, a simplification section 1
states outright. ODOT's announced plan is not a full closure: one southbound
lane stays open from the I-405 junction to the Broadway/Weidler exit (302A)
for local access, and everything south of 302A closes. This appendix
registers an arm that models that geometry, so October can grade a second
fidelity axis alongside Appendix K's. The base-vs-improved contrast asks how
much the driving behavior matters; full-closure-vs-access-lane asks how much
correctly reading the closure notice matters. The second axis is the one a
practitioner controls directly.

- Arm: prefix fwrqa, `python src/freeway_rosequarter.py --accesslane`
  (branch commit 77e9468, committed and pushed before this appendix).
  The fwrqi stack VERBATIM: realism stack on, corrected real lanes on, the
  lane-tagged graph, mixed fleet, merge-entry and rerouting explicitly OFF.
  Same 8 paired seeds, same tracked routes, same verdict rules. The ONLY
  difference from fwrqi is the closed-arm graph surgery.
- The partial closure, frozen edge for edge on the lane-tagged graph:
  - KEPT: mainline edge (40382443, 40397036, 0), I-405 junction to exit
    302A, 537 m, clamped from its tagged 4 lanes to 1 (the task refuses to
    run if the graph tags anything but 4, the same fail-loudly rule as the
    span guard). KEPT: the 302A off-ramp (40397036, 1343610044, 0).
  - REMOVED: the 2 southern mainline edges (40397036, 40413533, 0) and
    (40413533, 3427976322, 0), plus the stranded on-ramp
    (40413546, 40413533, 0). Exactly 3 of the full closure's 5 edges.
  - After removal, node 40397036 has the off-ramp as its only outgoing
    edge, so through traffic is structurally forced off at Broadway/
    Weidler, which is what ODOT's signage does. Verified end to end before
    this registration: the full-closure spec still selects its 5 edges on
    this graph, the partial closure removes exactly 3, the forced exit
    holds, and prepare_network resolves the kept edge to n_lanes = 1
    through the same real-lanes path the simulation uses.
- Stated modeling choices, registered now: the kept edge's tagged maxspeed
  is unchanged (the arm models the capacity cut only, not a work-zone speed
  limit), and there is no "local access only" destination filter (routing
  under realized times decides who uses the lane, as a live router does;
  real compliance sits somewhere between full filtering and none).
- Open-arm identity check, registered now: the fwrqa open arm is configured
  identically to the fwrqi open arm, so per-seed equality of their summary
  files is an integrity check of the whole pipeline. Any difference voids
  the arm and is reported.
- The graded contrast, registered now: per pair and per seed, the paired
  difference of closed-arm realized fastest-path travel times, fwrqa minus
  fwrqi (open arms shared), under the Appendix M instrument extended with
  an `access` arm entry (same commit). Verdict bar: the standing unanimous
  sign across 8 paired seeds and |t| > 3.
- Directional expectations for that contrast, banked now, before any run.
  All from the closure geometry, nothing from data:
  - vanc_pdx DOWN (closed-arm time smaller than fwrqi's): the pair ends at
    Pioneer Courthouse Square, and a downtown destination is exactly what
    the access lane plus the Broadway exit serves. The flagship geometry
    prediction.
  - interstate_sb DOWN: the pair ends at Broadway Bridge east, inside the
    area the access lane serves, and the surface parallel should shed the
    Broadway-bound diversion it carried under full closure.
  - i84wb_feeder ABOUT NO CHANGE: the severed WB-to-SB movement stays
    severed in this arm, and an I-84 WB approach cannot reach the access
    lane. This pair is the geometry arm's own control.
  - williams_nb, grand_nb, ctrl_se ABOUT NO CHANGE: northbound and
    far-field, untouched in both arms.
  - i5sb_span, i5sb_detour, i205_sb: reported, weak prior DOWN or no
    change (an added option cannot lengthen a fastest path at equal
    congestion, but the single clamped lane may congest enough that the
    router avoids it); the route-switch signature is expected to persist
    in both, since everything south of 302A is still gone.
  - mlk_sb, powell_wb OPEN QUESTION, either answer reported: Broadway
    egress feeds the MLK/Grand couplet southward, which could raise
    eastside surface load even as through diversion falls.
- October grading: the M.3 protocol applies to fwrqa verbatim, as a third
  graded arm wherever M.3 graded two. The three-way base / improved /
  access comparison is the registered instrument for the fidelity
  question: which axis, behavior or geometry, moves the predictions
  closer to what the logger records.
- The primary registered predictions remain Appendix A's and do not
  change. This arm's numeric results will be appended, dated, before
  Sept 11.

## Appendix P (2026-08-24): access-lane arm (fwrqa) results

Nothing above changes. The fwrqa campaign registered in Appendix O ran on
Orca as job 131478 (16/16 tasks completed, exit 0) on branch commit
77e9468, the same commit the appendix registered. The readout and the
graded contrast below were run on the campaign's saved outputs, no
simulation.

### P.1 The registered integrity check

The open-arm identity check PASSES 8/8: every fwrqa open summary is
identical to its fwrqi counterpart on every physics field (network NOx,
network throughput, all per-route values, vehicle and step counts). The
only differing fields are the arm's own stack label and an empty
access-lane bookkeeping key, both written by the fwrqa code path itself.
Verified twice: on Orca at harvest and again locally on the pulled
summaries. The arm is valid per its registration.

### P.2 Corridor route totals (paired per-seed, closed minus open), reported

Same frozen verdict bar as the other arms: unanimous sign across the 8
paired seeds and |t| > 3.

| route | mean % | sd | signs | verdict |
|-------|--------|----|-------|---------|
| I-405 | +34.8 | 10.2 | 8/8 | SUPPORTED, t = 9.7 |
| I-5 (route total) | +1.5 | 7.8 | 4/8 | not supported, t = 0.5 |
| I-205 | -0.9 | 3.1 | 4/8 | not supported, t = 0.8 |
| OR-213 | -1.2 | 8.3 | 4/8 | not supported, t = 0.4 |
| US-26 | +0.8 | 7.2 | 4/8 | not supported, t = 0.3 |

Read against Appendix L's full-closure table (I-405 +37.7, everything
else flat), the partial closure reproduces the same single-route
diversion signature at slightly smaller magnitude, which is the
direction a milder closure should move. Absolute companions, per the
standing rule that these percentages are never cited alone: I-405 gains
+591 +/- 170 g NOx per simulated hour on an open-arm base of 1,708 g
(fwrqi full closure: +644 +/- 163 g on the same 1,708 g base; the bases
are identical because the open arms are identical).

### P.3 The graded contrast: fwrqa minus fwrqi, closed arms

The Appendix M instrument ran on the fwrqa campaign as Orca job 131982
(banked output rqtt_fwrqa.json); the registered cross-arm contrast was
computed from the banked rqtt_fwrqa.json and rqtt_fwrqi.json exactly as
Appendix N recomputed its tables. ctrl_west was excluded by the snap
rule, as in both prior arms. Integrity: the shared open arms reconstruct
IDENTICAL open-arm times, max difference 0.0 s across all pairs and
seeds. Columns: mean closed-arm minutes under each arm, then the paired
per-seed percent difference (fwrqa minus fwrqi over fwrqi); bar =
unanimous sign + |t| > 3.

| pair | fwrqi min | fwrqa min | mean % | sd | signs | verdict |
|------|-----------|-----------|--------|----|-------|---------|
| i5sb_span | 16.3 | 16.7 | +2.5 | 2.2 | 7/8+ | under bar, t=3.2 |
| vanc_pdx | 17.3 | 17.1 | -1.1 | 1.3 | 6/8- | under bar, t=2.4 |
| i5sb_detour | 14.4 | 14.2 | -1.4 | 4.3 | 4/8 | under bar, t=0.9 |
| interstate_sb | 8.8 | 9.0 | +1.2 | 1.7 | 6/8+ | under bar, t=2.1 |
| williams_nb | 8.5 | 8.5 | -0.1 | 0.9 | 5/8- | under bar, t=0.3 |
| mlk_sb | 12.7 | 12.8 | +0.9 | 1.3 | 6/8+ | under bar, t=2.1 |
| grand_nb | 12.4 | 12.3 | -0.5 | 2.1 | 5/8+ | under bar, t=0.7 |
| i205_sb | 11.1 | 11.1 | +0.6 | 2.5 | 5/8+ | under bar, t=0.7 |
| i84wb_feeder | 14.5 | 14.5 | +0.0 | 2.1 | 5/8+ | under bar, t=0.1 |
| powell_wb | 11.6 | 11.5 | -0.6 | 1.0 | 5/8- | under bar, t=1.5 |
| ctrl_se | 18.8 | 18.7 | -0.0 | 0.9 | 5/8- | under bar, t=0.1 |

The banked directions, graded, honest:

- vanc_pdx DOWN, the flagship geometry prediction: NOT SUPPORTED at the
  bar. The sign leans the predicted way (-1.1%, 6/8 seeds negative) but
  the effect is a percent, inside seed noise, t = 2.4.
- interstate_sb DOWN: NOT SUPPORTED, and the lean is the WRONG WAY
  (+1.2%, 6/8 positive). A failed direction, reported as such.
- i84wb_feeder ABOUT NO CHANGE (the arm's own control): HOLDS
  (+0.04%, t = 0.1).
- williams_nb, grand_nb, ctrl_se ABOUT NO CHANGE: all HOLD.
- i5sb_span, i5sb_detour, i205_sb (reported, weak prior DOWN or no
  change): i5sb_span NOT SUPPORTED at the registered bar (7/8 seeds,
  misses unanimity). Separately, as exploratory evidence only, outside
  the preregistered grading: the lean is UP (+2.5%, 7/8 seeds, t = 3.2),
  opposite the weak DOWN/flat prior; the registered caveat anticipated
  the mechanism (the single clamped lane congests enough to price paths
  higher than a clean detour). i5sb_detour and i205_sb flat.
- mlk_sb, powell_wb OPEN QUESTION: both answer NO CHANGE at the bar
  (+0.9%, t = 2.1 and -0.6%, t = 1.5).

For honesty beside the contrast: the fwrqa arm's own closed-minus-open
table (banked in rqtt_fwrqa.json, same bar) reads nearly identically to
fwrqi's Appendix N.2: i5sb_span +36.2, vanc_pdx +22.1, i5sb_detour
+35.1, interstate_sb +16.0, all four SUPPORTED 8/8; mlk_sb +11.7 at 7/8
with the same 7/8 route-switch signature; every control under the bar.

### P.4 What this adds to the October instrument

The second fidelity axis has an answer, and it is small. Holding the
behavioral stack fixed, changing the closure geometry from full shutdown
to ODOT's actual access-lane plan moves closed-arm travel times by about
one to two percent, under the bar on every pair, while Appendix N showed
the behavioral axis (base vs improved stack) moves the same predictions
by factors of two to five on the closed-span pairs. Within this model,
misreading the closure notice costs far less prediction accuracy than
mis-modeling driver behavior. October grades all three arms against the
logger under M.3 unchanged; if the logger's measured changes land nearer
the arms' shared predictions than to their differences, that is itself
the fidelity result this instrument was registered to produce.

## Appendix Q (2026-08-24): the logger null-floor unit, registered before the floor is measured

Nothing above changes except one word of M.3 rule 5, amended here in the
honest window: before the floor is measured, before any closure data
exists, and before the instrument has ever run on logger data.

The gap, found Aug 23: M.3 rule 5 says the logger's null floor uses
"disjoint before-period week pairs", the Appendix J structure. Appendix J
had six pre-closure weeks to draw from; the logger began Aug 18 and the
closure starts Sept 11, so with Labor Day week excluded (M.3 rule 3) the
pre-closure window holds exactly three clean Tue-Thu weeks: Aug 18-20,
Aug 25-27, Sept 1-3. Three weeks admit only ONE disjoint week pair, and a
floor from a single draw is not a floor. The unit choice has to be made,
and it is made now, while the second of those weeks is still in the
future.

- The registered unit: the WEEK stays the unit, because a clean Tue-Thu
  week pool is exactly the shape October's before-vs-during comparison
  uses (M.3 rules 3-4), and a floor must be measured in the unit it
  polices. The floor uses ALL pairwise combinations of the clean
  pre-closure weeks: three draws from three weeks. The draws share weeks
  and are NOT independent; the instrument prints that wherever it prints
  the floor. This amendment can only RAISE the measured floor relative to
  any single disjoint pair (a maximum over three draws is at least the
  maximum over one), so it is conservative in the direction that makes
  October claims harder, not easier.
- The rejected unit, and why: day pairs would give more draws but
  measure a different quantity than the one October uses, with a bias
  whose direction depends on the variant. Day pairs within a week miss
  slow week-scale drift (a school-year start, a rainy week, a routing
  engine change), so their floor would sit too LOW, and ordinary drift
  could be called a closure effect. Single days paired across weeks
  average less than October's three-day pools, so their floor would sit
  too HIGH, and October would go too timid. Converting either to the
  week scale would need assumptions invented after the fact; matching
  the unit removes the question. Day-level draws are not part of the
  floor; if the instrument ever prints them they are labeled diagnostic
  and never govern wording.
- Weekend rows, stated now: the logger records weekends, but weekend
  rows are never part of the graded instrument or the floor. Weekend
  traffic differs systematically (that is pattern, not noise), and the
  model simulates an average weekday hour, so it has no weekend
  prediction to grade. Any weekend analysis in October is exploratory,
  labeled as such, and governs nothing.
- The instrument: src/rosequarter_logger_floor.py, committed before this
  appendix (main fe2c893). ONE shared code path scores a per-pair percent change in mean
  daytime travel_s between two day pools, and both the floor draws and
  the October before-vs-during run go through it, so floor and graded
  number cannot diverge in method. Implementation choices pinned in that
  commit: status ok rows only; hours assigned in Pacific time as a fixed
  UTC-7 (the whole logging window sits inside Pacific daylight time; the
  script refuses rows on or after the Nov 1 DST change rather than
  mislabel them); daytime = 06:00 <= local hour < 20:00, 14 slots; a
  pair-day with fewer than 12 of 14 daytime hours ok is dropped and said
  so (Appendix J's 20-of-24 rule scaled to the daytime window); a pool's
  mean is over all ok daytime rows on usable pair-days.
- The floor statistic: the largest per-pair magnitude across all pairs
  and all draws, one global floor, Appendix J style. Appendix J's
  a-priori 2x safety margin and tier wording apply verbatim: at or under
  the floor, "within the measured null floor, no evidence either way";
  over it up to 2x, "direction consistent, weak evidence"; over 2x,
  "clear of the null floor".
- One October qualifier, registered now in the spirit of Appendix J rule
  3 and matching Appendix N.4's practice: a pair whose October change
  sits within the floor takes NO RANK in the M.3 rule 4 rank grading,
  exactly as N.4 declared seed-noise pairs rankless on the model side.
  Floors govern wording and ranking eligibility, never the frozen
  metrics; every number is still computed and reported.
- Mechanics verification: the instrument's --selftest builds synthetic
  rows with hand-computed answers and checks the filters (status,
  daytime boundary hours at both ends, Tue-Thu), the Pacific conversion,
  the drop rule, clean-week enumeration, an exact +10.0% change, and the
  DST refusal. It passes at the pinned commit. As of this registration
  the instrument has NEVER been run on logger data, the same discipline
  Appendix M used for the travel-time instrument.
- Honest caveat, stated now: three overlapping draws from three weeks
  sample less weekly variability than Appendix J's three independent
  pairs from six weeks. The logger cannot be extended backward in time,
  so this is the maximum the data admits; the 2x margin exists for
  exactly this small-sample reason, per Appendix J's own caveat.
- Schedule, unchanged from M.3 rule 5: the floor is measured with
  --floor after the Sept 1-3 week's rows land and appended in a dated
  addendum before Sept 11, before any closure data is seen. The
  requirement that the two control pairs sit inside the floor, and the
  drift fallback if they do not, carry over verbatim.

## Appendix R (2026-08-27): the signed-detour compliance arm (fwrqc), registered before it runs

Every closed arm so far routes each displaced vehicle onto its own fastest
path, a population in which every driver ignores ODOT's detour signage. The
real closure ships with an official plan: through traffic is signed onto
I-405 SB. Between "everyone ignores the signs" and "everyone follows them"
lies the real population, and no registered arm spans that axis. This
appendix registers it: guidance response, a third fidelity axis beside
driving behavior (Appendix K) and closure geometry (Appendix O). Registered
before Sept 11 the arm is falsifiable; built afterward it would be fitting
to data already seen. A detour plan is a designated route plus a compliance
level, so this arm is also the machinery that scores a detour plan on
congestion and exposure together, the practical capability behind the
broader-impact framing.

- Arm: prefix fwrqc, `python src/freeway_rosequarter.py --compliance`
  (branch experiment/detour-compliance, commit b3df21b, pushed before this
  appendix). The fwrqi stack and the FULL five-edge closure VERBATIM; the
  only change is closed-arm route assignment. fwrqc-vs-fwrqi therefore
  isolates guidance response.
- Eligibility, frozen: a trip is detour-eligible iff its route on the OPEN
  network crosses the closed span's south exit, the final SB mainline edge
  (40413533, 3427976322). Those trips continue past the closure and are
  through traffic by definition; local trips never comply.
- Mechanism, frozen: a compliant trip routes origin -> via -> destination
  on the closed network, decided ONCE at spawn (route-once, no replanning,
  same as every arm). The via node is 40379068, on the I-405 SB mainline
  near W Burnside: past the I-5 diverge and the first exits, upstream of
  the US-26 junction, so passing it commits the trip to the signed loop
  while the rest of the route stays free. A probe showed the network's
  fastest detour leaves I-405 early for surface streets, which is exactly
  the difference between free rerouting and following the signs.
- Compliance levels, frozen: 0.25 / 0.50 / 0.75, all a priori. No data on
  signage compliance exists to pick one number, so three levels bracket it
  and no level is ever tuned after results are seen. Draws come from a
  dedicated RNG stream (RANDOM_SEED + 4), one draw per eligible trip
  regardless of level, so the trip stream is untouched and the same seed
  sees the same draw sequence at every share.
- Stated modeling choices, registered now: compliance is binary and
  per-trip (no partial or abandoned detours); the Webster warmup population
  spawns without compliance (its own isolated stream), so signal timing
  reflects free rerouting, a second-order effect on surface signals; the
  arm uses the full closure, not Appendix O's access lane, so the two axes
  stay separated; a compliant trip whose via route fails falls back to the
  free route and is counted (n_fallback in the saved summary), never
  silent, and realized compliance is recorded per run.
- Campaign: one flat 32-task array (8 shared open tasks + 8 closed per
  level), single submission, one-writer rule. The open arm is
  share-independent, so one open set serves all three levels.
- Integrity checks, registered now: (1) fwrqc_open must equal fwrqi_open
  per seed exactly (network totals and every tracked route; --readout
  runs the check, any mismatch voids the campaign); (2) share 0 is the
  identity, verified by a spawn-level selftest (routes and trip RNG
  stream byte-identical to the machinery off), PASSED at b3df21b before
  this registration: 2,000 uniform-OD spawns, 94 eligible, share 1 routed
  all 94 via the I-405 mainline with zero fallbacks, eligibility count
  identical across shares; (3) the standing frozen-span guard, plus: the
  marker edge must be absent from the closed graph and present in the
  open graph, and the via node must be an endpoint of an I 405 mainline
  edge. All fail loudly.
- Banked predictions, before any run. Verdict bar unchanged: unanimous
  sign across the 8 paired seeds and |t| > 3.
  - R1 (primary): dose-response on the signed detour. The I-405 NOx gain
    (closed minus open) increases monotonically with the compliance
    level, gain(0.25) < gain(0.50) < gain(0.75), per seed. No other arm
    can produce this prediction.
  - R2: at every level the I-405 gain is at least fwrqi's (+37.7%), since
    compliance only adds traffic to the loop, and I-405 outranks I-205 at
    every level.
  - R3: surface alternates (US 26, OR 99E, OR 213 route totals; the
    interstate_sb, mlk_sb, vanc_pdx instrument pairs) move DOWN relative
    to fwrqi as compliance rises, since compliant trips leave the surface
    streets. Registered with the explicit caveat that Appendix P's two
    banked DOWN calls landed under the bar, so these may too; an
    under-the-bar result is reported as such, never re-argued.
  - R4: travel-time instrument (arms compliance25/50/75, shared open,
    same Appendix M commit rules): the i5sb_detour pair rises with the
    compliance level, and Appendix N's October rank is re-registered per
    level.
  - R5: network NOx total rises slightly with compliance (the signed loop
    is longer than the surface shortcuts), staying within a few percent;
    the conservation check applies at every level.
- October grading: the three levels enter the M.3 head-to-head under the
  frozen rules (Appendix J floors). Whichever level's predictions land
  nearest the real logger and PORTAL data gives an observational estimate
  of signage compliance during a real five-week closure, a quantity absent
  from the literature.
- Citation rules: never cite an fwrqc diversion percentage without naming
  the level; R1 is about within-model ordering, and October says which
  level the real data lands nearest, not which is "right"; realized
  compliance (detour_stats) is cited alongside the configured share
  whenever a level is named.
- The primary registered predictions remain Appendix A's and do not
  change. This arm's numeric results will be appended, dated, before
  Sept 11.

## Appendix Q addendum (2026-08-28): scheduler outage in floor week 2, and the instrumentation fix

Registered pre-measurement: written before any null-floor computation has
run (the floor run stays scheduled for ~Sept 4, on whatever clean weeks
exist then) and before any closure-period data exists.

### What happened

On Aug 26 2026 GitHub's job scheduler began starving the logger's single
hourly cron slot. Every run that fired completed successfully in about 25
seconds with clean data (zero non-ok rows, all 12 pairs), but most hours
never fired at all: Aug 26 recorded 5 of 14 daytime Pacific hours, and
Aug 27 finished at 5 of 14 (one before the fix below landed mid-afternoon,
four after). The evidence is public (the Actions run list and the CSV
itself). This is a scheduling failure external to the instrument; the
data that exists is untouched and unaffected.

### Rule application (no discretion exercised)

Under the pre-registered 12-of-14 daytime rule, Aug 26 and Aug 27 DROP.
Aug 25 held at exactly 12 of 14. Floor week 2 (Aug 25-27) is therefore
not a clean week. Appendix Q defined the floor unit as all pairwise
combinations of clean Tue-Thu weeks; with week 2 unclean, the floor
reduces to the week 1 x week 3 pair (Aug 18-20 x Sept 1-3), provided
week 3 is clean. Nothing about this paragraph is a judgment call; it is
the frozen rule applied to what happened.

### Instrumentation fix (reliability only, data definition unchanged)

Commit fc6a9ae in the public logger repo (its own history is the
timestamp, Aug 27 2026): the workflow now carries three cron entries per
hour (minutes 7, 24, 41) as redundancy against scheduler starvation, and
the script gained an hour guard that exits before touching the API when
the current UTC hour already has rows. A third, fully external layer
runs outside GitHub's scheduler: an hourly scheduled task on the
maintainer's machine triggers the same workflow through the
manual-dispatch API. The data definition is unchanged under all three
trigger paths: at most one row set per UTC hour, whichever trigger fires
first.

The fix was verified in production the same day: a manual dispatch
logged 12 of 12 pairs, and a second dispatch minutes later exited at the
guard. The redundancy also proved immediately necessary: in the 15
completed hours between the fix and this addendum the added cron slots
never fired (starvation ongoing), and every one of those hours was
captured exactly once, all through the dispatch path.

This changes sampling RELIABILITY, not sampling DEFINITION, and it
predates every floor computation and all closure-period data. Weeks
before and after the fix remain comparable because the per-hour
semantics are identical; the fix only raises the probability that an
hour exists.

### Contingency, registered now as a decision tree (frozen rules untouched)

Appendix Q defined the floor as all pairwise combinations of clean weeks
precisely because one pair is not a floor; losing week 2 recreates that
single-pair situation. The only pre-closure Tue-Thu days remaining are
Sept 8-10, and frozen rule M.3.3 deliberately excludes them from
October's before pool (Labor Day week, Sept 7-11): the days after a
Monday holiday are not typical weekdays. That exclusion is NOT lifted;
October's before pool is unchanged. Instead, the fallback order is
registered now, before any of the relevant data exists:

1. If week 3 (Sept 1-3) is clean under the 12-of-14 rule, the floor is
   the week 1 x week 3 pair, reported explicitly as a single draw.
   Pairs involving Sept 8-10 are additionally computed and printed
   under Appendix Q's existing DIAGNOSTIC label: they never govern
   wording.
2. If week 3 is also lost to an outage, the floor falls back to
   week 1 x Sept 8-10 (provided Sept 8-10 passes the same 12-of-14
   rule), the only pair that exists, with the Labor-Day-week caveat
   printed beside every use. A post-holiday week is expected to be
   noisier than a typical week, which can only push the measured floor
   UP and October's wording toward the more cautious tier: the fallback
   fails conservative.
3. If no pair exists at all, October reports direction and rank with no
   floor-calibrated wording tier, and says so plainly.

### Consequence for the scoring timeline

The floor run stays at ~Sept 4, on the clean weeks available then
(week 1 x week 3 at most). Any use of Sept 8-10 (diagnostic or fallback)
lands as a second dated computation after Sept 10 and before any closure
data is scored. Both computations publish; neither replaces the other
silently.
