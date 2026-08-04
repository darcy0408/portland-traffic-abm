# Demand exit — what a day-scale run needs that no built phase provides

## The problem, as measured (not hypothesized)

Phase A2 (Orca array 117428, Aug 2, readout `src/day_readout.py`) established
this with the arithmetic in front of it:

- All four 24-hour metro arms end the day in gridlock. The profiled arms freeze
  at EXACTLY 9,591.0 and 13,455.0 stuck vehicle-hours, held to one decimal for
  the last three-to-six hours — only possible if an integer number of cars is
  below 5 km/h for every second of every hour. Total deadlock.
- At hour 23 the PORTAL curve asks for 2,876 active vehicles. The profiled base
  arm holds 9,591 (3.3x) and the realism arm 13,455 (4.7x).
- Mechanism: `profile_park_down` and the park branch in `step_vehicles` can only
  shed a vehicle when it REACHES ITS DESTINATION. Gridlock stops completions, so
  the fleet cannot ebb. The congestion the profile exists to relieve is what
  disables the relief.

So the honest statement is not "the demand profile did not work". It is that
the kernel gives a vehicle exactly TWO ways to leave the network — complete its
trip and respawn, or complete its trip and park — and both route through
completion. When completion stops, nothing leaves. Phases A (demand entry), B
(intersection mechanics) and C (calibration) all control how cars ENTER or MOVE.
None gives a trapped car a way OUT. That is a structural gap, not a tuning
failure, and it is why A2 could not be fixed by any parameter.

## The three mechanisms, and why they are not interchangeable

A real driver facing a jam has three distinct responses. They act on different
quantities and a model needs them separated, because conflating them is how a
model gets "fixed" by accident.

- **C1 — en-route rerouting.** The driver stays in the system and changes PATH.
  Total demand is conserved; only its spatial distribution moves. This is what
  navigation apps do and it is standard in dynamic traffic assignment.
- **C2 — trip abandonment.** The driver gives up and leaves the network short of
  the destination (parks, or the trip is curtailed). Demand is REMOVED.
- **C3 — departure suppression / latent demand.** The trip is never made when
  the network is already bad. Demand never ENTERS.

## Build order, and the reason for it

**C1 first, and possibly C1 only.** Three reasons, in order of weight:

1. **It is the least fudge-like.** C2 and C3 both make the model's own failure
   metric better by deleting the vehicles being measured. A reviewer is entitled
   to ask whether a mechanism was added to stop the model breaking, and for C2
   and C3 the honest answer would be uncomfortable. C1 conserves total demand
   and changes only where it goes, so it cannot flatter the stuck-time number by
   construction — if stuck time falls under C1, it fell because cars moved.
2. **It is the strongest falsifiable test of what the A2 freeze actually is.**
   If rerouting alone clears the freeze, the gridlock was a ROUTING artifact:
   every car queued for the same blocked path because routes were planned once,
   at spawn, against free-flow travel times and never revised. If the freeze
   SURVIVES rerouting, it is true spillback deadlock — a cycle where every exit
   is itself blocked — and that is a much stronger and more interesting claim,
   which then genuinely motivates C2/C3. Either outcome is publishable; the
   current state (no exit at all) can distinguish neither.
3. **It is the one that pays off outside A2.** Every closure result to date
   reroutes vehicles only at SPAWN, against a graph with edges removed. Drivers
   already en route when a freeway closes do not react at all. En-route
   rerouting makes the closure response dynamic, which is squarely the
   "what can the ABM do that Rao's static model cannot" list Christof asked for
   (memory `christof-jul27-contribution-list-ask`), and it strengthens the
   I-205/I-5 closure work that is paper 1's spine.

C2 and C3 stay UNBUILT until C1 has run. Writing them now would let the eventual
day-scale result be produced by the mechanism that removes cars, which is
exactly the confound to avoid.

## C1 design

Flag `REROUTE_ENABLED` (default False; every committed number reproduces).

**Trigger.** A vehicle that has been continuously below `config.STUCK_SPEED_KMH`
for `REROUTE_STUCK_S` seconds is a reroute candidate. Reusing the existing stuck
threshold matters: the trigger is then the SAME condition the A2 measurement
counts, so "cars that were stuck" and "cars that reroute" cannot drift apart.

**Action.** Recompute the shortest path from the node the vehicle is currently
heading toward to its unchanged destination, and splice it onto the route behind
the current edge. The vehicle keeps its id, destination, emission class, IDM
parameters and position. No U-turn: the kernel has no mechanism for one, and
inventing one here would be a second unreviewed mechanism riding along.

