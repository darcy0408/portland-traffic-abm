# Sound-barrier physics build (experiment/noise-barriers)

Started 2026-09-01. Goal: barrier-aware noise surface, with the open-vs-closed
Rose Quarter noise-redistribution prediction banked in a dated commit BEFORE the
Sept 11 closure. Christof's option 4 (sound-barrier siting) is the motivating ask
(his Aug 30 email). Decision (recommended, Darcy did not object): this is a dated
exploratory commit, NOT a formal prereg appendix; do not stake the campaign's
registration discipline on new physics.

## Why this matters for the closure story

I-5 traffic sits behind ODOT sound walls; its detour routes (I-405, surface
streets) mostly do not. So the closure moves noise from shielded corridors to
unshielded neighborhoods. Barrier physics is what makes that visible.

## Honest limits (say these everywhere)

- October measures travel times only. This prediction is never gradeable against
  the closure. Pre-banking buys a tamper-proof timestamp, nothing more.
- ODOT inventory covers state highways + some county/city walls. OSM cannot
  backfill (28 tagged noise barriers metro-wide). Layer is honest on freeways,
  incomplete off the state system. Fine for a freeway-closure story.
- v1 physics is single-diffraction Maekawa/Kurze-Anderson insertion loss per
  octave band, capped at 20 dB (TNM's own cap), not full CNOSSOS diffraction.
- Wall points are reconstructed to lines (below): centered-at-point is an
  assumption, document it.

## Data in hand

- data/odot_sound_barriers_metro.json: 229 walls, ODOT TransGIS layer 135
  (Sound Barrier), Portland bbox (-122.90,45.40,-122.45,45.65), pulled
  2026-09-01. Fields: ht_meter (median 3, max 11), len_meter (median 211, max
  2118), HWYNUMB (ODOT numbering: 001=I-5, 064=I-205, 002=I-84; 'cou'/'Cit' =
  county/city), cnstrc_dt, and atnatn_pre / atnatn_msr (predicted + measured
  attenuation strings like "4-7 dBA", present on 157 walls). Geometry is POINT.
  37 walls in the Rose Quarter bbox.
- Endpoint: gis.odot.state.or.us/arcgis1006/rest/services/transgis/catalog/
  MapServer/135/query (maxRecordCount 100000).
- WSDOT has an open Noise Walls layer if the WA side is ever needed.

## Build plan and status

1. [x] Wall-line reconstruction: DONE Sept 1 (src/barriers.py), a day early.
   224 of 229 walls reconstructed (5 dropped for missing length, 1 height
   imputed to the 3.0 m median). Median snap 17 m, max 72 m, none past the
   100 m flag. The v1 any-class snap drew 21 walls PERPENDICULAR to their
   freeway (dead-end cross-streets touch the wall and win nearest-edge), so
   the bearing now comes from class-filtered snapping: state-highway walls
   (numeric HWYNUMB) to motorway/trunk/primary, cou/Cit walls to
   secondary-and-above, any-class only as a >150 m fallback (3 walls, all
   benign: two on a literal frontage road). Built-in consistency check passed:
   every fixed wall's snap_ref matches its ODOT HWYNUMB (001=I-5, 026=US 26
   Powell, 047=US 26 Sunset, 064=I-205, 144=OR 217). Output:
   data/processed/odot_walls_lines.parquet (gitignored; v1 kept aside as
   _v1_anyclass for the diff), verification map
   outputs/figures/barrier_lines_map.png (Rose Quarter walls hug I-5, correct).
   Graph md5 re-verified against the Appendix R pin before snapping.
2. [ ] Physics (Sept 4-5): Maekawa insertion loss per octave band from path-
   length difference over the wall top; CNOSSOS source heights, receiver 1.5 m;
   receivers = population centroids (block groups), not the nominal 10 m point.
   Then the calibration check: our insertion loss vs ODOT's own atnatn_pre /
   atnatn_msr per wall. That check is publication-grade and unusual.
3. [ ] Barrier-aware surface on the saved open/closed Rose Quarter runs
   (Sept 6-9), banked with a dated commit. Locate the fwrq harvested parquets
   first (fwms parquets live via the freeway-closure worktree; fwrq analogous,
   check pta-* worktrees / analyses dirs / Orca harvest locations).

## Reuse, do not reinvent

- src/freeway_noise_contrast.py: THE idiom for street-level noise aggregation
  (energy domain, length-weighted per-metre energy, never average dB; source
  levels only, absolute dB not citable). Extend this pattern.
- src/noise.py: CNOSSOS category-1 source model, verified against Directive
  (EU) 2015/996 Table F-1. Its module docstring lists barriers as a dropped
  term; this build closes that item.
- NOISE_ACCURACY_BACKLOG.md (freeway-closure worktree): the ranked noise-gap
  list (heavy vehicles #1, junction accel #2, road surface #3). Barriers jump
  the queue because of Christof's option 4 and the Sept 11 timing; the backlog
  stays the roadmap for paper 2.
- Jul 4 audit fixed point-to-segment snapping in validate_traffic.py; reuse its
  geometry idiom for wall-point snapping (do not snap to midpoints).

## Hard dates this build must yield to

Floor run ~Sept 4 (Orca; no conflict, this build runs no sim). Rerouting-arm
registration before ~Sept 8 (Christof's Aug 30 reply did not object; proceed as
announced). Closure Sept 11. SIGSPATIAL registration: Darcy registers by ~Sept
12 ($450 student rate; Renso hardship email drafted for Darcy to send).
