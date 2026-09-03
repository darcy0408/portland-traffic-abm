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
2. [x] Physics + ODOT calibration: DONE Sept 2, two days early.
   src/barrier_physics.py: Kurze-Anderson per octave band (signed delta, 20 dB
   TNM cap, finite wall ends respected, single most-effective wall); self-test
   passes on hand values (N=0 gives 5 dB, N=1 gives 13.1, worked-geometry
   delta 0.4588 m). src/barrier_calibration.py: the check against ODOT's own
   attenuation numbers, with the geometry a real measurement sees (traffic as
   a LINE of point sources +-300 m, all inventory walls may shield, receivers
   15/30/60 m behind the wall midpoint on the shielded side).
   CALIBRATED READ of the results (barrier_calibration.parquet, figure):
   - The line-source treatment moves the textbook perpendicular-ray median
     16.1 dB(A) down to 10.0 at 30 m, the expected direction and size.
   - vs ODOT MEASURED (n=24): median bias -0.2 dB at 15 m (ours 8.7 vs 8.0).
     The magnitude at first-row distance is right. Scatter is wide (54% of
     walls below, 42% above).
   - vs ODOT PREDICTED (n=152): +4.2 dB median at 30 m, 80% above range.
     Partly ODOT design conservatism (on the 13 walls with both, ODOT's own
     measurements beat its predictions by a paired median +1.0 dB); the rest
     is real v1 overshoot, expected because pure diffraction ignores the
     ground-effect change a new wall causes (soft-ground attenuation lost,
     roughly 2-3 dB). That is a documented v2 item; do NOT tune it away
     against this same check.
   - Per-wall RANKING is weak (Spearman 0.10-0.34 vs ODOT midpoints). Honest
     limits: ODOT's receiver placement per wall is unknown, the strings are
     coarse integers, and our own 15-vs-60 m spread is 4 dB. Per-wall
     precision is probably not extractable from this inventory; the
     defensible claim is magnitude, not ranking.
   - Meaning for step 3: corridor-level redistribution needs the typical
     first-row IL to be the right size, which it is; per-wall precision
     matters less once walls aggregate along corridors.
   Step-1 parquet gained road_x/road_y (the snap foot, the calibration source
   point); rerun with unchanged snap stats. Population-centroid receivers move
   to step 3 where they belong (they need the run surfaces anyway).
3. [x] Barrier-aware surface on the saved open/closed Rose Quarter runs,
   DONE Sept 2 (ahead of the Sept 6-9 slot), src/barrier_surface.py. Inputs
   as located: the fwrqn campaign at C:/dev/pta-realism/data/processed/
   (8 paired seeds x 2 arms, non-work demand, mixed fleet, 16,500 vehicles,
   on the exact prereg metro20k graph, md5 verified), receivers = the 1,003
   block-group population centroids (landuse_bg.parquet). Construction:
   912,628 point sources (25 m spacing) from 159,425 segments, 7,120,543
   source-receiver pairs within 1.5 km, 5.2% wall-blocked with median band
   transmission 0.20 (about -7 dB, consistent with the step-2 calibrated
   first-row IL once paths run oblique and long). Everything energy-domain,
   source-side only, absolute dB never citable; the vectorized CNOSSOS and
   wall physics are verified element-by-element against the scalar
   references on every run. Geometry cached (barrier_pairs.npz) since it is
   identical across all 16 runs.
   THE BANKED PREDICTION (all numbers = median across the 8 paired seeds):
   - Network-wide the closure is nearly noise-neutral at centroids (median
     -0.02 dB, IQR -0.06 to -0.00): the freeway loss and the detour gains
     nearly cancel in log units. The story is redistribution, as with NO2.
   - Redistribution: 30,689 residents up >= 0.5 dB and 38,385 down >= 0.5 dB
     (both groups unanimous across all 8 seeds); 21,312 down >= 1 dB, 1,207
     up >= 1 dB. Largest increase +1.97 dB (BG 410510039022, 8/8 seeds),
     largest relief -2.40 dB (BG 410510038023). Relief traces I-5; the
     increases sit on the inner-eastside detour band.
   - The walls' fingerprint (the testable part): the barrier-aware and
     barrier-blind models agree wherever wall shielding is zero (wedge 0)
     and disagree by up to ~1.1 dB where walls shield the receiver.
     Two named cases: BG 410510039022 (shield 1.1 dB) rises +1.97 dB
     aware vs +1.54 blind, the wall blocks the freeway but not the new
     detour traffic, so the increase lands harder than a blind model says;
     BG 410510038022 (shield 3.3 dB) falls -2.04 aware vs -0.89 blind, the
     wall had already eaten the freeway, so its baseline is local-street
     noise and the closure quiets exactly that.
   - Honesty items: recovered speeds capped at 130 km/h (CNOSSOS validity
     ceiling; 13-25 short segments per run, the Jul 4 start-segment
     attribution limitation; uncapped, one 2 m segment at 658 km/h carried
     84% of open-s2024's source energy). Cars-only source model, no ground
     effect or air absorption, single diffraction, flat terrain: all
     inherited v1 limits, listed in the module docstring.

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