**Weights — the part that must not be invented.** Rerouting on the same
free-flow `travel_time_s` the spawn used would send the car down the same
blocked path, so the weight has to see congestion. Link cost is free-flow time
plus **deterministic queueing delay**: `t = travel_time_s + n_cars * IDM_T /
lanes`, i.e. how long the queue ahead takes to discharge at saturation headway.
This introduces NO new constant — the saturation headway IS `config.IDM_T`, the
same time gap the car-following model already enforces, so the router's estimate
and the kernel's own physics cannot disagree about how fast a queue drains.

> **Rejected: the BPR function.** The first draft used the Bureau of Public
> Roads volume-delay curve, t = t0(1 + 0.15(v/c)^4), on the grounds that its
> constants are famously a-priori. That was a category error and the gate caught
> it. BPR's v/c is an **hourly flow** ratio from static assignment; applying it
> to instantaneous queue occupancy is not the same quantity. Measured: at 90%
> jam occupancy BPR returns a **1.10x** penalty, so a fully blocked link still
> looks essentially free and no driver ever diverts. Queueing delay charges the
> same link ~3.7x. Recorded here because "the constants are published" is not by
> itself a reason a function is the right one.

**Throttle.** `REROUTE_MAX_PER_STEP` caps how many vehicles re-plan per step,
longest-stuck first, ties broken by vehicle id (deterministic). This is a
COMPUTE budget, not physics, and must be labeled as such wherever it is
reported: in the A2 freeze essentially every vehicle is stuck and would qualify,
so an uncapped implementation would call Dijkstra ~13,000 times per step.
`REROUTE_COOLDOWN_S` stops one vehicle re-planning every step.

**Refusals, per the turn-pocket/green-wave precedent.** A negative or zero
trigger time, a cap below 1, or a cooldown shorter than the step are refused
loudly rather than silently degraded.

**Inertness.** The reroute pass consumes NO RNG draws at all (the choice is
deterministic given state), so flag-off must be bitwise identical INCLUDING the
final RNG state, and `src/kernel_regression.py` must stay bit-identical.

## Gates (src/reroute_scenarios.py)

- **A. Inertness.** Flag off is bitwise the base model including final RNG state,
  over a run with real stuck vehicles so the test is not vacuous.
- **B. It actually reroutes around a blockage.** Hand-built diamond: one short
  fast path and one long slow path. Jam the short one; a stuck car must switch to
  the long one, and its new route must be a valid edge chain from its current
  node to its ORIGINAL destination.
- **C. Trigger arithmetic by hand.** A car stuck for exactly `REROUTE_STUCK_S`-1
  does not reroute and at `REROUTE_STUCK_S` does; the cooldown blocks an
  immediate second re-plan; the cap admits exactly N and the longest-stuck ones.
- **D. Destination is never changed** and no vehicle is ever removed — the
  active fleet count is invariant across the pass. This is what separates C1
  from C2 and it must be enforced by a test, not by intention.
- **E. No path available** (destination unreachable once congestion weights
  apply) leaves the vehicle exactly as it was rather than raising or stranding it.
- **F. Refusals** all fire.

## What C1's experiment answers

Re-run the A2 profiled pair with `REROUTE_ENABLED` on, same seed, same graph,
same 86,400 steps, new RUN_NAMEs. Read with `src/day_readout.py`, which already
computes the quota-aware verdict. The question: does the evening still freeze?

- Freeze clears -> the A2 gridlock was a routing artifact of once-planned paths.
- Freeze persists -> true spillback deadlock; C2/C3 become motivated, and the
  finding "rerouting alone cannot clear it" is itself the result.

Cost must be MEASURED before any 24-hour submission: time one simulated hour
locally with the flag on and off and record the ratio here, the way the SLURM
resources for B1xB3 and F6 were measured rather than guessed.

COST MEASURED (Aug 2, corridor graph, 1,500 vehicles, 1,800 steps, seed 42,
each arm in its OWN process so first-run setup caching cannot skew it -- a
first attempt that reused one process reported the flag-on arm as 3x FASTER,
which was pure cache artifact):

| arm | wall | stuck veh-h | re-plans |
|-----|------|-------------|----------|
| REROUTE_ENABLED=False | 10.3 s | 490.3 | -- |
| REROUTE_ENABLED=True  | 13.4 s | 369.5 | 2,903 (0 found no path) |

So C1 costs about **+30% wall time** at a cap of 20 re-plans/step. Budget metro
SLURM time accordingly: the ablation's 1:01-1:56 per metro hour implies roughly
1:20-2:30 with C1 on, still inside a 4 h request.

