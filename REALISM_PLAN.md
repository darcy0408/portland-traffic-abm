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
- Payoff readout DONE Jul 24 — see "Realism payoff readout" below. Headline:
  heterogeneity adds ~+1.0 km/h to the median per-segment speed SD and a modest
  +0.06 dB(A) to the median mean-vs-distribution noise delta; the LARGER finding
  is that the base run's own congestion-induced speed variance already shifts
  CNOSSOS by up to ~6.5 dB(A) on slow congested segments, an ABM-only signal no
  static mean-speed model carries.

## Phase 3 — MOBIL lane changing (DONE on this branch)
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

### Increment 2 — DONE: explicit lane identity wired into step_vehicles
Built as designed below, with the numbers it produced:
- `build_mobil_context(G)` returns None when `MOBIL_ENABLED` is off, and REFUSES
  to run alongside `LANES_ENABLED` (the two are different models of the same
  thing; running both would double-count lanes). `step_vehicles` refuses
  `lanes=` and `mobil_ctx=` together for the same reason. `_parse_lanes` now
  reads the OSM tag for EITHER flag — same physical fact, different use.
- Per-lane neighbour finding is shared by all three modes through
  `_lane_queues`: virtual lanes are `group[r::N]` (so the queue successor is
  exactly the old follow-N-ahead leader, `group[i+N]`), explicit lanes partition
  on `veh["lane"]`, and N = 1 returns the single group unsliced. Base and Phase 1
  behavior is therefore unchanged by construction, not just by intent.
- Gates green: `python src/mobil_network_scenarios.py` → 3/3.
  A (overtaking EMERGES) a 1.35x driver released 30 m behind a 0.55x driver on a
  6 km segment ends 4,367 m along in lane 1 with 2 lanes — a 2,525 m lead — and
  1,824 m along, 19 m BEHIND, when the same run has 1 lane. Nothing says
  "overtake": MOBIL finds the lane safe and worth taking and the IDM does the
  rest. B (inertness) MOBIL on with every segment 1 lane is bitwise identical to
  the feature off, while the same cars on 2 lanes do diverge (so the check can
  fail). C (clamping) a car in lane 2 entering a 1-lane segment lands in lane 0.
- Base gates unaffected: scenarios 4/4, lanes 2/2, driver 3/3, mobil 4/4, and the
  pinned kernel regression (`kernel_regression.py`) is bit-identical — that last
  one is what actually proves the neighbour-finding refactor changed no physics,
  since the equivalence gates only compare the kernel against itself.
- End-to-end smoke on the cached 1.5 km corridor (400 vehicles, 300 steps, flag
  on, no data written): 209 of 2,838 segments have >1 lane, 1,154 lane changes,
  59 of 400 cars end in lane 1, zero cars in a lane their segment lacks, and no
  measurable slowdown of the flag-off path (1.54 s vs 1.56 s for 400x600).
- Known simplifications, all documented at the code: MOBIL's six accelerations
  use in-lane neighbours only (no red-light or spillback term — those are shared
  by every lane of a segment and largely cancel in a lane COMPARISON; where they
  do not, the effect is cars filling the shorter queue at a red, which is what
  drivers do); two cars may pick the same gap in one step and the next step's IDM
  brakes the overlap; and a car crossing an intersection keeps its lane index
  (clamped) rather than choosing the emptiest lane.

Original design (as built):
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

## Realism payoff readout (DONE Jul 24 — the deferred run decision, executed)

First full authoritative runs with any realism flag on. Four sequential seeded
corridor runs (seed 42, 1.5 km cached graph, 500 vehicles, 3600 steps,
powell_through demand settings overridden visibly in `src/realism_runs.py`;
the checked-in config stays metro20k). New opt-in per-segment speed moments
(v_sum/v2_sum) in `generate.py` feed the readout; all six gates plus the
pinned kernel regression re-verified green/bit-identical after that edit.
Analysis is `src/realism_readout.py` (reads the four parquets, never re-runs).

| run             | flags         | mean km/h | throughput | med speed SD |
|-----------------|---------------|-----------|------------|--------------|
| realism_base    | none          | 28.35     | 169,697    | 4.9 km/h     |
| realism_drivers | heterogeneity | 27.61     | 165,313    | 5.9 km/h     |
| realism_mobil   | MOBIL         | 30.15     | 180,461    | 4.9 km/h     |
| realism_both    | both          | 29.54     | 176,784    | 6.0 km/h     |

