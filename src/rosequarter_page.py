"""Build the self-contained Rose Quarter predictions web page (a Leaflet map plus
two panels) from the saved simulation tables. This is the second of two builds of
the same dashboard, alongside the Tableau Public workbook src/tableau_export.py
already exported; both read the same files so the numbers on the two pages match.

Read-only over every input: this script never runs the simulation and never
downloads anything at build time (the page itself loads Leaflet and basemap tiles
from a CDN when a browser opens it). It reads the paired-campaign table
tableau_export.py already wrote, the small lookup tables that describe the
preregistered corridors/stations/routes, the cached OSMnx graph for segment
geometry, and the closure summary JSON for which edges were removed, then inlines
everything as JSON inside one index.html. No number on the page is typed by hand:
percentages, sums, counts, the git commit, and the build date are all computed
here at build time.

Usage (run from the repo root, i.e. this worktree):

  python src/rosequarter_page.py
      --out outputs/web/rosequarter/index.html
"""
import argparse
import json
import math
import os
import subprocess
import sys
from datetime import date

import osmnx as ox
import pandas as pd

# Repo-root config.py holds F_NO2 (NO2 = F_NO2 * NOx), used in the map caption
# below; read it from there instead of typing the fraction by hand.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# --- Fixed inputs (absolute paths from the build plan; override only for testing) ---
DEFAULT_PAIRED = (r"C:\dev\portland-traffic-abm\.claude\worktrees\tableau"
                   r"\outputs\tableau\rosequarter_paired.xlsx")
DEFAULT_TABLES = (r"C:\dev\portland-traffic-abm\.claude\worktrees\tableau"
                   r"\outputs\tableau\rosequarter_tables.xlsx")
DEFAULT_GRAPH = r"C:\dev\pta-realism\data\network\graph_metro20k_orca.graphml"
DEFAULT_SUMMARY = r"C:\dev\pta-realism\data\processed\fwrq_rosequarter_s42_summary.json"
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "outputs", "web", "rosequarter", "index.html")

# Selection rule for the map's colored segments (plan section 2): inner-Portland box,
# a real change, and enough seeds agreeing on its direction that it is not just
# single-seed demand-draw noise. The client-side radio then narrows further to 7 or 8.
BOX_LAT = (45.475, 45.595)
BOX_LON = (-122.75, -122.55)
MIN_MAGNITUDE_G = 1.0
MIN_SEEDS_AGREEING = 6

CLOSED_TOOLTIP = ("Closed: I-5 southbound, I-405 to I-84 "
                   "(3 mainline segments plus 2 stranded ramps)")

# The six verbatim paragraphs of the text panel (plan section 3). Typed once here,
# copied onto the page unchanged; every number inside them is the plan's own frozen
# prediction, not something this script recomputes.
TEXT_PANEL = [
    "I-5 southbound closes at the Rose Quarter from September 11, 2026, for up to "
    "five weeks. This page shows what a traffic simulation predicted for that "
    "closure, registered before it happened.",
    "The predictions were written down and pushed to a public GitHub repository on "
    "August 14, 2026, before any simulation task ran (commit f76d27c). Results were "
    "appended afterward with the registered sections unchanged (commit 8c185c0).",
    "The model: 16,500 vehicles on Portland's street network, run eight times with "
    "different random seeds, each seed once with I-5 southbound open and once with "
    "it closed on the same demand. Base driving model, mixed vehicle fleet, one "
    "steady-state hour.",
    "Registered predictions: I-405 southbound gains the most, up strongly (+84.9% "
    "NOx, all 8 seeds agree, supported). I-205 southbound up weakly (+3.1%, 4 of 8 "
    "seeds, not at the bar). The closed span falls to the local-access residual.",
    "Known limits, stated before the closure: the real one-lane local access is not "
    "modeled; demand is 2021 commute data plus a fixed 15% through share, with no "
    "trip evaporation, time shift, or mode shift; vehicles choose a route once at "
    "free-flow times and never replan.",
    "Scoring happens in October against ODOT PORTAL loop detectors and an hourly "
    "travel-time log kept since August 18, under rules registered in advance: "
    "direction and rank of the changes, not absolute volumes. Observed closure "
    "data are not shown here until that scoring is complete, so the predictions "
    "cannot be adjusted after seeing them.",
]

