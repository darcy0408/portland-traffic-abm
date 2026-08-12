# Cold-start emissions: design (branch `experiment/cold-starts`)

Created Aug 12 2026, Darcy's ask ("can we do a branch with cold starts figured
in"). Design first, factors sourced before any code runs: this pipeline's
emission numbers get audited, and a placeholder factor would poison every
downstream surface. Nothing here runs on Orca until the factors are sourced
and Christof has seen the design.

## Why this mechanism, and why now

The model currently has NO winter mechanism: the HBEFA3 NOx polynomial is a
hot-engine rate, so a trip's first kilometers emit the same as its last. In
reality a cold engine emits substantially more until it warms, the excess grows
as ambient temperature drops, and it lands at TRIP ORIGINS, which are
residential streets. That is exactly the season (winter) and the spatial
pattern (residential, where the heating signal also lives) where the forest
comparison currently finds the ABM adds nothing (ledger M20.11). Cold starts
are the one honest ABM-side lever on the winter story; the other winter lever
is statistical (a heating covariate added to BOTH forests) and lives outside
this branch.

## Mechanism sketch

- A vehicle spawn is a trip start. INTERNAL trips start cold; THROUGH trips
  enter the network warm (their engine started outside the study area).
  Respawns are new trips, so internal respawns start cold again. This
  asymmetry is free realism: it concentrates the excess on residential
  origins, not on freeway entries.
- Each vehicle carries `dist_since_start_m` (already derivable from its route
  progress). While `dist_since_start_m < L_COLD` (warm-up distance), the
  per-step NOx gets a multiplicative excess factor that decays to 1.0 as the
  engine warms (linear decay in distance is the EMEP simplification).
- The excess factor and warm-up distance come from the sourced methodology as
  a function of ambient temperature and the fleet class (diesel vs petrol
  differ a lot). Ambient temperature becomes a config parameter
  (`AMBIENT_TEMP_C`), set per experiment (summer run vs winter run), which is
  also the first time the model has any season knob at all.

## Data to source (DO NOT INVENT; in order of preference)

1. EMEP/EEA air pollutant emission inventory guidebook (2023), 1.A.3.b.i
   passenger cars: Tier 2/3 cold-start methodology. Gives e_cold/e_hot ratios
   for NOx by fuel, temperature, and speed band, plus the beta (cold-driven
   distance fraction) model with l_trip dependence. Public PDF + spreadsheet.
2. HBEFA cold-start (excess emission) module documentation, to stay in the
   HBEFA family the hot emissions already use.
3. EPA MOVES cold-start (start exhaust) rates as a US cross-check.

Record the exact table, edition, and page in this file when sourced, the same
way src/emissions.py records the SUMO HBEFA3 provenance.

## Hook points (verified against the current code, no code changed yet)

- `src/generate.py make_vehicle()`: mark `veh["trip_kind"]` (internal vs
  through) at spawn; initialize `veh["dist_cold_m"]`.
- The per-step emission accumulation (where speed/accel feed
  `emissions.nox_mg_per_s`): multiply by the warm-up factor while cold, and
  advance `dist_cold_m` by the step distance.
- `config.py`: `COLD_START_ENABLED` (default False), `AMBIENT_TEMP_C`,
  and the sourced parameter block, all flagged as calibration knobs.
- `src/fleet.py`: per-class cold factors if the sourced table splits by fuel;
  the single-class PC_D_EU4 path gets the diesel factor.

## Validation plan (same discipline as levers A/B)

1. Flag OFF: spawn population and per-segment NOx bit-identical to main
   (kernel regression + one saved-run comparison), so the flag can merge
   without touching any cited number.
2. Flag ON sanity: network NOx rises by a plausible cold-start share
   (published estimates put cold-start NOx in the single-digit to low-teens
   percent of urban totals; if we see 2x, something is wrong).
3. The real test, AFTER the heating-covariate control also exists: rerun the
   winter forest comparison with cold-start surfaces and the fair baseline,
   pre-registered, reported whichever way it lands.

## Scope guard

Journal-paper work. Not for the Aug 21 chapter revision beyond one sentence in
Limitations ("cold-start excess emissions are not modeled; winter is
underpredicted at trip origins"), and nothing runs before the symposium.
