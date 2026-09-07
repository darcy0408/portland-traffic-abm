# Tableau dashboard

The public-facing interactive layer of the closure results. Tableau displays; the
ABM computes. Nothing on the dashboard is computed in Tableau beyond hover, filter,
and color.

## What exists

A four-panel Tableau Public workbook: metro closure map with a Closure dropdown
(ten closures, changed segments only, 184,335 rows; the network itself is 159,410
segments), Powell corridor detail (2,838), validation scatter (356 held-out PBOT
counts, Spearman 0.59, ledger V1), top gainers. Workbook revision 1.9 (Sept 7).

The workbook is unlisted on purpose, so its title, account, and URL are deliberately
NOT recorded in this public repo; they live in the private session notes. Share the
dashboard URL, not a single-sheet URL (a sheet URL shows only the Powell map). Making
it listed is a separate decision, not a build step.

## Source of truth

Every table the workbook binds to is produced by `src/tableau_export.py` from saved
parquet files. It runs no simulation. If a number on the dashboard is questioned,
rerun the export and diff; if the export disagrees with the workbook, the workbook
is stale and gets re-uploaded (Tableau Public extracts are snapshots, not links).

Exports land in `outputs/tableau/` (gitignored, like every generated file). From a
worktree, pass `--data-dir` and `--graph` explicitly: `data/` is gitignored and lives
in the main checkout (corridor runs) or the metro5k-scaleup worktree (metro runs).

### Sept 5 audit of the ad hoc tables

The three tables the workbook was first built from (Aug 26 to Sept 4, made inline,
no script) were checked against this script's output:

- Metro closure: numbers identical (network +0.35%, M20.14). Names differed only in
  convention; the script now uses the workbook's (first OSM name, "(unnamed motorway
  link)", spaces in road types), 0 mismatches on 129,950 matched segments.
- Validation scatter: identical ranks, rho 0.590 (V1).
- **Powell corridor: built from the wrong pair.** The table came from `powell_no2`
  (the June gravity-only run, superseded Jul 4 and never cited since), not
  `powell_through` (seed 42, through-traffic on), the pair every cited closure number
  and the SRC abstract are unified on. The Powell Detail and Top Gainers panels must be
  rebound to the `powell_through` export before the link goes to anyone.

### Sept 5 rebind (done, published, verified)

- The `powell_closure_v2` data source's file connection was replaced in web authoring
  (Edit Connection, same file name, "Replace and Update"), so every field and the saved
  Segment Line calculation rebound with no sheet edits. Extract rebuilt 4:30 PM MDT.
  Data source renamed `powell_closure_through` so the workbook says what it holds.
- The unused Aug 26 source `powell_closure_no2_tableau` (also the June run) was closed
  out of the workbook; three sources remain (metro, powell_closure_through,
  powell_validation_scatter).
- Top Gainers had a hand-picked 9-street filter from the June data (it dropped SE 17th
  Avenue, 27.9 g and rank 8 under the correct pair, and kept Woodward at 1.8 g). Now a
  Top 9 by SUM(NO2 Change (g)) filter, so it follows the data. Nine bars: Division 594.8,
  Holgate 163.4, Gladstone 109.8, Tibbetts 48.2, 29th 40.0, 32nd 33.3, 22nd 30.6,
  17th 27.9, 25th 16.3 (sum 1,064.2 g).
- Published; the hosted dashboard was reloaded as a viewer and the Powell legend
  reads -42.3 / 89.1 (the powell_through per-segment range; the June pair read
  -155.1 / 120.9). Metro legend -442.5 / 381.3 unchanged (M20.14).