MAP_CAPTION = ("Where the model says the pollution moves when I-5 southbound "
               "closes. Mean change over 8 paired seeds, inner Portland, segments "
               "changing by 1 g or more where at least 7 of 8 seeds agree on the "
               "direction (the control sets 6, 7 or 8). Base model, mixed fleet, "
               "one steady-state hour. The map is the campaign's raw output: the "
               "graded predictions are the corridor totals and the station "
               "directions. Map colors are NO2 change in grams per segment over "
               f"the hour (NO2 = {config.F_NO2:.2f} x NOx, the convention used "
               "throughout the project); the corridor bars are NOx, as "
               "registered.")
CORRIDOR_CAPTION = ("Registered corridor predictions: mean percent change in route "
                     "NOx, 8 paired seeds. I-405, the signed detour: up strongly, "
                     "all 8 seeds agree, supported. I-205, the regional detour: up "
                     "weakly, 4 of 8 seeds, not at the bar. The other routes sit "
                     "inside seed noise. Verdict rule frozen before the run: "
                     "unanimous sign and |t| > 3. Supported means the simulation "
                     "bore out an expectation written before it ran; the "
                     "real-world test is October's.")
STATION_CAPTION = ("Stations: the 13 PORTAL detector stations frozen for the "
                    "October comparison, colored by the registered direction of "
                    "change. The two stations south of the I-84 merge have no "
                    "registered direction. The two upstream approach stations are "
                    "expected down but are not graded.")
ROUTE_CAPTION = ("Routes: twelve travel-time routes logged hourly since August 18, "
                  "colored by the registered expectation. Numbers give the frozen "
                  "October rank of modeled slowdowns (1 = largest): the I-5 to "
                  "I-405 detour trip first, the closed-span trip second, the "
                  "Vancouver commute third, then N Interstate, then MLK. Six "
                  "routes are declared inside seed noise and take no rank.")


def _num(x):
    """NaN-safe scalar for json.dumps: pandas NaN is not valid JSON, so it becomes
    JS null, which the tooltip code below renders as the word "none"."""
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    if isinstance(x, (int, float)):
        return x
    return str(x)


def edge_geometry(G, u, v, k):
    """[lat, lon] path for one directed edge. Curved edges carry a shapely
    LineString (x, y = lon, lat, the OSMnx convention); an edge without one is
    simplified to a straight line between its two node coordinates."""
    d = G.edges[u, v, k]
    if "geometry" in d and d["geometry"] is not None:
        return [[lat, lon] for lon, lat in d["geometry"].coords]
    nu, nv = G.nodes[u], G.nodes[v]
    return [[nu["y"], nu["x"]], [nv["y"], nv["x"]]]


def build_segments(paired_path):
    """The kept-segment table (plan section 2) plus, for each row, whether it
    clears the 7- or 8-seed thresholds the page's radio control switches between."""
    df = pd.read_excel(paired_path, sheet_name="rosequarter")
    box = df["Lat"].between(*BOX_LAT) & df["Lon"].between(*BOX_LON)
    mag = df["NO2 Change Magnitude (g)"] >= MIN_MAGNITUDE_G
    agree = df["Seeds Agreeing (NO2)"] >= MIN_SEEDS_AGREEING
    return df[box & mag & agree].copy()


def segment_features(sel, G):
    """One dict per kept segment: everything the map's tooltip and coloring need,
    plus geometry looked up from the graph by (U, V, Key). Column access is by
    name (not itertuples position) so it stays correct if the export ever adds
    or reorders a column."""
    out = []
    for _, row in sel.iterrows():
        out.append({
            "u": int(row["U"]), "v": int(row["V"]), "k": int(row["Key"]),
            "street": row["Street"], "road_type": row["Road Type"],
            "no2_before": round(float(row["NO2 Before (g)"]), 2),
            "no2_during": round(float(row["NO2 During Closure (g)"]), 2),
            "no2_change": round(float(row["NO2 Change (g)"]), 2),
            "no2_change_mag": round(float(row["NO2 Change Magnitude (g)"]), 2),
            "seeds_agreeing": int(row["Seeds Agreeing (NO2)"]),
            "sd": round(float(row["NO2 Change SD (g)"]), 2),
            "coords": edge_geometry(G, int(row["U"]), int(row["V"]), int(row["Key"])),
        })
    return out


