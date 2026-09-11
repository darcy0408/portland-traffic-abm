# Tableau dashboard

The public-facing interactive layer of the closure results. Tableau displays; the
ABM computes. Nothing on the dashboard is computed in Tableau beyond hover, filter,
and color.

## What exists

A four-panel Tableau Public workbook: metro closure map with a Closure dropdown
(ten closures, changed segments only, 184,335 rows; the network itself is 159,410
segments), Powell corridor detail (2,838), validation scatter (356 held-out PBOT
counts, Spearman 0.59, ledger V1), corridor top gainers, and since revision 2.6 a metro
top-10 gainers chart driven by the Closure menu; fixed size 1300 x 880. Workbook revision 2.8 (Sept 9 00:37
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

Fourth pass (Sept 8 afternoon, workbook revision 2.7 at 22:11 UTC, still hidden), after Darcy's narrow-window screenshot: (1) the dashboard Size is now Fixed 1300 x 880 instead of Automatic, because Automatic collapsed the five-panel layout at a 1280 px window (the two 25% cells shrank until their titles filled them and the scatter and bar chart vanished); a fixed size scrolls instead. Size popover: click the Size box, the mode selector offers Fixed size / Automatic / Range, then Width and Height are typed (click, Ctrl+A, type, Return; Tab lost the second value once). (2) A stray mark selection on the corridor map had been PUBLISHED with 2.6 (status bar read "1 of 2838 marks"; viewers saw the map dimmed with one highlighted segment, the black rectangle in Darcy's screenshot). Selections travel with the workbook: check the status bar reads "N marks", not "1 of N", for every zone before publishing; clicking an empty spot of the map clears it. (3) Validation title cut to "Model vs. reality: 356 held-out PBOT counts, rank agreement 0.59 (Spearman). Structural models score near 0.3 on this test, full demand models 0.7 to 0.9 (McDonald 2026)." and the metro gainers title to "Metro model: top 10 NO2-gaining named streets for the selected closure (grams, single seed)." (4) Correction to the label claim above: the Min/Max labels mark the largest drop and the largest gain, which is NOT always the closed stretch; for SE Powell they land on Southeast Grand Avenue and an unnamed motorway link, for N Lombard on North Lombard Street and North Interstate Avenue. Failure mode seen this pass: with the Chrome window minimized (outerWidth 159) the Edit Title editor never initializes and screenshots time out; the web session also timed out after about two hours and dropped the unpublished size change, so it was redone in a fresh tab.

Fifth pass (Sept 8 evening, workbook revision 2.8 at 00:37 UTC Sept 9, still hidden): the Min/Max street labels were removed from the metro map (Metro Overview, Label card, Show Mark Labels unchecked; the Street pill stays on Label but draws nothing, so tooltips are unchanged). Reason: for SE Powell the largest-drop label sat on Southeast Grand Avenue, single-seed noise on a high-volume segment, not a closure effect, and it was the first thing a reader's eye would land on. Nothing else changed. Verified two ways: the workbook metadata reports revision 2.8, and a fresh authoring session opened from the server shows the Label popup greyed out (Show Mark Labels off). Anonymous access re-checked with curl and no cookies: the viz URL resolves 200 and the workbook API returns revision 2.8 with showInProfile false. Quirks this pass: the find tool's "Metro Overview" match was a Sheets-list option, not the bottom tab strip; the real tabs are `.tabAuthTab` elements and respond to dispatched mousedown/mouseup/click; the Marks card Label button (`tabAuthEncodingButtonArea`, role=button) opens on the same dispatched sequence; the dashboard canvas and map render blank in screenshots and Page.captureScreenshot times out while the map draws, so state was read from the DOM.

## Rose Quarter predictions workbook (Sept 10: data built and verified, workbook not started)

Christof's Sept 10 ask: "a Tableau for the I-5 closure". Scope, as committed in the
Sept 10 reply to him: a SEPARATE workbook that shows only the preregistered
predictions, with observed closure data kept off until the October scoring is
banked, then a predicted-versus-observed panel added from the registered
instruments' output.

Rules for this workbook:
- Predictions only until the October scoring is banked. No PORTAL or logger data
  from Sept 11 onward is uploaded, joined, or displayed before then. The prereg has
  no rule about public display (checked Sept 10); this is the project's own rule.
- Grades come from src/rosequarter_score.py and the logger instrument, never from a
  Tableau calculation.
- Every number traces to the ledger by ID or is recomputed from the campaign's saved
  files behind a guard that refuses to write on any mismatch.

Data (script-built, read-only, in outputs/tableau/, gitignored):

