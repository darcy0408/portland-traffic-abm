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