def closed_feature(summary_path, G):
    """The 5 removed edges (plan's closure summary JSON, key 'removed') as one
    multi-part line feature sharing a single tooltip."""
    with open(summary_path) as f:
        removed = json.load(f)["removed"]
    parts = [edge_geometry(G, u, v, k) for u, v, k in removed]
    return {"coords": parts, "tooltip": CLOSED_TOOLTIP, "n_edges": len(removed)}


def build_stations(tables_path):
    df = pd.read_excel(tables_path, sheet_name="stations")
    out = []
    for _, row in df.iterrows():
        out.append({
            "station_id": _num(row["Station ID"]), "location": row["Location"],
            "group": row["Group"], "milepost": _num(row["Milepost"]),
            "lat": float(row["Lat"]), "lon": float(row["Lon"]),
            "direction": row["Registered Direction"], "graded": row["Graded in October"],
        })
    return out


def build_routes(tables_path):
    """Merge the 12-row route metadata onto the 24-row route_points table: group the
    points by Pair, order by Point Order for the polyline, and take the metadata from
    the one-row-per-pair sheet (avoids trusting float-for-float duplication across the
    24 point rows)."""
    routes = pd.read_excel(tables_path, sheet_name="routes").set_index("Pair")
    points = pd.read_excel(tables_path, sheet_name="route_points").sort_values(
        ["Pair", "Point Order"])
    out = []
    for pair, grp in points.groupby("Pair", sort=False):
        r = routes.loc[pair]
        coords = list(zip(grp["Lat"].astype(float), grp["Lon"].astype(float)))
        coords = [[lat, lon] for lat, lon in coords]
        mid = [sum(c[0] for c in coords) / len(coords),
               sum(c[1] for c in coords) / len(coords)]
        out.append({
            "pair": pair, "name": r["Name"], "why": r["Why"],
            "expectation": r["Registered Expectation"], "role": r["Role"],
            "frozen_rank": _num(r["Frozen Rank"]),
            "frozen_rank_base": _num(r["Frozen Rank (base arm)"]),
            "coords": coords, "mid": mid,
        })
    return out


def build_corridors(tables_path):
    """The corridor-bar rows. The two lines of bar text (change 3) are formatted
    here, not in the page's JS, so the finished, comma-grouped numbers land in
    the embedded JSON as plain text (e.g. "16,333 g") rather than only existing
    after a browser runs toLocaleString() on the raw ints."""
    df = pd.read_excel(tables_path, sheet_name="corridors")
    df = df.sort_values("Mean Change (%)", ascending=False)
    out = []
    for _, row in df.iterrows():
        pct = round(float(row["Mean Change (%)"]), 1)
        # int(), not _num(): these columns are whole grams (numpy int64), and
        # _num()'s isinstance(x, (int, float)) check misses numpy's own int
        # type, which would otherwise silently stringify them for JSON.
        grams = int(row["Mean Change (g NOx)"])
        baseline = int(row["Open Baseline (g NOx)"])
        verdict = row["Verdict"]
        supported = str(verdict).strip().upper() == "SUPPORTED"
        seeds_agreeing = row["Seeds Agreeing"]  # already "8/8" style text
        verdict_text = "supported by the simulation" if supported else "not at the bar"
        pct_sign = "+" if pct >= 0 else ""
        gram_sign = "+" if grams >= 0 else ""
        out.append({
            "route": row["Route"], "ledger_id": row["Ledger ID"],
            "registered_prediction": row["Registered Prediction"],
            "mean_change_pct": pct,
            "sd_pct": round(float(row["SD (%)"]), 1),
            "seeds_agreeing": seeds_agreeing,
            "t": round(float(row["t"]), 1),
            "verdict": verdict,
            "mean_change_nox_g": grams,
            "open_baseline_nox_g": baseline,
            "bar_line1": (f"{pct_sign}{pct}%, {seeds_agreeing.replace('/', ' of ')}, "
                           f"{verdict_text}"),
            "bar_line2": (f"{gram_sign}{grams:,} g on {baseline:,} g open "
                           "(NOx, one hour)"),
        })
    return out