- Every visible number was checked against the exports: 356 counts and rho 0.59 (V1),
  159,410 segments, 5,576 segments at |change| >= 0.1 g (counted on the rounded table
  the workbook holds; 5,357 on unrounded NOx, so keep citing the table's own count).

### Sept 6 scenario dropdown (published, workbook revision 1.7)

The metro panel now carries a **Closure** dropdown: SE Powell (the published M20.14
pair), SE Division, SE Cesar Chavez, SE Clinton. What was done and why, so the next
change does not have to rediscover it:

- **Rebind, not a new source.** The `metro` data source is an Excel connection
  (`metro_closure_v1`, sheet `metro`). Edit Connection with `metro_scenarios.xlsx`
  rebinds every field and the Segment Line calculation as long as the Excel SHEET is
  named `metro`; the file name is cosmetic. That is why `tableau_export.py` grew a
  `--sheet` option. The `.xlsx` is 7.5 MB (the CSV is 13.2 MB, over the 10 MB
  browser-upload cap); values are identical to the CSV to float precision.
- **Parameter, not a filter card.** Tableau Public web authoring's dashboard filter
  cards always show an "(All)" entry and their menu has no way to remove it; "(All)"
  would stack four closures on one map. So the dropdown is a parameter `Closure`
  (string, list built from the Scenario field, default SE Powell) and the Scenario
  filter is General = Use all, Condition by formula `[Scenario] = [Closure]`. A
  parameter control is single-choice by construction. Adding a closure means
  re-uploading the file AND adding the value to the parameter list (or switching the
  list to refresh from the field when the workbook opens).
- **Numbers on the panel, all matching the export:** SE Powell 23,716 marks, sum
  +685.9 g, legend -442.5 / 381.3; SE Division 17,842, +11.9 g, -92.4 / 27.3;
  SE Clinton 16,849, -15.8 g, -66.5 / 142.8. The old ad hoc metro table summed to
  686.7 g because its per-row rounding differed; 685.9 is the script's number.
  `|change| >= 0.1 g` counts per scenario: Powell 5,576 (the number the old title
  quoted), Division 3,388, Chavez 3,513, Clinton 3,117.
- **Panel title** (no em dashes): "The whole city, one closure: choose the street in
  the Closure menu. Metro-wide NO2 change, 159,410-segment network / Only changed
  segments are drawn. SE Powell is the published case; Division, Cesar Chavez and
  Clinton are single-seed, all-diesel exploratory runs, not results. Zoom in to
  explore." The color legend rescales per closure, so magnitudes are not comparable
  by color across closures; the legend labels say so.
- **What a closure is:** a 150 m radius zone (config.CLOSURE), every segment inside
  removed. "SE Division" is a ~300 m stretch near SE 35th, not the whole street. The
  four current closures all sit in inner SE within about 1.5 km of each other; the
  map is metro-wide, the menu is not yet. Round 2 (Sept 6-7, below) spreads it across
  N, NE, SW and outer SE.
- **Publishing lesson (cost a full rebuild):** web authoring has no draft save and the
  session expired after about two hours, in the middle of the first Publish click.
  Publish early and in stages; verify each publish through the site's own workbook
  metadata (`lastPublishDate`, `revision`), not a screenshot. The viewer-side render
  was not captured from the automation sandbox (the site's feature modal and the
  embed both defeat it); eyeball the hosted page by hand after any publish.
- Not done: the data source is still named `metro (metro_closure_v1)` although it
  now holds the four-scenario table (rename is cosmetic, do it on a quiet day); the
  four-line title squeezes the map on a laptop viewport.

## Scenario batch (Sept 5)

Three closed legs run on the metro5k-scaleup worktree at 330d034 against the shared
`metro20k_open` baseline, THROUGH 0.15, seed 42, all-diesel, 16,500 vehicles:
`scn_division_closed`, `scn_chavez_closed`, `scn_clinton_closed` (40.7 / 45.6 / 47.4
min). Gate: network NOx +0.006% / +0.006% / -0.008% vs the 645,737.8 g baseline, all
inside 2% (the Powell reference pair reproduces M20.14's +0.354%). Export:
`scenarios ... --changed-only` gives 76,582 rows across four scenarios (Powell 23,716,
Division 17,842, Chavez 18,175, Clinton 16,849), net NO2 +685.9 / +11.9 / +12.3 /
-15.8 g. Single seed, exploratory, labeled as such wherever shown.

| Table | Command | Reads |
|---|---|---|
| Powell corridor closure | `closure --open powell_through_open --closed powell_through_closed` | main's `data/processed` |
| Metro closure | `closure --data-dir <metro>/data/processed --graph <metro>/data/network/graph.graphml --open metro20k_open --closed metro20k_closed` | the metro5k-scaleup worktree (ledger sec. 2 operational note) |
| Scenario menu | `scenarios ... --open metro20k_open "SE Powell=metro20k_closed" "SE Division=scn_division_closed" ... --changed-only --sheet metro --out outputs/tableau/metro_scenarios.xlsx` | same |
| Validation scatter | `validation --run powell_through` | main's `data/processed` |

## Scenario batch, round 2 (Sept 6-7)

Six more closed legs, same provenance as round 1: metro5k-scaleup at 330d034, the
shared `metro20k_open` baseline, THROUGH 0.15, seed 42, all-diesel, 16,500 vehicles,
single seed, exploratory. Driver: the Sept 6 scratchpad `run_closure_batch2.py` (the
Sept 5 driver plus a printed pairing gate). Each zone center is a real intersection
node from the metro graph, previewed (`find_zones.py`, `find_zones2.py`) so the 150 m
circle removes the named arterial plus local cross streets only: no motorway,
motorway_link or bridge segment in any zone. Sandy sits at 57th because the 42nd
junction also takes out NE Broadway; Barbur sits on the Lair Hill stretch at Gibbs
because every candidate near Terwilliger, Capitol Highway or Burlingame removed an
I-5 ramp, and one removed I-5 mainline.

| Menu label | Zone center (lat, lon; 150 m) | Cross street | Segs closed (arterial / all) | Run | Gate vs open | Rows | Net NO2 |
|---|---|---|---|---|---|---|---|
| SE Hawthorne | 45.51206, -122.62959 | SE 34th | 12 / 34 | `scn_hawthorne_closed` | +0.03% | 17,402 | +48.0 g |
| SE Foster | 45.48864, -122.59434 | SE 67th | 8 / 28 | `scn_foster_closed` | +0.02% | 17,829 | +32.3 g |
| NE Sandy | 45.54223, -122.60459 | NE 57th | 8 / 29 | `scn_sandy_closed` | +0.06% | 17,515 | +116.8 g |
| N Lombard | 45.58248, -122.72405 | N Portsmouth | 10 / 28 | `scn_lombard_closed` | -0.01% | 17,493 | -10.4 g |
| SW Barbur | 45.49943, -122.68040 | SW Gibbs | 10 / 32 | `scn_barbur_closed` | +0.04% | 18,813 | +82.1 g |
| SE 82nd | 45.51223, -122.57870 | SE Hawthorne | 14 / 32 | `scn_82nd_closed` | +0.03% | 18,701 | +67.6 g |

Run times 46.7 to 52.2 min each. Hawthorne's wall clock was 705 min because the
machine went into Windows modern standby 25 min in and stayed there most of the
night; the result is unaffected (the sim never reads the clock). Lesson: hold standby
off for the life of the batch with an in-process SetThreadExecutionState request tied
to the batch PID (scratchpad `keep_awake.ps1`), never a power-plan change.

Export: the ten-scenario `metro_scenarios.xlsx` (sheet `metro`) is 184,335 rows and
18.0 MB, over the 10 MB browser-upload bridge, so the Edit Connection upload is a
manual drag-drop from Downloads. The four round-1 scenarios reproduce their Sept 6
numbers exactly in the new file; the old four-scenario file is kept beside it as
`metro_scenarios_4scn_sept6.xlsx` for rollback. `|change| >= 0.1 g` counts: Hawthorne
3,212, Foster 3,383, Sandy 3,325, Lombard 3,503, Barbur 3,749, 82nd 3,606. Legend
ranges (min / max g): Hawthorne -21.9 / 92.3, Foster -68.4 / 62.4, Sandy -58.0 / 49.5,
Lombard -80.0 / 51.5, Barbur -67.8 / 67.6, 82nd -95.2 / 111.4.

Published Sept 7 (workbook revision 1.8 at 21:57 UTC after the rebind and the
parameter list, 1.9 at 21:58 UTC after the title; workbook size 23.3 MB; still hidden).
Upload: Darcy dropped the 18 MB file into Edit Connection by hand (the automation tab
was renamed through `document.title` and found with Ctrl+Shift+A); switching to the
dashboard triggered "Creating Extract" automatically. Parameter: Edit Parameter, Add
values from, metro, Scenario adds all ten (duplicates of the four existing values are
dropped on OK); the current value was set back to SE Powell before publishing because
"Value when workbook opens" is "Current value". Verified in authoring: NE Sandy 17,515
marks, SUM +116.8 g; SE Powell 23,716 marks, +685.9 g; both equal the export. New panel
title (no em dashes): "The whole city, one closure: pick a street in the Closure menu.
Metro-wide NO2 change on the 159,410-segment network. / Only changed segments are drawn.
SE Powell is the published case; the other nine closures are single-seed, all-diesel
exploratory runs, not results. Zoom in to explore." Screenshots of the authoring page
timed out almost every time this session; state was read through the DOM
(`javascript_tool`) and `find` instead. Menu order of the dropdown is the four original
values then the six new ones alphabetically (cosmetic; reorder on a quiet day). The
viewer-side render was again not captured from the automation sandbox.

## Provenance and caveats that travel with the numbers

- NO2 = `config.F_NO2` (0.30) x NOx, applied at export, the same place `visualize.py`
  applies it.
- The metro tables are the M20.14 pair: seed 42, THROUGH_TRAFFIC_FRACTION 0.15 (the
  metro a-priori value; 0.30 is the corridor's and fails the ODOT band at metro scale,
  ledger sec. 20), ALL-DIESEL fleet. Absolute grams run about 4.26x the approved mixed
  fleet at metro scale (M20.16); the per-segment shape agrees at Spearman 0.913, so
  redistribution maps are sound and absolutes carry the caveat.
- The scenario menu (every closure except SE Powell) is SINGLE SEED, exploratory, and
  labeled that way. Each closed leg pairs with the shared `metro20k_open` baseline on
  the same kernel commit (metro5k-scaleup at 330d034); that reuse is the M20.14
  `run_closed_half.py` pattern and is valid because `run_simulation` seeds its own RNG
  per call. Post-run gate: network NO2 total within 2% of the baseline.
- No bridge scenario. The one bridge already tested (Ross Island, M20.18) flips sign
  across seeds and fleet; a bridge needs a paired multi-seed run before it is shown.
- Rose Quarter predicted-vs-observed panel (after Sept 11): grades come from the
  registered instrument's output only, never a Tableau calculation.
