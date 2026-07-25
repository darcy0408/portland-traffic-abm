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

### Increment 2a — DONE: per-node Webster timing + clearance wired into the kernel
Built as specced below, minus green-wave coordination (deferred to 2b). The flag
stays off by default; the committed spec is still the uniform signal.
- Flows source (the design fork, decided with the user): a MEASUREMENT PRE-PASS.
  `_measure_approach_flows(G, ...)` runs a short seeded warmup with the uniform
  base signals on its OWN RNG stream (`RANDOM_SEED + 11`), and the realized
  approach crossings (the existing `segment_throughput`, one count per traversal
  into the downstream node) over the LAST HALF of the window become veh/h. Its own
  stream means the authoritative run that follows is byte-for-byte the same
  population it would be with the flag off — only the signal timing differs.
  `config.WEBSTER_WARMUP_STEPS` (default 1200) sets the window.
- `build_webster_plans(G, signal_nodes, edge_phase, flows)` groups each signal
  node's incoming edges by phase (0 = EW, 1 = NS), takes the CRITICAL (max)
  approach flow per phase and that approach's lane count (edge `n_lanes`, = 1 in
  the base single-lane model), and calls `webster.cycle_and_split` per node →
  per-node cycle and EW split. `prepare_signals(G, flows=None)` fills
  `node_cycle` / `node_split` (both None when off), a `clearance` interval, and
  redraws each offset on the node's OWN cycle. `run_simulation` runs the pre-pass
  and passes the flows when `WEBSTER_ENABLED`.
- `is_green` gained a Webster branch: this node's own cycle/split, plus a
  yellow+all-red CLEARANCE at the end of each phase (neither phase green). The
  flag-off branch is the byte-for-byte original arithmetic — proven by the
  inertness gate (0 mismatches over an 8000-sample sweep) and the pinned
  kernel_regression (still bit-identical).
- `config.py`: `WEBSTER_YELLOW_S` 3.5, `WEBSTER_ALL_RED_S` 1.5 (display clearance,
  kept distinct from `WEBSTER_LOST_TIME_S`, the capacity parameter inside the
  cycle formula), `WEBSTER_WARMUP_STEPS` 1200 — all a-priori.
- Gate `src/webster_network_scenarios.py` → 3/3, through the REAL kernel on a
  synthetic four-way intersection: A) asymmetric demand (EW 1000 / NS 150 veh/h)
  → EW split 0.745 and 16 EW vs 6 NS cars clear C, while the uniform 50/50 control
  clears 16 vs 16 (the imbalance is Webster's, not the geometry); B) inertness —
  is_green's flag-off branch equals the original formula bitwise and a base queue
  is deterministic, while a Webster plan on the starved NS approach diverges (so
  the gate can fail); C) clearance — both phases read red during each yellow+all-
  red interval, and a saturated approach clears strictly fewer cars with the
  clearance than without it (the lost green is real, not cosmetic).
- Base gates unaffected: scenarios 4/4, lanes 2/2, driver 3/3, mobil 4/4, mobil
  network 3/3, webster (decision) 5/5, kernel_regression bit-identical. End-to-end
  smoke on the cached 1.5 km corridor (250 veh, WEBSTER on, no data written):
  warmup measured 1062 approach flows, 21 OSM-tagged signals got plans, run
  completed clean. (At this low warmup demand every node clamped to the 30 s
  minimum cycle — honest, not a defect; full-scale demand spreads the cycles.)
- Simplifications documented at the code: single-lane critical-approach capacity
  when no lane flag is on; the display clearance need not equal Webster's internal
  lost time; offsets only decorrelate the grid (no coordination yet).

### Increment 2b — DONE: green-wave coordination along a named chain (gated, off by default)
- `config.py`: `WEBSTER_GREENWAVE_ENABLED` (default False, meaningless without
  `WEBSTER_ENABLED` and refused loudly if set without it — same refusal style as
  `build_mobil_context` refusing `LANES_ENABLED`+`MOBIL_ENABLED`),
  `WEBSTER_GREENWAVE_STREET` ("Powell" — case-insensitive substring match against
  OSM edge `name`, list-valued names handled element-wise),
  `WEBSTER_PROGRESSION_SPEED_KPH` (50 km/h / ~30 mph — the standard urban arterial
  speed limit and textbook progression design speed; a-priori, NOT tuned to the
  held-out PBOT counts).