1. `rosequarter_paired.xlsx`, sheet `rosequarter`, 64,331 rows, 7.2 MB (under the
   10 MB upload bridge). Built by `tableau_export.py paired` over the fwrq campaign:
   8 seeds (42 7 13 99 314 777 2024 8) x arms open / rosequarter, files in
   C:/dev/pta-realism/data/processed, graph graph_metro20k_orca.graphml (159,425
   edges). Columns are COLS plus Seeds, Seeds Agreeing (NO2), NO2 Change SD (g),
   Seeds Agreeing (Traffic), Traffic Change SD (veh); Before and During are 8-seed
   means, Change is the mean of the within-seed paired differences.
   Command (from this worktree):
   python src/tableau_export.py paired --data-dir C:/dev/pta-realism/data/processed
     --graph C:/dev/pta-realism/data/network/graph_metro20k_orca.graphml
     --prefix fwrq --open-arm open --closed-arm rosequarter
     --seeds 42 7 13 99 314 777 2024 8 --scenario "I-5 SB, Rose Quarter"
     --changed-only --sheet rosequarter --out outputs/tableau/rosequarter_paired.xlsx
   Verified Sept 10: summing the mean change over the 31 I-405 route edges gives
   +244.0 g NO2 = +813 g NOx, I-205 +450 g, I-5 -122 g, identical to ledger section
   27/28. Sign agreement over the 64,331 changed segments: 724 at 8/8, 2,908 at 7/8.
   Inner-Portland box, magnitude >= 1 g, >= 7/8: 207 segments (145 at 8/8). Gainers
   there: I 405 +161 g (12 segments), I 5 +118 (11), Fremont Bridge +67; losers:
   North Lombard -197 (26), "I 5;US 30" -107 (the closed span), North Interstate
   -55, Banfield Freeway -42, Marquam Bridge -36. `_street` now falls back to the
   OSM `ref` when `name` is empty, so freeway mainlines read "I 405" instead of
   "(unnamed motorway)"; the published metro table predates this and is unchanged
   until re-exported.
   Display rule for the map: filter Seeds Agreeing (NO2) >= 7 (make it a parameter,
   6 to 8) and magnitude >= 1 g, box to inner Portland, color by NO2 Change capped,
   width by magnitude, the metro panel's conventions. The map is the campaign's
   output, not a graded prediction; the graded predictions are the corridor totals
   and the station directions, and the panel text says so.

2. `rosequarter_tables.xlsx`, 11 KB, built by `tableau_rosequarter.py`:
   python src/tableau_rosequarter.py --data-dir C:/dev/pta-realism/data/processed
     --stationmeta C:/dev/portland-traffic-abm/data/portal_rq/stationmeta.json
     --pairs C:/dev/portland-traveltime-log/pairs.json
     --out outputs/tableau/rosequarter_tables.xlsx
   Sheets: `corridors` (5 rows, RQ1 to RQ5 recomputed from the 16 summaries and
   asserted within 0.05 points of the ledger; verdict by prereg section 3, unanimous
   sign and |t| > 3: I-405 +84.9 sd 16.7 8/8 t 14.4 SUPPORTED, I-205 +3.1, I-5 -0.8,
   OR-213 +2.9, US-26 -0.6 all not at bar; Model column "base stack, mixed fleet"
   read from the summaries); `stations` (the 13 frozen PORTAL stations, lat/lon
   converted from the stationmeta.json Web Mercator cache, group and grading from
   rosequarter_score.GROUPS, direction wording from Appendix A.1; upstream = down but
   not graded, downstream = none registered); `routes` (12 logger pairs from
   pairs.json with the M.2 expectation and role, Frozen Rank = the improved-arm and
   fwrqe ordering of N.4/U.6, Frozen Rank (base arm) swaps the last two);
   `route_points` (24 rows, two per route, for line marks).

Panel plan, v1 (predictions only): the paired map (largest), corridor bars (mean %
with SD, labeled with seeds agreeing and verdict), the 13 stations colored by
registered direction with ungraded groups grayed, the 12 routes as lines colored by
expectation and labeled with rank, and a text panel: prereg pushed public Aug 14
(f76d27c) before any campaign task, Appendix A appended (8c185c0) with the frozen
sections byte-identical; base stack, mixed fleet, 16,500 vehicles, one steady-state
hour; caveats (local-access lane unmodeled, LODES 2021 demand plus a fixed 15%
through share with no evaporation or time shift, route once at free-flow and never
replan); "scoring in October under the registered rules; observed data appears here
only after it is banked". D1-D3 at most as a text line. The map and bars are the
base arm; the route rank is the improved-arm ordering, with the base-arm ordering as
its second column, and the panel says which is which.