- Phase 2 payoff: evaluating CNOSSOS at the mean speed vs a 3-point
  Gauss-Hermite quadrature over N(mean, var) understates noise by median
  +0.11 dB(A) in the BASE run already (signals/queues make speed variance even
  with identical drivers), up to ~6.5 dB(A) on slow congested segments
  (~20 km/h mean, 14-20 km/h SD: Holgate, Gladstone, Milwaukie). Heterogeneity
  adds +0.06 dB(A) median on top (690 -> 750 segments over 0.5 dB). The honest
  headline is therefore CONGESTION-induced variance — an ABM-only signal — with
  driver heterogeneity a modest amplifier at these a-priori sigmas.
- Phase 3 payoff: MOBIL raises total throughput +6.34% (+10,764 veh/hr),
  gains concentrated on Powell's multi-lane segments (+54 to +64 veh/hr each;
  top segment 987 -> 1,049). ZERO segments lose throughput (1,663 gain, 1,175
  tie — verified independently); single-lane segments gain via network effects
  (faster trips -> more respawns). Per-segment rank order essentially unmoved
  (Spearman 0.9989), consistent with the Phase 1 finding that capacity does not
  limit validation. MOBIL's +6.3% sits well below the frictionless virtual-lane
  upper bound (Phase 1 measured 2.0x discharge), the predicted contrast.
- Interaction (first measurement): throughput is almost perfectly additive
  (r=0.9999, median |actual-predicted| = 0.000 veh/hr; network total off by
  +707 of 176k). Mean speed interacts mildly (r=0.984, median 0.24 km/h): the
  flags couple through speed dynamics, not volumes.
- Caveats (also printed by the script): corridor scale only; a-priori
  uncalibrated sigmas/MOBIL parameters; two-moment Gaussian approximation in
  the noise quadrature; heterogeneity's effect is always the DELTA over the
  base run's own spread.

## Phase 4 — Signal timing

### Increment 1 — DONE Jul 24: Webster decision core (isolated, gated)
- `src/webster.py`: pure two-phase Webster (1958): y_i from the critical
  approach (scalar or iterable, max governs), C0 = (1.5L+5)/(1-Y) clamped to
  [30, 120] s, green split proportional to y with a 7 s min-green floor;
  degenerate cases Y=0 -> (min cycle, 0.5) and Y>=1 -> max cycle. Returned
  split = fraction of the CYCLE the EW phase holds (sums to 1 with NS,
  directly comparable to SIGNAL_GREEN_SPLIT). No config/generate imports —
  same purity discipline as mobil.py increment 1.
- `config.py`: WEBSTER_ENABLED (default False) + SAT_FLOW 1900, LOST_TIME 4 s,
  CYCLE_MIN/MAX 30/120 s, MIN_GREEN 7 s — standard a-priori values, not tuned
  to held-out counts.
- Gate `src/webster_scenarios.py` 5/5, expectations derived independently with
  exact Fractions: symmetric 400/400 -> split exactly 0.5, C0 29.36 s clamps
  to 30; asymmetric 700/300 -> split 2117/3230 ≈ 0.6554 asserted to 1e-9;
  oversaturated -> 120 s fallback; min-green floor raises a 20 veh/h approach
  to exactly 7 s; iterable [300,700] bitwise-equals scalar 700.

### Increment 2 — NEXT: wire Webster into the simulation
- Approach volumes per signalized intersection from the modeled flows (a
  measurement pass or a prior run's throughput), feeding cycle_and_split per
  intersection in prepare_signals when WEBSTER_ENABLED.
- Yellow + all-red clearance intervals.
- Green-wave offsets along Powell (progression at the corridor speed limit).
- Portland runs SCATS (adaptive, no public plans) — PBOT signal timing cards
  are public-records-requestable if we ever want ground truth; Webster is the
  standard research fallback.
- Gate: single intersection with asymmetric demand → Webster gives the heavy
  approach more green (through the REAL kernel this time); inertness — flag
  off bitwise unchanged; corridor demo shows a platoon riding the green wave.

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