- `src/generate.py`: `find_signal_chain(G, signal_nodes, street_name)` finds every
  signalized node touching a name-matched edge and orders them by projecting each
  node onto the DOMINANT AXIS of the matched edges (the mean unit bearing vector
  over all of them) — generic by construction, no assumption about compass
  direction and no edge-by-edge walk, so it tolerates a corridor that jogs.
  `apply_greenwave` then gives the chain's members a common coordination cycle =
  the MAX of their own (already-computed) per-node Webster cycles — the smallest
  shared cycle that still fits every member's own critical approach — while each
  member's green SPLIT (a fraction of the cycle) is left exactly as 2a computed
  it, so its window on the new cycle is automatically that same fraction (no
  change needed in `is_green`, as specced). Offsets are solved so a platoon
  leaving member 0's own green start arrives at every downstream member during
  ITS chain-phase green too: `offset_i = (offset_0 + (g_i - g_0) - cum_travel_i)
  mod C`, where `g_i` is member i's own window-start position (0 for EW, `split_i
  * C` for NS) and `cum_travel_i` is the shortest-path travel time from member 0
  at the progression speed (`_chain_travel_time_s`, shortest-path-by-length, not a
  same-name-edge walk — real named streets are often split at unsignalized nodes
  in between). The chain phase at each member — 0 (EW) or 1 (NS) — is read
  directly from the bearing of the matched edges AT THAT NODE
  (`_chain_phase_at_node`), never assumed constant along the chain: a corridor
  can jog and flip which phase serves it at one intersection without the rest of
  the chain following. An empty or single-node chain (fewer than 2 signalized
  matches) is handled gracefully — a printed warning, coordination skipped,
  behavior bitwise identical to 2a.
- Gate `src/greenwave_scenarios.py` → 3/3, through the REAL kernel on a synthetic
  3-signal arterial that itself jogs 90 degrees between the 2nd and 3rd signal
  (so the 3rd sees the chain street as NS while the first two see it as EW),
  plus an unrelated signalized 4-way that must never be touched: A) PROGRESSION —
  a platoon released exactly at signal 1's green rides the coordinated wave
  through signals 2 and 3 with zero stops, while the same platoon under
  deliberately anti-phased offsets (each downstream member placed at the exact
  midpoint of ITS OWN red window, not a matter of random-offset luck) stops at
  both; B) INERTNESS — the flag off reproduces an independently reconstructed 2a
  plan bitwise, a street matching nothing is equally inert (chain empty, warned),
  a street matching exactly one signal ("Foster Rd") is likewise inert, and the
  real chain DOES change the member plan while leaving the unrelated signal
  untouched (the "gate can fail" proof); C) STRUCTURE — the 3 members share one
  common cycle equal to the max of their own independently-recomputed Webster
  cycles, each member's split is preserved exactly, the non-member's cycle/split
  are untouched, and every offset matches an independently hand-derived
  travel-time formula (written fresh in the gate, not calling `apply_greenwave`'s
  own arithmetic back at itself) to 1e-9. Sabotage-tested: zeroing the travel-time
  offset (`cum_travel = 0.0`) broke PROGRESSION (0 stops → 10) and STRUCTURE
  (offset mismatch) while leaving INERTNESS green, as expected since that gate
  doesn't exercise the travel-time formula; reverted and reconfirmed 3/3.
- Base gates unaffected: scenarios 4/4 (including saturation, re-run on the main
  worktree with the cached graph), lanes 2/2, driver 3/3, mobil 4/4, mobil
  network 3/3, webster (decision) 5/5, webster network 3/3, kernel_regression
  bit-identical. Plus a real-graph smoke: on the cached corridor graph the
  "Powell" chain is empty as expected (no in-graph signal touches Powell), the
  no-chain path leaves the 2a plans bitwise identical, and the
  greenwave-without-webster refusal fires.
- Simplifications documented at the code: the chain finder orders members by a
  geometric axis projection, not a literal edge-sequence walk (robust to OSM
  splitting one named street into several edges at unsignalized nodes in
  between); a node touching matched edges of two different phases (a jog's own
  corner) breaks the tie toward phase 0, arbitrary but deterministic;
  `WEBSTER_GREENWAVE_STREET` defaults to "Powell" but is verified (Jul 19 audit)
  to find NO chain at all on the real cached 1.5 km corridor graph — the flag is
  exercised end to end only on the synthetic graphs in `greenwave_scenarios.py`;
  no claim is made anywhere about Powell-scale green-wave effects.
### Webster payoff run — DONE Jul 25: the first full authoritative hour with WEBSTER_ENABLED
One seeded corridor run (`src/webster_runs.py`: 1.5 km, 500 vehicles, 3600 steps,
seed 42, WEBSTER_ENABLED only, RUN_NAME `realism_webster`), read out against the
Jul 24 `realism_base` by `src/webster_readout.py` (analysis-only; also dumps the
plans the run used to `realism_webster_plans.json`). The runs share the
byte-for-byte same vehicle population (the pre-pass has its own RNG stream), so
per-segment deltas are cleanly paired. Numbers (corridor scale, one seed):
- CYCLES: all 21 nodes clamp to the 30 s minimum even at full corridor demand —
  the smoke session's "full demand will spread the cycles" hypothesis is
  FALSIFIED at this scale. From webster.py's own math a node unclamps only past
  ~823 veh/h combined critical flow; the busiest node measures 798 veh/h (3.1%
  short — close, not distant). The network's 1,008 veh/h peak approach feeds no
  signal at all (consistent with the Jul 19 no-signals-on-Powell finding).
- SPLITS are where Webster lives at this scale: 0.367–0.633, 18/21 nodes
  meaningfully off 50/50 — but 15/21 sit EXACTLY at the 7 s min-green floor, so
  the asymmetry is mostly floor-pinning, not smooth proportionality.
- VOLUMES: network throughput −6.18% (169,697 → 159,210) with ZERO winning
  segments (1,611 losers / 1,227 exact ties; max per-segment delta 0.0) —
  the 5 s/phase clearance (10 s of every 30 s cycle green for neither phase) is
  a one-directional capacity price the base's zero-clearance signal never paid.
  Not a defect: the base's free capacity was the unrealistic part. Rank order
  essentially unmoved (Spearman 0.9987), consistent with every standing
  structure-vs-demand finding.
- SPEEDS/NOISE: median deltas near zero network-wide (noise −0.16 dB(A) median)
  but heavy local movers: Holgate segments where Webster's tighter capacity
  creates standing queues swing up to +6.7 dB(A) — one checked segment holds
  12x the vehicle-seconds at 2.7 km/h vs 35.5 km/h base, and queued crawling
  traffic is LOUDER because source density dominates the speed effect in
  CNOSSOS. The hypothesis that clearance raises speed variance at signals was
  NOT supported (variance falls on signal-adjacent segments — queues compress
  speeds toward zero); reported as found.
- Caveats (printed by the readout): corridor scale, one seed, a-priori Webster
  constants (not calibrated to held-out PBOT counts), two-moment Gaussian
  noise quadrature, and no repeated-seed variance estimate — single-segment
  deltas could be seed noise.

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