The 24.6% stuck-time drop in that table is SUGGESTIVE ONLY and must not be
quoted as a result: one seed, corridor scale, half a simulated hour, and the
corridor is exactly the scale the Jul 28 diagnosis declared exhausted. Its only
legitimate use here is as proof the mechanism fires often enough (2,903
re-plans) that the cost measurement is meaningful. The real test is the A2
profiled pair at metro scale.

## C1 STATUS (Aug 2)

MECHANISM BUILT AND GATED, off by default; no experiment run, and no committed
or cited number moves. Branch `experiment/demand-exit`, worktree
`C:\dev\pta-exit`, commit `52c6cfe`.

- `config.REROUTE_ENABLED` plus `REROUTE_STUCK_S` (120 s), `REROUTE_COOLDOWN_S`
  (300 s) and `REROUTE_MAX_PER_STEP` (20, a COMPUTE budget and labeled as one).
- `generate.build_reroute_context` / `_reroute_pass`, wired into
  `step_vehicles` as pass 0c (after the pocket pass, before accelerations) and
  into `run_simulation`. The continuously-stuck timer `veh["stuck_s"]` is only
  tracked when the flag is on, so flag-off neither pays for it nor carries the
  key.
- Gates `src/reroute_scenarios.py` 6/6; all twelve prior suites green;
  `kernel_regression.py` bit-identical.

WEAKEST LINK, state it with any C1 result: `REROUTE_STUCK_S = 120 s` is the
softest constant in the phase. Unlike IDM_T (kernel physics) or the NHTS shares
(a published table), it is a judgement about driver patience with no direct
source. It is NOT fit to the held-out counts, and it deserves a sensitivity
sweep before any number leaves this branch.

TWO KNOWN LIMITATIONS of the mechanism as built:
- The re-plan starts from the node the car is HEADING TOWARD, so a car already
  committed to the blocked link cannot divert -- correct (no U-turn), but it
  means C1's relief is bounded by how many cars are still upstream of a fork
  when they lose patience. Verified as real behavior in gate B, not a bug.
- Every driver re-plans on perfect, instantaneous knowledge of current
  occupancy network-wide. That is the optimistic end of the information
  spectrum; real drivers have partial information. So C1 measures an UPPER
  BOUND on what rerouting can relieve, the same way the merged-osmid rule made
  B1 an upper bound.

## C1 HOUR RESULT (Aug 3) — band NOT wrecked; and a throughput finding

SLURM array 117852, 16/16 COMPLETED, read with `--readout --deep`. Paired
against the Jul 29 `metrocal_{base,realism}_n16500_s*` controls on the 8 shared
seeds. Provenance checked on all 32 runs: each parquet's NOx total matches its
own summary to under 1 g, so no pair can be a mis-join (the `_network_row`
refusal fires if it ever is).

**The gate question passes.** Busiest Powell, real ODOT band 1,400-1,745 veh/hr:

| arm | control | C1 | paired delta | in band per seed |
|-----|---------|-----|--------------|------------------|
| realism | 1,404 +/- 42 | **1,439 +/- 46** | +34 +/- 14, 8/8 up | control 4/8 -> C1 6/8 |
| base | 884 +/- 41 | 979 +/- 29 | +95 +/- 32, 8/8 up | 0/8 -> 0/8 |

Rerouting does not push the realism arm out of band; per-seed membership
improves. **The day result will therefore be interpretable.**

**The hour arm also carries more than the regression check it was designed as.**
Fleet vehicle-seconds are identical across arms to the digit (59,400,000 =
16,500 x 3,600), fixed by construction, so every line below is an EFFICIENCY
difference and not a demand difference. Realism arm, paired over 8 seeds:

| measure | change | seeds |
|---------|--------|-------|
| stuck veh-h | **-21.6%** | 0/8 up |
| distance veh-km | **+7.3%** | 8/8 up |
| mean speed | 39.4 -> 42.3 km/h | 8/8 up |
| edge traversals | +9.7% | 8/8 up |
| **network NOx** | **+0.42%** | 8/8 up |
| NOx per veh-km | **-6.4%** | 0/8 up |
| edges gaining / losing traffic | 28,930 / 2,057 | -- |

So the same fleet travels about 7% further for about 0.4% more NOx. The obvious
confound -- that more edge traversals is just detouring through short local
streets -- was checked and rejected: distance covered rises 8/8 seeds. That
traversals (+9.7%) outrun distance (+7.3%) says re-planned paths do use somewhat
shorter edges, but real ground covered is the dominant term.

