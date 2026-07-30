# Adversarial audit of Phase 1 + Phase 2 (Jul 23, from the main session)

Two independent adversarial auditors reviewed this branch at commit 1be9ad0
(before the Phase 3 increment). Verdict: no computational bug moves a number.
Flag-off inertness for BOTH phases was re-verified bitwise against main's actual
kernel (exact float equality, scenarios exercising leader, spillback,
entrance-hold, and red-light paths). The lanes results (11 vs 22 discharge,
2.00x, 209 multi-lane segments) were independently reproduced.

But several gates are weaker than advertised and one doc claim is false.
Apply fixes 1-3 BEFORE building more Phase 3 on top of these gates.

## Must fix

1. FALSE DOC CLAIM (Phase 2). drivers.py (~line 36), config.py (~line 237), and
   generate.py (~line 531) claim heterogeneity keeps traffic "bit-identical to
   the same-seed homogeneous run." That sentence is true for the FLEET layer it
   was copied from (fleet changes only emission chemistry) and false here:
   changed dynamics change finish times, which shift respawn timing, which
   reassigns trip draws. Proven by micro-run (routes identical at spawn,
   divergent after respawns). Correct claim: identical initial population and
   stream seeds; realized traffic then diverges because the dynamics differ,
   which is exactly what the experiment measures. Three doc edits, no code
   change. Do this before the branch is ever described to Christof.

2. VACUOUS GATE (Phase 1). lanes_scenarios.py line ~121 passes the literal
   constant True to _check for "nobody runs the red" instead of the computed
   `held` variable (which is printed but never asserted, and the 1-lane value
   is overwritten by the 2-lane iteration). The property holds today, but a
   regression letting cars run the red would still PASS. Assert `held` for
   each lane count.

3. GATE THAT CANNOT FAIL (Phase 1). lanes_scenarios.py lines ~112-114: the
   "two cars queue abreast" check requires the front two cars above pos 390,
   but _queued_vehicles places them at 398 and 391 initially, and under red the
   single-file queue is stationary at IDM equilibrium, so a completely broken
   lanes implementation passes. Fix: assert the gap between the front two cars
   is < 7 m (abreast), or both within ~1 m of 398.

## Should fix

4. DEMO CONFIG DRIFT. demos/watch_the_cars.py spawns config.N_VEHICLES, which
   is now metro-scale (16,500) while the cached graph is the 1.5 km corridor:
   running it today gridlocks 16,500 cars on Powell, against a docstring
   promising 500 vehicles / 30% through-traffic. Add a corridor config override
   at the top (the mixed_rerun.py pattern) or an explicit guard.

5. KEYWORD DISCIPLINE NOT HELD WHERE IT MATTERS. generate.py run_simulation
   (~line 849) passes `lanes` as the 16th POSITIONAL argument; every other call
   site uses lanes=. Phase 2 inserted driver_ctx immediately before lanes in
   the step_vehicles signature, which is exactly the silent-mis-binding hazard
   the keyword-only rule targets (it happened to be updated correctly this
   time). Make it lanes=lanes (and driver_ctx by keyword too).

6. INCONSISTENT s0 (Phase 2). The segment-entry hold (generate.py ~line 773)
   uses config.IDM_S0 while the accel call uses the car's drawn idm["s0"].
   Base main uses the same constant in both places, so per-car s0 is
   inconsistently applied. One-line fix (use idm["s0"] when present) or one
   doc line accepting it.

## Hygiene / notes (no action required, know about them)

7. Both equivalence gates compare the new kernel against itself (lanes: None vs
   all-ones; drivers: flag-off vs all-sigma-0), not against main, so a refactor
   bug hitting both arms equally would pass. The auditors closed this gap
   externally (bitwise-equal vs main's kernel), but consider pinning a
   known-good trajectory literal in the gates as regression armor.
8. _parse_lanes drops semicolon tags ("2; 3") to 1 instead of min (zero such
   tags in the current corridor graph; error direction conservative), ignores
   lanes:forward/backward, and int(float("inf")) would raise OverflowError
   (catches only ValueError). Not worth fixing unless the graph changes.
9. sigma=0 no-draw shortcut: one-knob-at-a-time sigma sweeps do NOT hold other
   vehicles' draws fixed (skipping a draw shifts stream alignment for later
   vehicles). Within one config all is deterministic; just never attribute
   per-vehicle deltas between different-sigma-config runs to the added knob
   alone. Document before running such sweeps.
10. The +3 driver stream inherits the known RNG-not-checkpointed limitation,
    plus a stale-checkpoint hazard if a checkpoint written with the flag in the
    other state is resumed (mixed population until respawn). Add the driver
    stream to the existing limitation list.
11. Gate B validates that the kernel realizes the drawn factors, not the
    sampling statistics (mean/sd/truncation); only the offline _demo prints
    those. Fine as designed; don't describe it as validating the distribution.

## What survived attack (for the record)

- Inertness both phases: bitwise vs main, held.
- RNG discipline: no driver draw on route retries; no +3 stream created when
  off; route/fleet/signal streams untouched; held.
- Three-rule N-lane generalization: queue ordering, fewer-than-N cases, per-car
  red-light braking all correct; the same-step by_edge staleness exists
  identically in base main (documented Jul 4 limitation), not newly introduced.
- Physical sanity: no degenerate IDM parameters at config sigmas (worst case at
  2-sigma truncation: a_max 1.05, T 1.05 s, s0 1.6 m; no division hazard).
- lane_discharge_anim.py is clean (real kernel, DT-correct).
