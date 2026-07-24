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
- Gate HARDENED Jul 23 (audit items 2-3, see `AUDIT_FINDINGS_JUL23.md`): the
  red-light check asserted the literal `True` instead of the computed value, and
  the "two cars abreast" check tested a threshold the cars already satisfied at
  setup, so both passed no matter what the kernel did. Now the red check asserts
  the measured crossing count for EACH lane count, and the abreast check asserts
  the front-two longitudinal gap is < 1 m with 2 lanes AND ~7 m (the L+s0
  equilibrium) single file. Verified to FAIL against a sabotaged kernel that
  ignores the lane counts (gap 7.00 m both ways) and against an injected
  red-light violation.

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
- Gates green: `python src/driver_scenarios.py` → 3/3.
  A (inertness) all-sigma-0 draw equals the config defaults and trajectories are
  bitwise identical to the base kernel; B (dispersion) 12 free drivers each settle
  to v0×factor to 1e-9, speed variance 2.44 (m/s)², fastest/slowest separate 1850 m
  vs 1896 m hand-predicted (−2.4%), and zero-sigma leaves no spread at all;
  C (own s0, added Jul 23 with audit item 6) the segment-entry hold uses the car's
  OWN jam distance, matching its acceleration: with a blocker 6.8 m into the next
  segment, the default driver (threshold 5+2.0 = 7.0 m) is held and a
  short-headway driver (s0 1.6, threshold 6.6 m) enters, while the flag-off path
  is unchanged. Verified to FAIL against the pre-fix kernel.
- Doc claim CORRECTED Jul 23 (audit item 1): `drivers.py`, `config.py` and
  `generate.py` had claimed heterogeneity leaves traffic "bit-identical to the
  same-seed homogeneous run". That is true of `fleet.py` (emission chemistry only)
  and FALSE here — changed dynamics change finish times, which shift respawn
  timing, which reassigns trip draws. The separate stream buys an identical
  INITIAL population and no consumed trip/route/fleet draw; the realized traffic
  then diverges, and that divergence is the effect being measured.
- Base gates unaffected (flag off default): scenarios.py 4/4, lanes_scenarios.py 2/2.
- Remaining (needs a deliberate run, not built yet): the speed-VARIANCE-per-segment
  readout on a full run — CNOSSOS noise is nonlinear in speed, so variance should
  move the noise surface even at equal means. This is the payoff figure; it needs
  an authoritative seeded run (flag on) and belongs behind a run decision.

## Phase 3 — MOBIL lane changing (IN PROGRESS on this branch)
True lane identity per car (replacing Phase 1's free-reshuffle virtual lanes),
IDM+MOBIL (Kesting/Treiber/Helbing 2007): incentive criterion (accel gain vs
politeness x imposed braking) + safety criterion (b_safe). Passing emerges. Three
lane modes now coexist, mutually exclusive, the other two unchanged: base (single
file) / `LANES_ENABLED` virtual lanes / `MOBIL_ENABLED` explicit lanes.

### Increment 1 — DONE: the MOBIL decision core (isolated, gated)
- `config.py`: `MOBIL_ENABLED` (default False), `MOBIL_POLITENESS` 0.2,
  `MOBIL_A_THRESHOLD` 0.2 m/s^2, `MOBIL_B_SAFE` 4.0 m/s^2 (a-priori literature
  values, not tuned to held-out counts).
- `src/mobil.py`: the PURE decision. `wants_change(self_before, self_after,
  old_pair, new_pair, params) -> (change, margin)`. Safety = new follower brakes
  no harder than b_safe; incentive = own IDM-accel gain - p*(followers' braking
  loss) > a_thr. Every acceleration is a real `generate.idm_acceleration`; this
  module recomputes NO physics (the caller passes the six accels in), so the
  car-following kernel stays single-sourced. Absent follower = None (0 loss;
  missing new follower => trivially safe). Returns the margin so the caller can
  pick the best of several candidate lanes.
- `src/mobil_scenarios.py`: gate, all 4 PASS. Fast car stuck behind a crawler with
  a clear lane changes (margin +8.2); an unsafe cut-in is vetoed (new follower
  -inf); an already-free car stays (margin 0); and politeness works — the same
  safe change is taken when selfish (p=0, margin +0.89) and declined when polite
  (p=0.5, margin -0.22). Numbers match hand-calculation.

### Increment 2 — NEXT: wire explicit lane identity into step_vehicles
Data model (design, not yet built):
- Each vehicle carries `veh["lane"]` = its integer lane index on its CURRENT
  segment (0 = rightmost). On crossing into a new segment, clamp the index to the
  new segment's lane count (default keep index; if the new road is narrower, drop
  to the highest lane that exists). Per-segment lane counts reuse Phase 1's
  `_parse_lanes` / `n_lanes` (OSM `lanes` tag) — MOBIL just needs the counts.
- Neighbour finding per step: within a segment, partition cars by `lane`; within a
  lane, sort by `pos` -> each car's same-lane leader/follower. For a candidate
  target lane, the leader is the nearest car ahead IN THAT LANE and the new
  follower the nearest behind. Car-following (the accel + move in step_vehicles)
  then runs WITHIN lanes: leader = same-lane car ahead, not queue-rank-mod-N.
- Lane-change pass, BEFORE the accel/move pass, from the SAME frozen snapshot the
  IDM already uses (honest simultaneous update): for each car on a >1-lane MOBIL
  segment, compute the six IDM accels for each adjacent candidate lane, call
  `mobil.wants_change`, and if the best safe candidate clears the threshold, set
  `veh["lane"]`. At most one lane change per car per step. Residual same-gap
  conflicts (two cars eyeing one gap) are rare and the next step's IDM brakes any
  overlap; document this as a known simplification (a full model would add a
  gap-acceptance tie-break). Optionally evaluate MOBIL every K steps, not every
  step, for speed — a documented knob.
- Keep it a SEPARATE branch in step_vehicles gated on `MOBIL_ENABLED`, so the base
  and virtual-lane (`lanes=...`) paths stay byte-for-byte unchanged and their
  gates (scenarios.py 4/4, lanes_scenarios.py 2/2) stay green. MOBIL and virtual
  lanes are mutually exclusive; refuse both flags on at once.
Gates to add (`src/mobil_network_scenarios.py` or extend the existing gate):
- Fast driver stuck behind a slow one on a 2-lane segment OVERTAKES (ends ahead),
  and on a 1-lane segment CANNOT (ends behind, blocked). The headline emergence.
- Inertness: `MOBIL_ENABLED` on with every segment 1 lane == the base kernel,
  bitwise (a car with nowhere to change behaves exactly single-file).
- The Phase 1 virtual-lane mode still passes its own gate unchanged (the
  frictionless virtual lane is the capacity upper bound; MOBIL's realistic
  friction sits below it — that contrast is a result worth plotting).

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
