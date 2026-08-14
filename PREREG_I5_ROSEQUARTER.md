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
