# Tableau dashboard

The public-facing interactive layer of the closure results. Tableau displays; the
ABM computes. Nothing on the dashboard is computed in Tableau beyond hover, filter,
and color.

## What exists

A four-panel Tableau Public workbook: metro closure map with a Closure dropdown
(ten closures, changed segments only, 184,335 rows; the network itself is 159,410
segments), Powell corridor detail (2,838), validation scatter (356 held-out PBOT
counts, Spearman 0.59, ledger V1), corridor top gainers, and since revision 2.6 a metro
top-10 gainers chart driven by the Closure menu. Workbook revision 2.6 (Sept 8 16:47
UTC): the metro map is filtered to an inner-Portland box, 13 x 16 km, and to segments
changing by 1 g or more, colored on a -50 to +50 g capped scale with line width by
magnitude (see "Why the metro panel reads as nearly blank" under round 2).

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

Why the metro panel reads as nearly blank at its default view (Darcy's Sept 7 screenshot, measured from the M20.14 pair, scratchpad `metro_spread.py`): the changed-only export keeps every segment with ANY nonzero change, and for SE Powell those 23,716 segments span the entire 20 km disk (same lat/lon extent as the full network; median 10 km from the zone), so the map auto-fits to the whole metro. On the -442.5 / 381.3 color scale only 806 segments carry >= 1 g of change (176 >= 10 g, 40 >= 50 g), everything else draws near-white, and 83% of the total |change| sits within 10 km of the zone, 54% within 5 km. Add the long title (seven lines at a laptop width, which leaves the map about 180 px tall) and the panel is a pale smear. Fix APPLIED the same evening (workbook revisions 2.0 title, 2.1 filter, 2.2 title again; 2.2 published 01:11 UTC Sept 8, still hidden): web authoring has NO map pin (the map toolbar's More Actions menu holds only Zoom Area, Pan and the selection tools), so the fixed view is done with data instead. A boolean calculated field `Inner Portland` = `[Lat] >= 45.475 AND [Lat] <= 45.595 AND [Lon] >= -122.75 AND [Lon] <= -122.55` sits on the Metro Overview Filters shelf as `Inner Portland: True`, so the auto-fit lands on the same box, 13 km tall and 16 km wide (N Lombard to SE Foster, SW Barbur to SE 82nd, every zone at least 1.4 km inside), for every closure. Cost: segments outside the box are no longer drawn (SE Powell 8,948 of its 23,716 marks; its in-box sum is -437.0 g and its legend max drops from 381.3 to 289.6). Title cut to one sentence pair (no em dashes): "Inner Portland, one closure: pick a street in the Closure menu. SE Powell is the published case; the other nine are single-seed exploratory runs, not results." The panel's short height on a laptop is now the limiting factor; a layout change (a taller bottom row or a full-width metro panel) is the next lever, not done. Raising the changed-only cutoff to >= 0.1 g would cut the export to about 37,000 rows (about 4 MB, back under the 10 MB upload bridge) and stays optional. Quirks this time: the filter dialog's checkbox list ignored coordinate clicks, ref clicks and Space (its summary stayed at "Selected 0 of 2 values") yet OK by element ref applied True; the calculation editor sends keystrokes to the formula until the name label is double-clicked; the Edit Title editor (a TinyMCE iframe) appears a second or two after the dialog, so click into it only once it exists; mid-session the automation tab's viewport shrank to 535 x 617 CSS px and resize_window could not restore it, while a fresh tab had the full viewport (safe, because everything published reopens from the server).

