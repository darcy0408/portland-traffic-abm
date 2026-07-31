# Real-demand upgrade plan — getting all the cars on the road

Written Jul 30, from the Jul 29 metro results (`CALIBRATED_DEMAND_PLAN.md`
RESULTS section). Same governance as every plan here: staged, each stage
gated by hand-checkable scenarios through the real kernel, every new flag off
by default, nothing tuned to the held-out counts except where a stage says
CALIBRATION out loud, one sim at a time, seeds pinned.

## Where the evidence says we are

- Peak hour, metro, realism stack: busiest Powell 1,404–1,566 ± ~45 across
  the demand ladder — IN the real 1,400–1,745 band, but saturating ~1,570.
  Doubling demand (16.5k → 33k) buys +162 veh/hr; the last 8,250 vehicles
  bought +27. A NEW ceiling binds ~10% below the band top.
- 24 h at constant peak demand: BOTH arms seize (base 72% / realism 76% of
  vehicle-time stuck). Realism relocates the jam (Powell clear but starved),
  it does not prevent the spiral. Flat demand is a permanent rush hour; no
  finite network survives one.
- Corridor diagnosis (Jul 27-28) already named the peak mechanism: turners
  into jammed side streets dam their through lane; side arterials with 50/50
  splits choke first; spillback strangles the network.

So "all the cars on the road" means two different fixes, not one:
(A) cars must be able to LEAVE and demand must EBB (day scale), and
(B) the peak-hour ceiling must rise from ~1,570 toward the 1,745 band top
    (mechanism, not volume — the ladder proved volume alone is spent).

## Phase A — time-varying demand (gates ALL day/week claims)