The honest headline: **rerouting does not reduce emissions, it makes them more
efficient per km and REDISTRIBUTES them.** The 14:1 ratio of edges gaining to
edges losing traffic means this is not zero-sum diversion -- the network was
losing capacity to gridlock, and 1,358 edges carry traffic that carried none.

WHAT THIS RESULT DOES NOT SAY:

- **It is not the day question.** One hour at flat demand is a different regime
  from the A2 deadlock. Hour-scale relief does not imply the day freeze clears;
  that is array 117851's call and nothing here should be read as previewing it.
- **The base arm's numbers are not physical.** Base is out of band in control
  AND C1 (0/8), so its larger effects (+18.3% distance, +27.7% traversals,
  +57.9% Powell stuck, +26.4% Powell NOx) describe a model that does not
  reproduce real Powell flow. The pattern -- base dumps relief onto Powell
  because Powell has headroom it cannot otherwise fill, realism does not because
  it already sits at the real band -- is a mechanism HYPOTHESIS, not measured.
- **"More throughput" is not "more completed trips."** The fleet is fixed and
  trip completions are not in the summary schema; what is measured is that the
  same cars got further.
- Both bounds above still apply: no-U-turn, and perfect network-wide
  information, so this is an UPPER BOUND. `REROUTE_STUCK_S = 120 s` is still
  unswept.

## C1 DAY RESULT (Aug 3-4) — the freeze CLEARS on the realism stack; the base arm is relieved but does not recover

SLURM array 117851, BOTH tasks COMPLETED: task 1 (`realism_reroute`) Aug 3 16:07
Pacific, elapsed 23:52:43; task 0 (`base_reroute`) Aug 3 23:56 Pacific, elapsed
1d 07:41:35. Read with `day_readout.py --runs c1` and
`metro_c1_experiment.py --readout`, then a `_deep` network pass over the segment
parquets. The two `metrocal_dayprof_*_segments.parquet` controls were copied down
from Orca for that pass; `_network_row`'s provenance refusal passed on every run,
so no pair is a mis-join.

**The pre-registered verdict, on the measure it was pre-registered on.** Hour 23
network stuck vehicle-hours against the PORTAL hour-23 quota of 2,876 active
vehicles. The `recovers` test is `final/quota <= 3x overnight`, i.e. does the
network return to within 3x of its OWN free-flow reference from the quiet small
hours — not merely whether the total moved:

| arm | h23 stuck veh-h | x quota | overnight ref | verdict |
|-----|-----------------|---------|---------------|---------|
| ctrl/base (A2) | 9,591 | 3.33x | 0.06x | no recovery — gridlocked |
| ctrl/realism (A2) | 13,455 | 4.68x | 0.04x | no recovery — gridlocked |
| C1/base | 917.4 | 0.32x | 0.06x | no recovery (5.3x its own reference) |
| **C1/realism** | **133.7** | **0.05x** | 0.04x | **recovers** |

Whole day: realism 184,111 -> 28,151 veh-h (**-84.7%**), base 170,083 -> 82,595
(**-51.4%**). The heuristic deadlock flag fires on 6 hours of the realism control
(18-23) and 3 of the base control (21-23), and on **0** hours of EITHER
treatment. Peak stuck moves from h18 — i.e. never recovering — to h8 in both
treated arms, and falls monotonically after it.

**THE VERDICT ON THE PHASE IS TWO-PART, and the parts must not be collapsed.**
Rerouting eliminates the frozen deadlock in BOTH arms — no integral-valued hours
survive anywhere, and even the base arm sheds 90.4% of its hour-23 stuck time.
But only the realism stack RECOVERS to its own free-flow reference. The base arm
ends the day at 5.3x its overnight value, hugely better than the 55x of its
control and still not free-flowing. So A2's gridlock was substantially, but not
entirely, an artifact of routes planned once at spawn: in the base model
something beyond routing prevents a return to free flow.

The natural reading is that the arm which reproduces real Powell flow clears and
the arm which does not, does not — the base model is out of the ODOT band in
0/8 seeds, so its day behaviour was never physical. That reading is a HYPOTHESIS
about why the two differ, not a measurement, and it should be labelled as one.

C2 (trip abandonment) remains NOT motivated: it exists to answer true spillback
deadlock, and no deadlock survives in either arm.

One further change worth recording: the A2 CROSSOVER DISAPPEARS. In the controls
realism beats base for h0-h11 and is worse from h12 on; with rerouting on,
`realism never exceeds base` at any hour. The crossover was a property of the
freeze, not of the realism stack.

