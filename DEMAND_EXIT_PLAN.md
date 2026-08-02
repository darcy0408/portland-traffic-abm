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
blocked path, so the weight has to see congestion. It uses the standard Bureau
of Public Roads volume-delay function, t = t0 * (1 + a(v/c)^b) with the
universally cited a = 0.15, b = 4. Those are a-priori published constants, not
fitted. Occupancy v/c is computed from state the step already has (cars per
edge from `by_edge`) over a jam capacity derived from existing config
(`VEHICLE_LENGTH_M`, `IDM_S0`, lane counts) — so C1 adds no new capacity knob.

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