def build_headline(corridors):
    """The one-line registered-prediction summary shown above the subtitle
    (change 1). The seed counts are parsed from the corridors table's own
    "Seeds Agreeing" text (e.g. "8/8", "4/8") instead of being typed by hand,
    and a verdict or seed-count mismatch is a hard error rather than a
    silently wrong headline."""
    by_route = {c["route"]: c for c in corridors}
    i405, i205 = by_route["I-405"], by_route["I-205"]
    if i405["verdict"].strip().upper() != "SUPPORTED":
        raise ValueError(
            f"I-405 verdict is {i405['verdict']!r}, expected SUPPORTED; the "
            "headline text assumes this corridor cleared the bar."
        )
    if i205["verdict"].strip().lower() != "not at bar":
        raise ValueError(
            f"I-205 verdict is {i205['verdict']!r}, expected 'not at bar'; the "
            "headline text assumes this corridor did not clear the bar."
        )
    i405_agree, i405_total = i405["seeds_agreeing"].split("/")
    i205_agree, i205_total = i205["seeds_agreeing"].split("/")
    if i405_agree != i405_total:
        raise ValueError(
            f"I-405 Seeds Agreeing is {i405['seeds_agreeing']!r}, not "
            "unanimous; the headline text says 'all N seeds agree'."
        )
    return (
        "The prediction, registered before the closure: I-405 southbound up "
        f"strongly (all {i405_total} seeds agree). I-205 southbound up weakly "
        f"({i205_agree} of {i205_total} seeds, not at the bar). Locked on "
        "GitHub August 14, 2026; scored against real traffic in October."
    )


def git_fact(worktree, args):
    """Short commit hash and the origin URL rewritten to https, for the footer's
    build stamp and the preregistration link."""
    out = subprocess.run(["git", "-C", worktree] + args, capture_output=True,
                          text=True, check=True)
    return out.stdout.strip()


