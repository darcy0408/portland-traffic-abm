# Traffic-realism experiment plan (branch `experiment/traffic-realism`)

Side project, deliberately OUT of the chapter (draft due Jul 26). Lives in the
`C:\dev\pta-realism` worktree; never merged to `main` without an explicit
decision. Goal: make the traffic model itself more realistic — the three named
limitations (single lane, uniform signals, homogeneous drivers) become
switchable, testable features, plus whatever else earns its keep.

Ground rules (inherited from the repo spec):
- Every phase gated by hand-predictable scenario checks through the REAL kernel
  (the `scenarios.py` / `lanes_scenarios.py` discipline).
- Every feature OFF by default and provably inert when off (bitwise equivalence
  with the base model), so the citable main-line numbers never move.
- Seeded and reproducible; parameters live in config.py.

## Phase 1 — Multi-lane (DONE on this branch)
Revived the parked virtual-lane experiment (old worktree-lanes-experiment,
commits 8cb63ed + e4c0781, cherry-picked across the Jul 19 history rewrite) and
ported it to the current `step_vehicles` signature (main added `fleet_ctx`;
`lanes` is now keyword-only at every call site to avoid positional aliasing).
- `LANES_ENABLED` in config.py (default False), per-edge counts from the OSM
  `lanes` tag: list→min (bottleneck), two-way→halved, clamp [1, LANES_MAX].
- Gates green: `python src/lanes_scenarios.py` → equivalence bitwise PASS,
  discharge 2.00x with 2 lanes (22 vs 11 cars/30 s green), nobody runs the red.
- Demos in `demos/`.

## Phase 2 — Heterogeneous drivers (DONE on this branch)
Per-vehicle IDM parameters drawn from truncated Gaussians (Treiber & Kesting's
recommended approach): multiplier on v0 (desired-speed factor), plus draws for
T, a_max, b_comf, s0. Own seeded RNG stream (same discipline as fleet draws so
route/fleet streams stay untouched). `DRIVER_HETEROGENEITY` flag, default off.
- `src/drivers.py`: `sample()` draws each parameter as a factor N(1, sigma)
  truncated to [1-2σ, 1+2σ] (clamped); sigma=0 returns exactly 1.0 with no draw
  consumed, so all-zero is provably inert. Sigmas live in config.py
  (`DRIVER_SIGMA_*`, default v0 0.12 / a,b,T 0.15 / s0 0.10).
- `src/generate.py`: `build_driver_context()` (own stream RANDOM_SEED + 3, beside
  +1 signals / +2 fleet), draw in `make_vehicle` AFTER route success (retries
  don't consume driver draws), applied in `step_vehicles` (per-vehicle v0_factor ×
  segment limit, and the car's own a_max/b_comf/T/s0). idm=None ⇒ byte-for-byte
  the base kernel.
- Gates green: `python src/driver_scenarios.py` →
  A (inertness) all-sigma-0 draw equals the config defaults and trajectories are
  bitwise identical to the base kernel; B (dispersion) 12 free drivers each settle
  to v0×factor to 1e-9, speed variance 2.44 (m/s)², fastest/slowest separate 1850 m
  vs 1896 m hand-predicted (−2.4%), and zero-sigma leaves no spread at all.
- Base gates unaffected (flag off default): scenarios.py 4/4, lanes_scenarios.py 2/2.
- Remaining (needs a deliberate run, not built yet): the speed-VARIANCE-per-segment
  readout on a full run — CNOSSOS noise is nonlinear in speed, so variance should
  move the noise surface even at equal means. This is the payoff figure; it needs
  an authoritative seeded run (flag on) and belongs behind a run decision.

## Phase 3 — MOBIL lane changing
True lane identity per car (replacing the free-reshuffle virtual lanes),
IDM+MOBIL (Kesting/Treiber/Helbing 2007): incentive criterion (accel gain vs
politeness x imposed braking) + safety criterion (b_safe). Passing emerges.
- Gate: fast driver stuck behind slow one — overtakes on 2 lanes, cannot on 1.
- Gate: virtual-lane mode remains available and unchanged (upper bound vs
  MOBIL's realistic friction is itself a result worth plotting).

## Phase 4 — Signal timing
- Webster's formula per intersection: cycle + green split from modeled approach
  volumes (replaces uniform 60 s / 50%).
- Yellow + all-red clearance intervals.
- Green-wave offsets along Powell (progression at the corridor speed limit).
- Portland runs SCATS (adaptive, no public plans) — PBOT signal timing cards
  are public-records-requestable if we ever want ground truth; Webster is the
  standard research fallback.
- Gate: single intersection with asymmetric demand → Webster gives the heavy
  approach more green; corridor demo shows a platoon riding the green wave.

## Phase 5 — Menu (pick per session)
- Truck/bus dynamics: fleet.py classes get length + accel envelopes (fleet
  already exists for emissions; extend to physics).
- TriMet dwell friction: buses stop in-lane at stops (GTFS stop locations).
- Gap acceptance for unprotected lefts; stop signs.
- Human Driver Model (Treiber/Kesting/Helbing 2006): reaction time + estimation
  errors on top of IDM.

## Why bother (not the paper, but not nothing)
- Single lane caps edges at ~1,070 veh/h vs Powell's observed 1,400–1,745
  directional peak — the base model structurally cannot reproduce peak volumes.
- Each phase quantifies one named limitation → sensitivity numbers that defend
  the simplified model ("lanes change segment volumes by X%") — future-paper /
  thesis material.
- Demo animations of the full corridor with lanes + heterogeneous drivers +
  green waves are presentation gold.