A1. Hourly demand profile. A multiplier m(t) on trip generation, 24 values,
    from a real hourly traffic profile (PBOT hourly counts if extractable,
    else the standard FHWA urban-arterial hour-of-day shape — a-priori
    either way, NOT fit to our validation counts). Implementation: respawn
    gating — a finished trip respawns only with probability m(t)/m_peak;
    below-quota vehicles PARK (leave the network) and rejoin when m(t)
    rises. The active-fleet size then tracks the profile with no new
    physics. Flag `DEMAND_PROFILE_ENABLED`, off by default.
    Gates: (i) inertness — flat profile ≡ base, bitwise; (ii) conservation —
    parked + active + finishing == N_VEHICLES every step; (iii) hand-check —
    a two-level square-wave profile yields active-fleet counts predictable
    by hand; kernel_regression bit-identical with the flag off.
    (Seeded by the parked AM/PM worktree experiment — promote, don't rebuild.)

    A1 STATUS (Jul 31): SHIPPED, gated, off by default. Implementation is
    quota-based (the deterministic form of the respawn gate): each hour has an
    active-fleet quota round(N * m(h)/m_peak); a trip finishing over quota
    parks, parked cars release as fresh trips when the quota rises, and the
    initial fleet parks down to hour zero's quota before the first step -- so
    N_VEHICLES now means the PEAK-hour fleet, matching the metrocal ladder.
    Chosen over the literal probability-gate wording above because it consumes
    ZERO extra RNG draws, which makes gate (i) provable in the strongest form:
    flat profile == base bitwise INCLUDING the final RNG state (both arms of
    the gate confirm). Profile source: demand_data.hourly_demand_profile() --
    the real PORTAL hour-of-day curve (CSV copied into this worktree's data/;
    NOTE data/ is gitignored, so Orca needs the CSV scp'd or the run falls
    back to the synthetic shape; the run log prints which one it used) -- or
    an explicit config.DEMAND_PROFILE list. Gates: all three planned checks in
    src/demand_profile_scenarios.py 3/3 (bitwise+RNG inertness with 533
    exercised respawns; conservation every step of a 2.5 h square wave with
    the hand-derived 40/16 quotas, one-step refill, completion-paced ebb;
    quota/start-hour/park-down arithmetic vs hand values + loud refusal of a
    malformed shape), the other nine suites re-run green, kernel_regression
    bit-identical. Interactions pinned in code: run_day_experiment refuses the
    flag (it applies the same shape itself, one sim per hour), and the Webster
    pre-pass deliberately measures the full un-gated fleet, i.e. signals are
    timed once to PEAK-hour flows like a real fixed-time plan. The per-hour
    stuck buckets A2 needs are NOT built yet (next increment).

A2. Re-run the two day jobs WITH the profile (Orca, same harness, new
    RUN_NAMEs). The question: does realism now reach a daily steady state —
    stuck fraction recovering after the AM peak instead of ratcheting?
    Readout: stuck veh-h BY HOUR (needs the stuck accumulator sliced by
    hour — small extension: optional per-hour buckets, same opt-in pattern).
    Success = PM-peak stuck ≈ AM-peak stuck (no day-long accumulation).
    If base still seizes and realism doesn't, THAT is the day-scale
    contrast worth citing; if both stabilize, the honest claim is "a
    demand profile, not the realism stack, is what makes day-scale run."

A3. Only after A2 stabilizes: the week run Christof asked about (7×86,400
    steps, checkpointed, long partition — ~3-5 days wall on current rates).

## Phase B — raise the peak ceiling (mechanism, in evidence order)

B1. Turn pockets / dedicated turn lanes. THE named corridor mechanism: a
    left-turner today waits in the through lane and dams it. OSM carries
    `turn:lanes` tags on major arterials; where a left-turn lane exists,
    a turning car moves into a POCKET queue at the segment end (finite
    capacity, spillback into the through lane only when the pocket fills —
    which is the real failure mode too). Flag `TURN_POCKETS_ENABLED`.
    Gates: through-car passes a waiting turner where a pocket exists, is
    blocked where none does; pocket overflow dams the lane; inertness off.
    Expected effect: directly attacks the ~1,570 ceiling AND the
    side-street choke (Division/Chavez jams began at the turn interface).

B2. Protected left-turn phases. Two-phase Webster serves EW/NS only;
    permitted lefts across opposing flow are effectively free today
    (unmodeled conflict) yet still dam their lane. Extend the Webster plan
    to an optional 4-phase cycle (EW-left / EW-through / NS-left /
    NS-through) at intersections where both cross streets are multi-lane.
    Uses the same measured-flows pre-pass. Gates: phase truth table,
    clearance accounting, asymmetric-left discharge scenario, inertness.

B3. Non-commute demand composition. LODES is work trips only; most real
    trips are not. Add a second OD layer: gravity on retail/service job
    density (already have WAC job categories) for shopping/errand trips,
    mixed at the national NHTS work:non-work share (a-priori). Flag
    `DEMAND_NONWORK_ENABLED`. Gate: weights sum, reproducibility, spatial
    sanity (non-work trips shorter on average — NHTS says ~half the length).
    Expected effect: loads Powell's retail frontage the way real ADT does;
    may matter as much as B1 for WHERE the cars are.

B4. (Only if B1–B3 leave a gap) Saturation-flow calibration: IDM T=1.5 s
    implies ~1,900 veh/h/lane free-flow — close to the standard 1,900
    PCU/h/lane, so headway is probably NOT the binder; check before
    touching. Any change here is CALIBRATION and must be labeled as such.

## Phase C — the calibration pass (explicit, last)

With A1 + B1–B3 in: ONE free dial (global demand scale) fit on a TRAINING
half of the PBOT counts, validated on the held-out half + the Powell band.
Everything before C stays a-priori so C's fit is honest and small. Deliver:
the calibrated peak-hour metro run, the day run with profile, mean ± SD over
the 8 pinned seeds, and the same summary-JSON + readout pipeline.

## Order and cost

A1 → A2 are the highest-value next runs (they unblock the day/week story and
reuse the Orca harness as-is). B1 is the highest-value kernel change (named
mechanism, OSM data already in the graph). B2 rides on B1's intersections.
B3 is data work, no kernel change. Rough effort: A1 ~a session (worktree seed
exists), A2 ~a day of Orca wall time, B1 ~1-2 sessions with gates, B2 ~1
session on top of B1, B3 ~a session. Each lands separately, gated, off by
default — the committed model never moves until a comparison says it should.