def origin_to_https(url):
    """git@host:owner/repo.git -> https://host/owner/repo (already-https origins
    just lose a trailing .git)."""
    if url.startswith("git@"):
        host, path = url[len("git@"):].split(":", 1)
        url = f"https://{host}/{path}"
    if url.endswith(".git"):
        url = url[:-4]
    return url


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>When I-5 Closes: Preregistered Predictions for the Rose Quarter Closure</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root {{
  --ink: #1b1f24; --muted: #5b6572; --line: #d9dee3; --paper: #ffffff;
  --red: #b2182b; --blue: #2166ac; --gray: #8a94a0;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 24px; background: #f4f5f7; color: var(--ink);
  font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.45;
}}
.page {{ max-width: 1300px; margin: 0 auto; }}
header h1 {{ font-size: 1.5rem; margin: 0 0 4px 0; }}
header .headline {{ font-size: 1.05rem; font-weight: 500; margin: 0 0 6px 0; }}
header .subtitle {{ color: var(--muted); margin: 0 0 18px 0; }}
.layout {{ display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start; }}
.mapcol {{ flex: 1 1 62%; min-width: 340px; }}
.panelcol {{ flex: 1 1 34%; min-width: 300px; }}
@media (max-width: 900px) {{ .mapcol, .panelcol {{ flex: 1 1 100%; }} }}
.controls {{
  display: flex; flex-wrap: wrap; gap: 16px; align-items: center;
  background: var(--paper); border: 1px solid var(--line); border-radius: 8px;
  padding: 10px 14px; margin-bottom: 10px; font-size: 0.9rem;
}}
.controls fieldset {{ border: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
.controls legend {{ font-weight: 600; padding: 0; float: left; margin-right: 8px; }}
.controls label {{ white-space: nowrap; }}
.seeds-note {{ flex-basis: 100%; color: var(--muted); font-size: 0.78rem; margin-top: 2px; }}
#map {{ height: 560px; width: 100%; border: 1px solid var(--line); border-radius: 8px; }}
.caption {{ color: var(--muted); font-size: 0.85rem; margin: 8px 0; }}
.legend {{
  background: var(--paper); border: 1px solid var(--line); border-radius: 8px;
  padding: 10px 14px; margin-top: 10px; font-size: 0.82rem; display: flex;
  flex-wrap: wrap; gap: 18px;
}}
.legend .swatch {{
  display: inline-block; width: 12px; height: 12px; border-radius: 50%;
  margin-right: 5px; vertical-align: middle; border: 1.5px solid #333;
}}
.legend .ramp {{
  display: inline-block; width: 120px; height: 10px; vertical-align: middle;
  background: linear-gradient(to right, var(--blue), #f7f7f7, var(--red));
  border: 1px solid #999; margin: 0 6px;
}}
.legend .dashline {{
  display: inline-block; width: 34px; height: 0; margin-right: 5px;
  vertical-align: middle; border-top: 2px dashed var(--gray);
}}
section.panel {{
  background: var(--paper); border: 1px solid var(--line); border-radius: 8px;
  padding: 14px 16px; margin-bottom: 16px;
}}
section.panel h2 {{ font-size: 1.05rem; margin: 0 0 10px 0; }}
.bar-row {{ display: flex; align-items: center; gap: 8px; margin-bottom: 10px; font-size: 0.85rem; }}
.bar-label {{ width: 60px; font-weight: 600; }}
.bar-track {{ flex: 1; background: #eee; border-radius: 3px; height: 16px; position: relative; }}
.bar-fill {{ display: block; height: 100%; border-radius: 3px; }}  /* block, an inline span ignores width and height */
.bar-text {{ width: 300px; color: var(--muted); }}
.bar-text .bar-line1 {{ display: block; color: var(--ink); }}
.bar-text .bar-line2 {{ display: block; font-size: 0.78rem; color: var(--muted); margin-top: 1px; }}
.text-panel p {{ margin: 0 0 12px 0; font-size: 0.92rem; }}
.text-panel p:last-child {{ margin-bottom: 0; }}
footer {{ color: var(--muted); font-size: 0.82rem; margin-top: 18px; }}
footer a {{ color: inherit; }}
</style>
</head>
<body>
<div class="page">
<header>
  <h1>When I-5 Closes: Preregistered Predictions for the Rose Quarter Closure</h1>
  <p class="headline">{headline}</p>
  <p class="subtitle">Predictions only. Scoring in October under rules registered in advance.</p>
</header>
<main>
<div class="layout">
  <div class="mapcol">
    <div class="controls">
      <fieldset>
        <legend>Seeds agreeing</legend>
        <label><input type="radio" name="minagree" value="6"> at least 6</label>
        <label><input type="radio" name="minagree" value="7" checked> at least 7</label>
        <label><input type="radio" name="minagree" value="8"> at least 8</label>
        <div class="seeds-note">Seeds are independent simulation runs with different random starts. A segment shows only when at least 6, 7 or 8 of the 8 runs agree on the direction of its change.</div>
      </fieldset>
      <span><strong id="seg-count"></strong> segments shown</span>
      <fieldset>
        <legend>Layers</legend>
        <label><input type="checkbox" id="toggle-segments" checked> Segments</label>
        <label><input type="checkbox" id="toggle-stations" checked> Stations</label>
        <label><input type="checkbox" id="toggle-routes" checked> Routes</label>
      </fieldset>
    </div>
    <div id="map"></div>
    <div class="legend">
      <span>NO2 change (g): <span class="ramp"></span> -20 &nbsp; 0 &nbsp; +20</span>
      <span><span class="swatch" style="background:#2166ac;border-color:#2166ac"></span>down</span>
      <span><span class="swatch" style="background:#8b0000;border-color:#8b0000"></span>up strongly</span>
      <span><span class="swatch" style="background:#e07b00;border-color:#e07b00"></span>up weakly</span>
      <span><span class="swatch" style="background:#fff;border-color:#8a94a0"></span>not graded or none registered</span>
      <span><span class="dashline"></span>logged trip: straight line between its two ends, not the driven path</span>
    </div>
    <p class="caption">{map_caption}</p>
    <p class="caption">{station_caption}</p>
    <p class="caption">{route_caption}</p>
  </div>
  <div class="panelcol">
    <section class="panel">
      <h2>Registered corridor predictions</h2>
      <div id="bars"></div>
      <p class="caption">{corridor_caption}</p>
    </section>
    <section class="panel text-panel">
      {text_paragraphs}
    </section>
  </div>
</div>
</main>
<footer>
  <p>Built {build_date} from the saved simulation files by src/rosequarter_page.py at commit {commit}. No number on this page is typed by hand.</p>
  <p>Tools: Python (OSMnx, NetworkX, pandas), Leaflet and OpenStreetMap data with CARTO tiles. The code was written with AI assistance (Claude Code) and checked by the author; every number is read from the saved simulation tables.</p>
  <p><a href="{prereg_url}">Preregistration (GitHub)</a></p>
</footer>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const DATA = {data_json};

// --- map ---
const map = L.map('map').setView([45.5355, -122.6690], 12);
// CARTO Positron: a muted, light basemap so the red/blue NO2 segments dominate.
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
  subdomains: 'abcd',
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
}}).addTo(map);

const segLayer = L.layerGroup().addTo(map);
const closedLayer = L.layerGroup().addTo(map);
const stationLayer = L.layerGroup().addTo(map);
const routeLayer = L.layerGroup().addTo(map);

// diverging color scale, capped at +/-20 g NO2 change
function lerp(a, b, t) {{ return a + (b - a) * t; }}
function colorForChange(v) {{
  const cap = 20;
  const c = Math.max(-cap, Math.min(cap, v));
  const neg = [33, 102, 172], mid = [247, 247, 247], pos = [178, 24, 43];
  let stop0, stop1, t;
  if (c <= 0) {{ stop0 = neg; stop1 = mid; t = (c + cap) / cap; }}
  else {{ stop0 = mid; stop1 = pos; t = c / cap; }}
  const rgb = [0, 1, 2].map(i => Math.round(lerp(stop0[i], stop1[i], t)));
  return `rgb(${{rgb[0]}},${{rgb[1]}},${{rgb[2]}})`;
}}
function weightForMag(mag) {{
  const m = Math.max(1, Math.min(20, mag));
  return 2 + (m - 1) / 19 * 6;
}}

function segTooltip(s) {{
  return `<b>${{s.street}}</b> (${{s.road_type}})<br>` +
    `NO2 change: ${{s.no2_change.toFixed(2)}} g (before ${{s.no2_before.toFixed(2)}} g, during ${{s.no2_during.toFixed(2)}} g)<br>` +
    `Seeds agreeing: ${{s.seeds_agreeing}}/8, SD ${{s.sd.toFixed(2)}} g`;
}}

function renderSegments(minAgree) {{
  segLayer.clearLayers();
  let n = 0;
  DATA.segments.forEach(s => {{
    if (s.seeds_agreeing >= minAgree) {{
      n++;
      L.polyline(s.coords, {{
        color: colorForChange(s.no2_change),
        weight: weightForMag(s.no2_change_mag),
        opacity: 0.85
      }}).bindTooltip(segTooltip(s)).addTo(segLayer);
    }}
  }});
  document.getElementById('seg-count').textContent = n;
}}
renderSegments(7);
document.querySelectorAll('input[name="minagree"]').forEach(r => {{
  r.addEventListener('change', e => renderSegments(parseInt(e.target.value, 10)));
}});

// closed edges: one multi-part dashed black line, one tooltip
L.polyline(DATA.closed.coords, {{
  color: '#000000', weight: 5, dashArray: '8,6', opacity: 0.9
}}).bindTooltip(DATA.closed.tooltip).addTo(closedLayer);

// stations: color by Registered Direction, hollow gray if not graded
function stationStyle(s) {{
  if (s.graded !== 'yes') {{ return {{ color: '#8a94a0', fill: false }}; }}
  const dir = s.direction;
  if (dir.indexOf('down') !== -1) {{ return {{ color: '#2166ac', fill: true, fillColor: '#2166ac' }}; }}
  if (dir.indexOf('up strongly') !== -1) {{ return {{ color: '#8b0000', fill: true, fillColor: '#8b0000' }}; }}
  if (dir.indexOf('up weakly') !== -1) {{ return {{ color: '#e07b00', fill: true, fillColor: '#e07b00' }}; }}
  return {{ color: '#8a94a0', fill: false }};
}}
DATA.stations.forEach(s => {{
  const st = stationStyle(s);
  L.circleMarker([s.lat, s.lon], {{
    radius: 7, color: st.color, weight: 2,
    fill: st.fill, fillColor: st.fillColor || '#ffffff',
    fillOpacity: st.fill ? 0.85 : 0
  }}).bindTooltip(
    `<b>${{s.location}}</b><br>${{s.group}}<br>` +
    `Registered direction: ${{s.direction}}<br>` +
    `Graded in October: ${{s.graded}}`
  ).addTo(stationLayer);
}});

// routes: color by Registered Expectation, dashed for the excluded logger-side control
function routeStyle(r) {{
  if (r.role === 'logger-side control') {{ return {{ color: '#c9ced4', dashArray: '4,6' }}; }}
  const exp = r.expectation;
  if (exp.indexOf('up weakly') !== -1) {{ return {{ color: '#e07b00', dashArray: null }}; }}
  if (exp === 'up') {{ return {{ color: '#b2182b', dashArray: null }}; }}
  if (exp.indexOf('open question') !== -1) {{ return {{ color: '#7b3fa0', dashArray: null }}; }}
  return {{ color: '#8a94a0', dashArray: null }};  // about no change / no change
}}
DATA.routes.forEach(r => {{
  const st = routeStyle(r);
  // Thin and dashed on purpose: these are straight lines between two logged
  // points, not the driven path, and the dashing says so at a glance (legend).
  L.polyline(r.coords, {{ color: st.color, weight: 2, dashArray: '6,6', opacity: 0.8 }})
    .bindTooltip(
      `<b>${{r.name}}</b><br>${{r.why}}<br>` +
      `Registered expectation: ${{r.expectation}}<br>` +
      `Role: ${{r.role}}<br>` +
      `Frozen rank: ${{r.frozen_rank === null ? 'none' : r.frozen_rank}} ` +
      `(base arm: ${{r.frozen_rank_base === null ? 'none' : r.frozen_rank_base}})`
    ).addTo(routeLayer);
  if (r.frozen_rank !== null) {{
    L.marker(r.mid, {{
      icon: L.divIcon({{
        className: 'rank-badge',
        html: `<div style="background:#1b1f24;color:#fff;border-radius:50%;width:20px;height:20px;` +
              `display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:600;">` +
              `${{Math.round(r.frozen_rank)}}</div>`,
        iconSize: [20, 20], iconAnchor: [10, 10]
      }})
    }}).addTo(routeLayer);
  }}
}});

document.getElementById('toggle-segments').addEventListener('change', e => {{
  if (e.target.checked) {{ segLayer.addTo(map); closedLayer.addTo(map); }}
  else {{ map.removeLayer(segLayer); map.removeLayer(closedLayer); }}
}});
document.getElementById('toggle-stations').addEventListener('change', e => {{
  if (e.target.checked) {{ stationLayer.addTo(map); }} else {{ map.removeLayer(stationLayer); }}
}});
document.getElementById('toggle-routes').addEventListener('change', e => {{
  if (e.target.checked) {{ routeLayer.addTo(map); }} else {{ map.removeLayer(routeLayer); }}
}});

// --- corridor bars ---
const maxAbs = Math.max(...DATA.corridors.map(c => Math.abs(c.mean_change_pct)));
const bars = document.getElementById('bars');
DATA.corridors.forEach(c => {{
  const pos = c.mean_change_pct >= 0;
  const supported = c.verdict.toUpperCase() === 'SUPPORTED';
  const color = supported ? (pos ? '#b2182b' : '#2166ac') : '#b7bdc4';
  const pct = Math.abs(c.mean_change_pct) / maxAbs * 100;
  const row = document.createElement('div');
  row.className = 'bar-row';
  row.title = `Ledger ID: ${{c.ledger_id}}\\nSD: ${{c.sd_pct}}%\\nt: ${{c.t}}\\n` +
    `Registered prediction: ${{c.registered_prediction}}\\n` +
    `Mean change: ${{c.mean_change_nox_g}} g NOx\\nOpen baseline: ${{c.open_baseline_nox_g}} g NOx`;
  // bar_line1 / bar_line2 are pre-formatted in build_corridors (Python), so the
  // comma-grouped numbers are plain text in the page, not only produced by
  // running this script in a browser.
  row.innerHTML = `<span class="bar-label">${{c.route}}</span>` +
    `<span class="bar-track"><span class="bar-fill" style="width:${{pct}}%;background:${{color}}"></span></span>` +
    `<span class="bar-text">` +
      `<span class="bar-line1">${{c.bar_line1}}</span>` +
      `<span class="bar-line2">${{c.bar_line2}}</span>` +
    `</span>`;
  bars.appendChild(row);
}});
</script>
</body>
</html>
"""


def render(payload, commit, prereg_url, headline):
    text_paragraphs = "\n      ".join(f"<p>{p}</p>" for p in TEXT_PANEL)
    # Guard only the embedded JSON against a street/route name that happens to
    # contain "</script": escaping the whole rendered page would also mangle the
    # real closing tags around the Leaflet <script> elements.
    data_json = json.dumps(payload, separators=(",", ":")).replace("</script", "<\\/script")
    return PAGE_TEMPLATE.format(
        headline=headline,
        map_caption=MAP_CAPTION,
        station_caption=STATION_CAPTION,
        route_caption=ROUTE_CAPTION,
        corridor_caption=CORRIDOR_CAPTION,
        text_paragraphs=text_paragraphs,
        build_date=date.today().isoformat(),
        commit=commit,
        prereg_url=prereg_url,
        data_json=data_json,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--paired", default=DEFAULT_PAIRED)
    ap.add_argument("--tables", default=DEFAULT_TABLES)
    ap.add_argument("--graph", default=DEFAULT_GRAPH)
    ap.add_argument("--summary", default=DEFAULT_SUMMARY)
    ap.add_argument("--worktree",
                     default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     help="repo checkout to read git facts (commit, origin) from")
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()

    print(f"loading graph from {a.graph} ...")
    G = ox.load_graphml(a.graph)
    print(f"  {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges")

    sel = build_segments(a.paired)
    segments = segment_features(sel, G)
    closed = closed_feature(a.summary, G)
    stations = build_stations(a.tables)
    routes = build_routes(a.tables)
    corridors = build_corridors(a.tables)

    commit = git_fact(a.worktree, ["rev-parse", "--short", "HEAD"])
    origin = origin_to_https(git_fact(a.worktree, ["remote", "get-url", "origin"]))
    prereg_url = f"{origin}/blob/main/PREREG_I5_ROSEQUARTER.md"

    payload = {
        "segments": segments, "closed": closed, "stations": stations,
        "routes": routes, "corridors": corridors,
    }
    headline = build_headline(corridors)
    html = render(payload, commit, prereg_url, headline)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(html)

    # --- verification summary (build plan section 4) ---
    n7 = sum(1 for s in segments if s["seeds_agreeing"] >= 7)
    n8 = sum(1 for s in segments if s["seeds_agreeing"] >= 8)
    total_change = sum(s["no2_change"] for s in segments)
    print(f"wrote {a.out}")
    print(f"segments embedded: {len(segments)} (>=6); >=7: {n7}; >=8: {n8}")
    print(f"closed edges: {closed['n_edges']}")
    print(f"stations: {len(stations)}")
    print(f"routes: {len(routes)} (from route_points groups)")
    print(f"corridors: {len(corridors)}")
    print(f"sum of NO2 Change (g) over embedded segments: {total_change:.2f}")
    print("corridor mean change (%):")
    for c in corridors:
        print(f"  {c['route']:<8} {c['mean_change_pct']:+.1f}")
    em_dash_count = html.count("\u2014")
    print(f"em dash occurrences in output: {em_dash_count}")


if __name__ == "__main__":
    main()