**It is not an artifact of the fleet parking itself down.** That was the obvious
failure mode, and it is the mechanism A2 identified: the hourly profile can only
shed vehicles when trips COMPLETE, so a run that completes trips ends with fewer
active vehicles and trivially less stuck time. C1 does park more — on-network
vehicle-hours 263,044 -> 229,138, -12.9%. But normalising stuck time by ACTUAL
on-network vehicle time rather than the nominal 16,500 x 24 h fleet-day:

| arm | on-network veh-h | stuck veh-h | stuck share |
|-----|------------------|-------------|-------------|
| ctrl/base | 244,398 | 170,083 | 69.6% |
| ctrl/realism | 263,044 | 184,111 | 70.0% |
| **C1/realism** | **229,138** | **28,151** | **12.3%** |

A 5.7x drop that survives the normalisation. The controls spend 70% of their
on-network time below stuck speed; C1 spends 12%.

**What the fleet does with the relief** (network totals from the parquets):

| measure | ctrl/realism | C1/realism | change |
|---------|--------------|------------|--------|
| distance veh-km | 4,469,108 | 11,051,278 | **+147.3%** |
| mean speed km/h | 16.99 | 48.23 | +183.9% |
| edge traversals | 16,840,715 | 43,337,570 | +157.3% |
| **network NOx** | **2,508,986 g** | **2,303,364 g** | **-8.20%** |
| NOx per veh-km | 0.56141 | 0.20843 | -62.9% |
| edges carrying traffic | 130,606 | 140,189 | +7.3% |
| edges gaining / losing traffic | 135,399 / 12 | | — |

The NOx sign is the OPPOSITE of the hour arm's (+0.42%), and the reason is
mechanical rather than contradictory: the deadlocked control burns NOx idling for
almost no distance. **The quotable form is "nearly the same NOx for two and a
half times the distance."** Do NOT lead with the -62.9% NOx-per-km figure — it is
arithmetically true but its denominator moved 147%, which flatters it. This also
settles the "fewer kilometres driven?" alternative explanation for the NOx drop:
ruled out, and in the opposite direction.

Note `edges gaining / losing = 135,399 / 12`. At day scale this is not the 14:1
redistribution the hour arm showed — essentially nothing loses traffic, because
the control is starved network-wide. Read it as the network unlocking, not as
diversion.

**Two corroborating provenance signals**, worth keeping because they are cheap
and they check the join independently of the NOx cross-check:

- Hours 0-3 are identical between control and treatment on network stuck
  vehicle-hours to the reported precision (delta +0.0); the first divergence is
  h4 at -4.6. Rerouting is correctly inert before congestion exists, and the pair
  is genuinely the same seed. This is NOT a bit-identity claim about
  trajectories — `kernel_regression.py` is what makes that claim.
- The control's Powell goes DEAD after h16 while C1's carries traffic through
  h23 (Powell 1,172.5 -> 2,980.0 veh-h). The control's quiet Powell is starvation
  by upstream gridlock, not free flow.

**Interpretation.** A2's day-scale gridlock was substantially an artifact of
routes planned once at spawn against free-flow times and never revised. This is
the freeze-CLEARS branch of the two outcomes this phase pre-registered, which
means **C2 (trip abandonment) is NOT motivated and should stay unbuilt.**

WHAT THIS RESULT DOES NOT SAY:

- **Seed 42 only**, inherited from the A2 controls, and so qualitative under the
  project's standing day-run caveat.
- **The base arm's day numbers are not physical** for the same reason its hour
  numbers are not: 0/8 seeds in the ODOT band, in control and treatment alike.
  Its failure to recover should not be over-read as a fact about traffic.
- The network totals below are the REALISM pair. The base pair's parquets are on
  disk but its network-wide view has not been read.
- Every effect size here is measured against a DEADLOCKED control, so it reads
  "deadlocks vs does not," not "improvement in a working model."
- Day-run `busiest_powell_veh_hr` (850 C1, 347 control) is a 24-HOUR AVERAGE
  (throughput / sim_hours), not the peak-hour metric. Do NOT read it against the
  ODOT band of 1,400-1,745; only the hour arm speaks to the band.
- Network mean speed of 48.23 km/h is at the high end of plausible for this
  graph and has not been sanity-checked against a free-flow expectation.
- Both bounds still apply: no-U-turn, and perfect network-wide information, so
  this is an UPPER BOUND on what rerouting can relieve.
- **`REROUTE_STUCK_S = 120 s` is still unswept, and this result makes the sweep
  MORE load-bearing, not less**: an 85% effect resting on an unsourced
  driver-patience constant is the exposed flank. Sweep harness:
  `src/metro_c1_sweep.py`.