Second pass (Sept 8 morning, workbook revision 2.3 at 13:36 UTC, still hidden): the box alone still read as a beige haze because most in-box marks were near-zero on a -442/+290 scale. Now (a) the box field is `Inner Portland 1g+` = the box AND `[NO2 Change Magnitude (g)] >= 1`, so SE Powell draws 465 marks (in-box sum -408.7 g); (b) the color scale is Custom, start -50, end 50 (Edit Colors: the Start/End dropdowns offer Automatic / Custom / Update on interaction, then the value boxes are typed), and mark opacity is 100% (was 80); (c) `NO2 Change Magnitude (g)` is on Size, so wider lines mean bigger changes; web authoring has no Edit Sizes, so widths rescale per closure, and the size legend is not on the dashboard (the title explains the widths instead); (d) legends retitled on the sheet through the legend card's context-menu button, Edit Title: "Metro map: NO2 change (g), color capped at -50 to +50" and "Line width: NO2 change magnitude (g)"; the Powell detail legend still says "NO2 Change (g)" because its dashboard zone exposed no menu; (e) panel title now 12 pt (no em dashes): "Inner Portland, one closure: pick a street in the Closure menu. Segments changing by 1 g or more, wider for bigger changes. SE Powell is the published case; the other nine are single-seed exploratory runs, not results." Mechanics that worked: the menu button at the right end of a Data pane row (`tab-schema-field-pill-menu-btn`) gives Edit... for a calculated field; double-clicking a measure adds it to the Marks card and the pill's icon menu then offers Color / Size / Label / Tooltip. Mechanics that failed: "Add to > Filters" from the field menu did nothing, and dragging a field onto the Filters shelf left a stuck ghost pill (reload the tab to clear it; unpublished edits are lost, so publish first); the Edit Title editor needs a screenshot or about six seconds before it accepts focus. Not done: a taller metro panel (layout), the Powell legend title, and the em dash in the dashboard subtitle.

Third pass, the "Christof's eyes" list (Sept 8 morning, workbook revisions 2.4 at 16:14, 2.5 at 16:17, 2.6 at 16:47 UTC, still hidden). (1) Models named on every panel: corridor map headline "When Powell closes, its pollution does not disappear. It moves." (bold 15 pt) over a 12 pt subtitle naming the corridor model (2,838 segments, published case, 12 seeds) and stating the static-model contrast (a land-use model predicts zero change on every street because its inputs do not change); corridor gainers title names the corridor model and carries the grams caveat (all-diesel upper bound, two to four times a mixed fleet, pattern not magnitude); validation title explains rank agreement, 356 held-out counts, 0.59, and the McDonald 2026 bands (structural near 0.3, demand models 0.7 to 0.9); metro title names the metro model (159,410 segments, single seed). (2) A Text object under the Closure menu (double-clicking Text in Objects drops it into the right column) says freeways are not in the menu and that the real I-5 southbound Rose Quarter closure (from Sept 11 2026) gets its own predicted-versus-observed panel graded by the preregistered instrument. (3) Metro Overview labels: Label card, Show Mark Labels, Marks to Label = Min/Max, Field = SUM(NO2 Change (g)), Street moved from Detail to Label through the pill's icon menu, so the deepest drop (the closed stretch) and the biggest gain carry street names. (4) New sheet `Metro Gainers`: Rows Street, Columns SUM(NO2 Change (g)) (Show Me horizontal bars), toolbar sort descending, Street filter Top 10 by SUM(NO2 Change (g)) plus wildcard "Does not start with (unnamed" (the unnamed motorway pools otherwise take two of the ten slots); the Scenario and `Inner Portland 1g+` filters were set to Apply to Worksheets > All Using This Data Source and added to context on this sheet so the Top 10 is computed after them (before context it returned 6 or 8 rows). SE Powell: 10 named streets, 1,462.8 g, Holgate, Foster, Division, Glisan on top. Title: "Where the pollution went in the metro model: top 10 NO2-gaining named streets for the selected closure, summed over the segments drawn on the map (grams, single seed)." Placed in the bottom row: validation 290 | metro gainers 290 | metro map 579 (dashboard px of an 1159-wide row); top row unchanged (corridor map 579 | corridor gainers 579). Tiled-layout lessons: double-clicking a sheet in the Dashboard pane always splits the FIRST tiled cell in half; a zone dropped inside another zone splits that zone's cell in half and the vacated space goes to the moved zone's former sibling; a drop about 17% into a single-zone cell inserts as a sibling instead; a drop within ~25 px of the dashboard edge makes a full-height column; tiled size fields in the Layout pane are disabled; divider drags do not register; zone moves work by dragging the top-centre handle (`tabAuthZoneDragTarget`); the Dashboard pane's Sheets list only shows a few rows, scroll_to the sheet before double-clicking; Ctrl+Z undoes layout steps cleanly. Still not done: the Powell detail legend title, a fixed line-width range (no Edit Sizes in web authoring), the size legend on the dashboard, panel heights.

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