### Second build of the same dashboard: the scripted page (Sept 10, built and verified)

Darcy asked for both builds so the two tools can be compared on the same data.
`src/rosequarter_page.py` reads the two exports above, the metro graph (segment
geometry, so segments draw as their real curves), and the s42 closure summary (the
5 removed edges), and writes one self-contained `outputs/web/rosequarter/index.html`
(163 KB, data inlined as JSON; Leaflet 1.9.4 from unpkg and OpenStreetMap tiles load
when viewed). Same captions and text panel as the Tableau plan, verbatim, zero em
dashes. Controls: seeds agreeing at least 6 / 7 / 8 (262 / 207 / 145 segments, the
count shown live), layer toggles for segments, stations, routes. Corridor bars are
plain HTML. Footer carries the build date, the generating commit, and the GitHub link
to the preregistration. Command: `python src/rosequarter_page.py --out
outputs/web/rosequarter/index.html` (about 25 s, the graph load). Verification the
script prints: 262 segments, 5 closed edges, 13 stations, 12 routes, 5 corridors,
corridor values 84.9 / 3.1 / 2.9 / -0.6 / -0.8, em dashes 0. Rendered check: headless
Chrome with a throwaway profile (`chrome.exe --headless=new --user-data-dir=<tmp>
--window-size=1300,1500 --screenshot=<png> file:///...`), never the interactive tab.
Two bugs found and fixed during the build: a global `</script>` escape corrupted the
Leaflet script tags (blank page), scoped to the JSON payload; the bar fill was an
inline span, which ignores width and height, so no bar drew (display: block). CARTO
Positron tiles now demand an API key, so the page uses OpenStreetMap tiles. Known
simplification for v2: the 12 routes are straight endpoint-to-endpoint lines
(pairs.json holds endpoints only), so the I-84 feeder reads as a line across NE
Portland; snapping each to the graph's shortest path would draw the road.
Build cost: one Sonnet agent, 11 minutes, about 150k tokens, plus the bar fix.

### The I-5 workbook itself: generated in code, published through the desktop app (Sept 11, DONE)

After the browser-driven stage 1 (one sheet, two hours), the rest of the workbook was
written as XML by `src/tableau_workbook.py` and published with `src/tableau_publish.py`.
Facts that made this possible and the rules learned, all verified Sept 11:

- Any published workbook downloads as a .twbx with no login:
  `https://public.tableau.com/workbooks/<RepoUrl>.twb`. A .twbx is a zip of one XML
  .twb plus Data/ (the Excel file and a .hyper extract). The stage-1 file is the
  template: its paired-map sheet, parameter, calculations, and extract are kept as is.
- The generator adds three data sources from rosequarter_tables.xlsx, each shipped as
  a .hyper extract written with pantab (`table=("Extract","Extract")`): Tableau Public
  refuses live connections even at load time ("workbooks saved to Tableau Public must
  use extracts"). It adds the Corridors bar sheet, the Stations map (MAKEPOINT on
  Geometry and Detail), the Routes map (MAKELINE between endpoints, rank as a string
  calc on Label so it reads "3" not "3.000"), the 1300 x 880 dashboard, and windows.
- XML rules the desktop validator enforced: `shelf-sorts` is not accepted, use
  `<sort class='computed' column=... direction='DESC' using=... />` after the
  datasource-dependencies; the `enable-sort-zone-taborder` dashboard attribute is not
  accepted; categorical colors live in the DATASOURCE `<style>` as
  `<encoding attr='color' field='[none:Field:nk]' type='palette'><map to='#hex'>
  <bucket>&quot;value&quot;</bucket></map>` AND that column-instance must be declared
  at the datasource level, or the palette is silently ignored; sheet titles need an
  explicit `<run fontsize='10'>` or they render huge inside dashboard zones; a
  `layout-flow` container re-flows children into even shares and ignores h/w, so the
  sheet grid sits in one `layout-basic` container with absolute x/y/w/h (hundred-
  thousandths of the dashboard); the parameter control zone's param needs the
  `[Parameters].` prefix or it shows Null; a text zone is one `<run>` with `&#10;`
  paragraph breaks (separate runs join inline).
- Publishing: Tableau Desktop Public Edition (free; the download server refuses
  scripted clients, the browser fetches it) opens the .twbx, validates it against a
  schema with every error listed at once, and File > Save to Tableau Public As with
  the existing title overwrites in place (Yes to the prompt), keeping the URL and the
  hidden flag. Sign-in happens once in the app with Remember me. A killed instance
  leaves a File Recovery offer on the next start: dismiss it, never open the backup.
