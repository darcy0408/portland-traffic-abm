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

    A2 STATUS (Jul 31): the MEASUREMENT and the job list are built and gated;
    the runs themselves are not submitted (they are Orca wall time, and the
    submit is the user's call). What exists now:
    - run_simulation(stuck_by_hour=...) slices stuck time by ELAPSED hour --
      deliberately not the wrapped clock hour, so a week run (A3) would show
      day-over-day ratcheting instead of averaging it away. "network" gives
      the per-hour network total for free; "segments" also keys by segment
      so any corridor (Powell) can be sliced by hour. Cost measured, not
      guessed: 37.5k edges carry stuck time in a single metro hour, so a 24 h
      run holds up to ~0.9M sparse entries (~150 MB) -- job_day.sh mem raised
      16G -> 24G. Gate: stuck_scenarios D (a red straddling the 3600 s
      boundary splits 15/15 s by hand; every bucket sums back to stuck_sum;
      network mode files no segments; bucketing is trajectory-inert), plus
      the checkpoint-predates-buckets refusal.
    - The day array is now FOUR jobs, {flat, profiled} x {base, realism}, all
      bucketed. The flat pair is re-run as the CONTROL: the Jul 29 flat runs
      recorded only whole-run totals, so they can say both arms seized but
      not whether stuck time ratcheted or plateaued -- which is the A2
      question. New RUN_NAMEs (metrocal_dayflat_*, metrocal_dayprof_*), so
      nothing on disk is touched. Peak-hour demand is MATCHED across the
      pair (profiled reads N_VEHICLES as the peak fleet); the profiled day
      therefore carries less total traffic, which is the point.
    - Each summary JSON gains network_stuck_veh_h_by_hour and (segments mode)
      powell_stuck_veh_h_by_hour. Verified end to end on the corridor smoke:
      both arrays sum EXACTLY to the whole-run totals they refine.
    - GOTCHA for the submit: data/ is gitignored, so a fresh Orca clone has no
      portal_powell_sample.csv and the profile would silently fall back to the
      synthetic hourly shape. scp it first (RUNBOOK step 7 now says so, with a
      one-line check); the run log states which shape it used.
    Still to build when the runs land: the readout that reads the four hourly
    arrays and answers the PM-peak-vs-AM-peak question.

    A2 RESULT (Aug 2, Orca array 117428, 4/4 COMPLETED, seed 42 only --
    qualitative under the standing day-run caveat; readout is
    src/day_readout.py): THE DAY-SCALE QUESTION ANSWERS NEGATIVE. No arm
    meets the PM-stuck ~= AM-stuck criterion. Flat arms are saturated from
    hour 0 (no peak exists to recover from). Profiled arms start genuinely
    free-flowing (overnight stuck 0.04-0.06x quota) and seize anyway: by h23
    prof/base holds 9,591 stuck veh-h against a quota of 2,876 (3.3x) and
    prof/realism 13,455 (4.7x), both frozen at exact integers for the last
    3-6 hours, i.e. total deadlock. MECHANISM, now measured not hypothesized:
    A1 can only shed vehicles when trips COMPLETE, gridlock stops
    completions, so the fleet cannot ebb -- the congestion the profile
    relieves is what disables the relief. Realism buys a better morning and
    a worse night in BOTH regimes (crossover h9 flat / h12 profiled, ends
    5-8% worse on whole-day stuck); Powell under realism is starved, not
    flowing (0.0 stuck from h16 while the network freezes) -- "relocates the
    jam" confirmed at hourly resolution. The flat pair reproduces the Jul 29
    day runs bit-identically on all six totals, proving the bucketing inert.
    The honest headline is weaker than the fallback claim: NEITHER a demand
    profile NOR the realism stack makes day-scale run. What a day needs is
    an exit for stuck demand (trip abandonment / rerouting / parking
    timeout), which no built phase provides.

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

    B1 STATUS (Jul 31): MECHANISM BUILT AND GATED, off by default; no
    experiment run yet (that is a deliberate run decision, and the metro
    sidecar below has to be built first).
    - DATA (B1a, src/turn_lanes.py): the plan assumed OSM turn:lanes was in
      the graph. It is NOT -- zero turn-ish attributes on BOTH cached graphs.
      Cause is OSMnx's default useful_tags_way, which never requests the tag,
      not missing OSM data (an 800 m probe with it requested found 10 of 33
      Powell edges carrying one). Re-downloading would break graph identity
      (graph_metro20k_orca.graphml is the graph behind every Jul 29-31
      number), so the tag is fetched separately into a SIDECAR keyed by OSM
      way id and joined by osmid. Corridor sidecar built: 163 of 2,838 edges
      joined, 131 with a dedicated left lane, 32 of 71 Powell edges.
      A 'left' token is a pocket; 'left;through' is NOT (a turner there still
      dams the lane). CAVEAT, loud: 64 of the 163 are merged-osmid edges
      under an any-way rule that can only ADD pockets, biasing B1 toward more
      relief -- state the pocket count with any B1 result.
    - MECHANISM (B1b, generate.py): TURN_POCKETS_ENABLED puts eligible
      left-turners in a sentinel lane (POCKET_LANE = -1) once within
      TURN_POCKET_LENGTH_M (30 m a-priori, = 4 cars at 7 m each) of the stop
      line, so they leave the through queue entirely and stop being anyone's
      leader. Bay full -> later turners stay in-lane and dam it, the real
      failure mode. Requires MOBIL (pockets are a claim about lane identity;
      refused loudly otherwise, like green-wave requiring Webster). A missing
      sidecar is refused too, rather than running with zero pockets and
      looking like a result -- this fired for real during the smoke.
    - WHAT ACTUALLY DAMS THE LANE, worth knowing before reading any B1
      result: this kernel has no opposing-traffic gap acceptance, so a
      left-turner onto a CLEAR street just goes and blocks nobody. Turners
      dam the lane when their DESTINATION is full -- which is exactly the
      corridor diagnosis ("turners into jammed side streets dam their Powell
      lane"), so B1 attacks the mechanism that was actually diagnosed. But it
      means B1's effect is bounded by how often turn destinations are
      congested, and the permitted-left conflict is B2's job, not B1's.
    - Gates: src/turn_pocket_scenarios.py 5/5 on a hand-built four-way
      intersection (jammed left destination: 0 of 4 through cars pass without
      a bay, 4 of 4 with it; overflow admits exactly the hand-computed 4
      nearest the line and the rest still dam; bearings read W->C->N left,
      ->E straight, ->S right; a trip ENDING at the node is never admitted;
      flag-off inertness; the no-MOBIL refusal). All eleven suites green,
      kernel_regression bit-identical. End-to-end on the real corridor graph
      with the real sidecar: 48 distinct pocketed segments used, peak 6 cars
      in bays, and zero cars in a bay on a segment without one.
    - TO RUN THE EXPERIMENT: build the METRO sidecar first (a 20 km fetch,
      `python src/turn_lanes.py --build --graph
      data/network/graph_metro20k_orca.graphml`), and give it its own harness
      the way the ablation got one. Do NOT add an arm to
      metro_calibrated_experiment.ARMS: build_jobs indexes SLURM array tasks
      by arm order, so inserting one renumbers the 48 existing jobs.
      METRO SIDECAR STATUS (Aug 1): BUILT on the local machine
      (data/network/turn_lanes_20000m.json): 13,807 tagged ways; joined onto
      graph_metro20k_orca.graphml it reaches 8,646 of 159,425 edges (5.4%),
      6,686 with a dedicated left pocket; Powell 173 of 468 edges tagged, 156
      with a pocket. CAVEAT, louder at this scale: 5,317 of the 8,646 tagged
      edges (61%, vs the corridor's 39%) are merged-osmid edges under the
      any-way rule that can only ADD pockets -- a metro B1 result is even more
      of an upper bound than a corridor one. data/ is gitignored, so Orca
      needs the sidecar scp'd just like the PORTAL csv.

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

    B3 STATUS (Aug 1): SHIPPED, gated, off by default. The three knobs are
    pinned to NHTS 2022 Summary of Travel Trends numbers, all a-priori,
    never fit to the held-out counts:
    - NONWORK_TRIP_SHARE = 0.64 from Table 8-2's WEEKDAY vehicle-trip split
      (work incl. work-related business 36.0% / non-work 64.0%) -- weekday,
      deliberately, because every citable run is one; the same table's
      weekend split (13/87) is the ready-made lever for the future
      weekend-demand work. At the 7 am peak commutes are still under half
      of all trips (Fig 8-1), so the share is not wildly wrong at peak.
    - Destinations: consumer-facing WAC sectors CNS07/16/17/18/19 (retail,
      health, entertainment, food, personal services), 292,928 jobs across
      the 1,003 metro block groups, summed from the SAME cached
      or_wac_2021.csv.gz the total-jobs load reads (no new download, no new
      vintage). Origins stay resident population.
    - NONWORK_DECAY_SCALE_M = 800: Table 3-5 network-calculated lengths,
      shopping 5.8 mi + errands 8.7 mi trip-weighted = 7.3 mi = 0.54 x
      work's 13.5 mi, times the work layer's 1500 m.
    Mechanism: the layer rides INSIDE the demand dict (demand["nonwork"],
    attached by build_demand_weights), so every consumer -- run_simulation,
    the Webster measured-flows pre-pass, the harnesses -- sees the same trip
    mix, and signals are timed to the composition they serve. The
    share-of-local-trips draw sits before the OD/gravity branch in
    make_vehicle with a share>0 guard, so share=0.0 consumes ZERO extra RNG
    draws. Missing/empty/degenerate service table, share outside [0,1], or
    the flag over a None work layer all REFUSE loudly (turn-pocket
    precedent), never fall back silently.
    Gates: src/nonwork_scenarios.py 4/4 -- (A) share 0.0 bitwise identical
    to no-layer INCLUDING final RNG state, with 562 respawns exercised, and
    share 1.0 with all service mass hand-placed on one node sends every
    trip there; (B) Voronoi origin/dest weights on a hand 3-BG/4-node case
    match hand values exactly, zero-service BGs contribute zero weight, and
    all five refusals fire; (C) real corridor graph + real Census/WAC
    masses: non-work trips route SHORTER than work trips (1,387 m vs
    1,771 m, ratio 0.78 -- direction right; the 1.5 km window truncates
    both arms toward each other, so 0.54 is not expected at corridor
    scale); (D) 200 seeded (o, d) pairs identical across two independent
    builds. All eleven prior suites re-run green, kernel_regression
    bit-identical.
    Honest limitation, stated in config: social/recreational trips (14.0 mi
    average, often ending at private homes) are approximated by the same
    retail attractor and short decay; the long social-rec tail is not
    reproduced. A knob for the mentor's calibration gate.
    NOT DONE: no experiment run. The natural first read is the metro
    peak-hour arm with the flag on vs the committed metrocal arm -- where
    do the cars land (Powell retail frontage vs office corridors), and does
    the count agreement move. Needs its own RUN_NAMEs; nothing on disk is
    touched.

B1 x B3 HARNESS (Aug 1): BUILT and smoke-proved, not submitted.
    `src/metro_b13_experiment.py` + `orca/job_b13.sh`. A 2x2 factorial on top
    of the FULL realism stack (B1 requires MOBIL, and the Jul 31 ablation
    showed lane-changing is what reaches the band at all), 3 new arms x the
    same 8 pinned seeds = 24 one-hour jobs at n=16,500:
      pockets / nonwork / both.
    The CONTROL is not re-run -- metrocal_realism_n16500_s* (Jul 29, same
    graph, demand, seeds, steps, both flags off) is joined from disk, which is
    legitimate ONLY because both features are proved bitwise inert when off
    (turn_pocket + nonwork gates, kernel_regression). Readout verified against
    it: control reads 1,404 +/- 42 veh/hr IN BAND, matching ledger ABL6
    exactly, so the join is right.
    Readout reports PAIRED per-seed deltas as well as arm means -- the seeds
    are shared, and the closure work already learned that unpaired single-seed
    diffs jitter enough to swamp a small effect.
    `--check` verifies all four prerequisites (metro-radius sidecar, WAC
    service-jobs file, metro graph, 8 control summaries) in one second before
    any cluster time is spent. `--smoke` runs all three arms in ONE process and
    ASSERTS no flag leaked between them (run_one's complement-off loop is
    supposed to prevent that; the smoke now proves it did).
    Smoke finding worth knowing before reading the real result: at 120 vehicles
    on the uncongested corridor graph, the `nonwork` and `both` arms are
    numerically identical -- turn pockets are inert without congestion, exactly
    as the mechanism says (turners dam a lane only when their DESTINATION is
    full). B1 can only show an effect where the network is actually jammed,
    which is why this must run at metro scale and why a null B1 result would
    need to be read as "not enough congested turn destinations", not "pockets
    do not matter".
    SLURM resources are measured, not guessed: 4 h / 16G, from ablation job
    115208 (same graph, same demand, same one hour) running 1:01-1:56 at 16G.
    TO SUBMIT (after the A2 day array frees the queue): scp the harness is not
    needed (it is committed), but data/ is gitignored -- the metro sidecar was
    scp'd Aug 1 and is already in place.

    B1xB3 RESULT (Aug 2, Orca array 117559, 24/24 COMPLETED, ~2.5 h/task;
    band readout `--readout`, count agreement src/b13_count_agreement.py):
    A DOUBLE NULL/NEGATIVE, both read against the pre-registered measures.
    - B1 (pockets): NULL on both measures. Busiest Powell +2 +/- 2 veh/hr
      paired vs control (1,406 vs 1,404, both IN BAND), stuck -18 +/- 29,
      count agreement +0.000 +/- 0.001 (5/8 seeds up). Read as
      pre-registered: at in-band metro flow there are not enough congested
      turn destinations for pockets to matter, and the 61% merged-osmid
      caveat means even this null is an upper bound. The mechanism that
      could still matter is B2's opposing-flow conflict, not bay capacity.
    - B3 (nonwork): NEGATIVE as parameterized. Busiest Powell falls OUT of
      the band, 1,404 -> 889 (-515 +/- 38 paired); network stuck improves
      14% (-585 +/- 139); and on its OWN payoff measure -- Spearman vs the
      held-out counts on the metro graph, throughput, geometry snap, 372
      matched segments -- it does NOT improve: control +0.621 +/- 0.015,
      nonwork -0.010 +/- 0.012 paired (2/8 seeds up). Diverting 64% of
      local trips to short service runs takes through-flow off Powell
      without putting cars anywhere the counts like better.
    - both ~= nonwork on everything (pockets add nothing on the B3
      background either).
    First metro-scale count rho ever computed, so the control's +0.621 is
    itself a new (unledgered) number; corridor 0.51/0.59 is a different
    graph and matched set, do not compare across.
    CONSEQUENCE for the plan: the realism stack with work-only LODES demand
    remains the best configuration on every measure. B3's NHTS knobs are
    NOT retuned quietly (calibration-gate rule); the a-priori composition
    is simply reported as not helping. The open levers are B2 and the
    day-scale demand-exit problem A2 exposed.

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