- Result: revisions 1.1 to 1.4 on Sept 11, final 1.4 with the dashboard as the
  default view, still hidden; the hosted page checked with headless Chrome at each
  step (`chrome.exe --headless=new --screenshot=... "<viz URL>?:showVizHome=no&:embed=y"`).
  Every number on it is the export's: 207 marks at 7 of 8, bars 84.9 / 3.1 / 2.9 /
  -0.6 / -0.8, 13 stations, 12 routes.
- Cost: the whole code route, including the desktop-app publish loop, was a fraction
  of stage 1's browser bill; the loop is rebuild (seconds), open (60 s), publish (~1 min).
- Mistake to avoid: the first desktop publish accepted the dialog's default name and
  created a second, VISIBLE workbook "rosequarter_workbook" on the profile. Always set
  the title in the dialog; a duplicate has to be deleted by hand on the site.

Commands (from this worktree):
  python src/tableau_workbook.py --template <stage1.twbx> --tables outputs/tableau/rosequarter_tables.xlsx --out outputs/tableau/rosequarter_workbook.twbx
  python src/tableau_publish.py --twbx outputs/tableau/rosequarter_workbook.twbx --title "<exact title>" --repo <RepoUrl>

### Sept 11 afternoon review pass, both versions (workbook revision 1.7, commit 84d6c1c)

A six-hats read of the two I-5 dashboards through Christof's eyes, after a ChatGPT
review Darcy pasted (it never rendered the page; four of its seven points held, its
proposed headline misstated the I-205 call). Changes, applied to BOTH the workbook
generator and `rosequarter_page.py` so the versions stay comparable:

- A headline band in registered words leads the page (I-405 up strongly, all 8 seeds;
  I-205 up weakly, 4 of 8, not at the bar; locked on GitHub Aug 14; scored in October),
  with the closure dates and the predictions-only line under it. The generator asserts
  the headline's seed counts and verdicts against the corridors table before writing it.
- Each corridor row shows the seeds agreeing and the change in grams on the open-hour
  total next to the percent (Christof asked for absolute values in July; I-205's +450 g
  is not small in grams, only against its 16,333 g base).
- The corridor title says what "supported" means (the simulation bore out an
  expectation written before it ran; the real-world test is October's), because the red
  SUPPORTED reads as observational support at a glance.
- The map title glosses seeds (independent runs, different random starts) and NO2
  versus NOx (map colors NO2 = F_NO2 x NOx; bars NOx as registered).
- The October note says observed data are "not shown here until scoring is complete, so
  the predictions cannot be adjusted after seeing them" (not "withheld").
- A provenance footer: generating script and commit, preregistration path, tools, and
  the program's AI-assistance acknowledgment.
- Web page only: OSM basemap muted with a CSS filter on the tile pane; the twelve
  logger routes drawn as thin dashed chords with a legend line saying they join a
  trip's two ends and are not the driven path; a numpy-int payload bug fixed.

Tableau rules learned this pass (in addition to the list above):
- Parameter-control and legend zones render in compact form (title beside the control,
  truncated) below about 54 px; at 56 px the title sits on top in full.
- A long sheet title steals row height silently: the bars zone needs about 336 px for a
  six-line 10 pt title, a header row, five rows and the axis (322 px cut the fifth row).
- Rename a physical column for display with a datasource-level
  `<column caption='Seeds' ... name='[Seeds Agreeing]'>` (the `captions` map on
  `Source`); header space in a nested-rows table is tight.
- A string calc on Rows (`(Route / Seeds / Change (g))`) is the robust way to put text
  beside bars; mark labels overflow at the long bar and get hidden.
- `<run bold='true' fontsize='11'>` works in a text zone; a line break must sit inside
  the preceding run, text outside a run is dropped.
- `tableau_publish.py` now matches the app window on the workbook's file name (an
  unloaded workbook opens as Book1 and must never be published over the live one) and
  retries the title entry through UI Automation when typed keys are dropped.
- CARTO's light basemap stamps "API KEY REQUIRED" on tiles served to an unregistered
  page (Sept 11); OSM tiles plus a grayscale/opacity filter give the same muted look.

Hosted revisions 1.5 (subline and two rows clipped), 1.6 (fifth row still cut, legend
titles compact), 1.7 (clean, verified by headless-Chrome screenshot). Size 1300 x 1070.

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
- Rose Quarter predictions workbook: both tables come from `tableau_export.py paired`
  and `tableau_rosequarter.py` (section above); predictions only until October.
