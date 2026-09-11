"""Generate the Rose Quarter Tableau workbook (.twbx) from the published stage-1 file.

Why this exists: building sheets in Tableau Public's web editor by hand (or by a
browser-driving agent) cost about two hours and a large token bill for ONE sheet on
Sept 10 2026. A .twbx is just a zip holding an XML workbook (.twb) plus its data, so
the remaining sheets, the dashboard, the captions, and the text panel are written
here as XML, cloned from patterns Tableau itself wrote into the stage-1 workbook and
the earlier Powell workbook. The result opens in Tableau Desktop Public Edition,
whose only job is to validate it and press "Save to Tableau Public As".

Read-only over its inputs. Predictions only: the workbook shows the preregistered
predictions and says so; no observed closure data is connected (TABLEAU.md, "Rose
Quarter predictions workbook" rules).

Inputs:
  --template   the stage-1 .twbx downloaded from Tableau Public (it carries the paired
               map sheet, its extract, the parameter, and the calculated fields)
  --tables     outputs/tableau/rosequarter_tables.xlsx from tableau_rosequarter.py
  --out        the .twbx to write

The captions and the text panel are the plan's verbatim text (private notes,
TABLEAU_ROSEQUARTER_BUILD_PLAN.md sections 4 to 6); every number in them is a ledger
value that tableau_rosequarter.py asserts against the saved campaign files.
"""
import argparse
import os
import random
import re
import shutil
import string
import subprocess
import tempfile
import time
import uuid
import zipfile
from xml.sax.saxutils import escape

import pandas as pd

# ----------------------------------------------------------------------------- text
TITLE_MAP = ("Where the model says the pollution moves when I-5 southbound closes. Mean change "
             "over 8 paired seeds, inner Portland, segments changing by 1 g or more where at "
             "least 7 of 8 seeds agree on the direction (the menu sets 6, 7 or 8). Base model, "
             "mixed fleet, one steady-state hour. The map is the campaign's raw output; the "
             "graded predictions are the corridor totals and the station directions. Seeds are "
             "independent simulation runs with different random starts. Map colors are NO2 "
             "change in grams per segment over the hour (NO2 = {f_no2} x NOx, the project's "
             "convention); the corridor bars are NOx, as registered.")
TITLE_CORRIDORS = ("Registered corridor predictions: mean percent change in route NOx, 8 paired "
                   "seeds. I-405, the signed detour: up strongly, all 8 seeds agree, supported. "
                   "I-205, the regional detour: up weakly, 4 of 8 seeds, not at the bar. The "
                   "other routes sit inside seed noise. Verdict rule frozen before the run: "
                   "unanimous sign and |t| > 3. Supported means the simulation bore out an "
                   "expectation written before it ran; the real-world test is October's. Rows "
                   "show the seeds agreeing and the change in grams on the open-hour total.")
TITLE_STATIONS = ("The 13 PORTAL detector stations frozen for the October comparison, colored by "
                  "the registered direction of change. The two stations south of the I-84 merge "
                  "have no registered direction. The two upstream approach stations are expected "
                  "down but are not graded.")
TITLE_ROUTES = ("Twelve travel-time routes logged hourly since August 18, colored by the "
                "registered expectation. Numbers give the frozen October rank of modeled "
                "slowdowns (1 = largest): the I-5 to I-405 detour trip first, the closed-span "
                "trip second, the Vancouver commute third, then N Interstate, then MLK. Six "
                "routes are declared inside seed noise and take no rank.")
TEXT_PANEL = [
    "I-5 southbound closes at the Rose Quarter from September 11, 2026, for up to five weeks. "
    "This page shows what a traffic simulation predicted for that closure, registered before "
    "it happened.",
    "The predictions were written down and pushed to a public GitHub repository on August 14, "
    "2026, before any simulation task ran (commit f76d27c). Results were appended afterward "
    "with the registered sections unchanged (commit 8c185c0).",
    "The model: 16,500 vehicles on Portland's street network, run eight times with different "
    "random seeds, each seed once with I-5 southbound open and once with it closed on the same "
    "demand. Base driving model, mixed vehicle fleet, one steady-state hour.",
    "Registered predictions: I-405 southbound gains the most, up strongly (+84.9% NOx, all 8 "
    "seeds agree, supported). I-205 southbound up weakly (+3.1%, 4 of 8 seeds, not at the "
    "bar). The closed span falls to the local-access residual.",
    "Known limits, stated before the closure: the real one-lane local access is not modeled; "
    "demand is 2021 commute data plus a fixed 15% through share, with no trip evaporation, "
    "time shift, or mode shift; vehicles choose a route once at free-flow times and never "
    "replan.",
]
# The scoring sentence lives beside the bars, in the zone the October comparison will take.
TEXT_OCTOBER = ("Scoring happens in October against ODOT PORTAL loop detectors and an hourly "
                "travel-time log kept since August 18, under rules registered in advance: "
                "direction and rank of the changes, not absolute volumes. Observed closure data "
                "are not shown here until that scoring is complete, so the predictions cannot be "
                "adjusted after seeing them. This panel will then hold the predicted-versus-"
                "observed comparison, graded by the registered instruments, never by a "
                "calculation made here.")
# The headline band: the registered call in registered words, then the closure and the
# no-observed-data statement. main() checks the seed counts against the corridors table
# before writing them, so the headline cannot drift from the data.
HEADLINE = ("The prediction, registered before the closure: I-405 southbound up strongly (all 8 "
            "seeds agree). I-205 southbound up weakly (4 of 8 seeds, not at the bar). Locked on "
            "GitHub August 14, 2026; scored against real traffic in October.")
SUBLINE = ("I-5 southbound closed at the Rose Quarter from September 11, 2026, for up to five "
           "weeks. Predictions only: no observed closure data appear on this page until the "
           "October scoring.")
# The provenance footer (the program's AI-assistance acknowledgment lives here).
FOOTER = ("Generated from the saved simulation tables by src/tableau_workbook.py (commit {commit}) "
          "and published through Tableau Public; no number is typed by hand. Preregistration: "
          "github.com/darcy0408/portland-traffic-abm/blob/main/PREREG_I5_ROSEQUARTER.md. Tools: "
          "Python (OSMnx, NetworkX, pandas), Tableau Public. The code was written with AI "
          "assistance (Claude Code) and checked by the author.")
DASHBOARD = "Rose Quarter"
HEIGHT, WIDTH = 1030, 1300   # fixed dashboard size in pixels

# Colors keyed by the exact category strings the tables carry (tableau_rosequarter.py).
VERDICT_COLORS = {"SUPPORTED": "#b2182b", "not at bar": "#b7bdc4"}
DIRECTION_COLORS = {
    "down to the local-access residual": "#2166ac",
    "down (Appendix A.1 expectation, not graded)": "#92c5de",
    "none registered (context only)": "#999999",
    "up strongly": "#b2182b",
    "up weakly": "#f4a582",
}
EXPECTATION_COLORS = {
    "up": "#b2182b",
    "up weakly, may not clear the bar": "#f4a582",
    "about no change": "#999999",
    "no change": "#999999",
    "open question, either answer reported": "#7b3294",
    "no model comparison: endpoint outside the graph": "#cccccc",
}

TYPES = {"object": "string", "str": "string", "float64": "real", "int64": "integer", "bool": "boolean"}


def _id(n):
    """A random base-36 token like the ones Tableau writes into connection names."""
    return "".join(random.choice(string.digits + string.ascii_lowercase) for _ in range(n))


def attr(s):
    """Escape text for a single-quoted XML attribute (Tableau's own quoting style)."""
    return escape(s, {"'": "&apos;", '"': "&quot;"})


def col_type(series):
    """Tableau datatype for a pandas column; integer columns with NaN arrive as float."""
    return TYPES[str(series.dtype)]


# ------------------------------------------------------------------------ datasource
class Source:
    """One Excel sheet as a Tableau datasource. `calcs` are (name, caption, datatype,
    role, formula) tuples; `roles` maps column -> Tableau semantic role."""

    def __init__(self, sheet, df, xlsx_rel, calcs=(), geo=(), palette=None, captions=None):
        self.sheet, self.df, self.xlsx_rel, self.calcs, self.geo = sheet, df, xlsx_rel, calcs, geo
        self.palette = palette   # (field, {member: color}); Tableau keeps categorical colors here
        self.captions = captions or {}   # column -> short display name (header space is tight)
        self.name = "federated." + _id(28)
        self.conn = "excel-direct." + _id(28)
        self.obj = f"{sheet}_{uuid.uuid4().hex.upper()}"
        self.hyper = f"federated_{_id(22)}.hyper"   # the extract file, named like Tableau's

    def ref(self, field):
        return f"[{self.name}].[{field}]"

    def columns_xml(self):
        rows = [f"<column datatype='{col_type(self.df[c])}' name='{attr(c)}' ordinal='{i}' />"
                for i, c in enumerate(self.df.columns)]
        last = string.ascii_uppercase[len(self.df.columns) - 1]
        grid = f"A1:{last}{len(self.df) + 1}:no:A1:{last}{len(self.df) + 1}:0"
        return (f"<columns gridOrigin='{grid}' header='yes' outcome='6'>\n"
                + "\n".join("                  " + r for r in rows)
                + "\n                </columns>")

    def relation_xml(self):
        return (f"<relation connection='{self.conn}' name='{self.sheet}' "
                f"table='[{self.sheet}$]' type='table'>\n                {self.columns_xml()}\n"
                f"              </relation>")

    def field_defs(self):
        """<column> definitions the datasource carries: calcs and geographic roles."""
        out = []
        for name, caption, dtype, role, formula in self.calcs:
            out.append(f"      <column caption='{attr(caption)}' datatype='{dtype}' name='[{name}]' "
                       f"role='{role}' type='nominal'>\n"
                       f"        <calculation class='tableau' formula='{attr(formula)}' />\n"
                       f"      </column>")
        for c, kind in self.geo:
            out.append(f"      <column aggregation='Avg' datatype='real' name='[{c}]' role='measure' "
                       f"semantic-role='[Geographical].[{kind}]' type='quantitative' />")
        for c, cap in self.captions.items():   # a renamed physical column, Tableau's own pattern
            out.append(f"      <column caption='{attr(cap)}' datatype='{col_type(self.df[c])}' name='[{c}]' "
                       f"role='dimension' type='nominal' />")
        out.append(f"      <column caption='{self.sheet}' datatype='table' "
                   f"name='[__tableau_internal_object_id__].[{self.obj}]' role='measure' "
                   f"type='quantitative' />")
        if self.palette:   # the datasource-level palette needs its column-instance declared here
            f = self.palette[0]
            out.append(f"      <column-instance column='[{f}]' derivation='None' name='[none:{f}:nk]' "
                       f"pivot='key' type='nominal' />")
        return "\n".join(out)

    def write_extract(self, work):
        """Tableau Public refuses live connections even at load time ("workbooks saved to
        Tableau Public must use extracts"), so each small table ships as a .hyper extract
        written with pantab into the package's Data/Extracts folder, and the XML points at
        it exactly the way the template's own extract is wired."""
        import pantab
        os.makedirs(os.path.join(work, "Data", "Extracts"), exist_ok=True)
        pantab.frame_to_hyper(self.df, os.path.join(work, "Data", "Extracts", self.hyper),
                              table=("Extract", "Extract"))

    def style_xml(self):
        """Categorical color assignments live on the datasource (the template's pattern,
        field named without the datasource prefix); a worksheet-level palette is ignored."""
        if not self.palette:
            return "      <style />"
        field, colors = self.palette
        maps = "\n".join(f"            <map to='{c}'>\n              <bucket>&quot;{attr(v)}&quot;</bucket>\n            </map>"
                         for v, c in colors.items())
        return (f"      <style>\n        <style-rule element='mark'>\n"
                f"          <encoding attr='color' field='[none:{field}:nk]' type='palette'>\n{maps}\n"
                f"          </encoding>\n        </style-rule>\n      </style>")

    def extract_xml(self):
        now = time.strftime("%m/%d/%Y %I:%M:%S %p")
        return f"""      <extract count='-1' enabled='true' object-id='{self.obj}' units='records' user-specific='false'>
        <connection authentication='auth-none' author-locale='en_US' class='hyper' dbname='Data/Extracts/{self.hyper}' default-settings='yes' schema='Extract' tablename='Extract' update-time='{now}'>
          <relation name='Extract' table='[Extract].[Extract]' type='table' />
        </connection>
      </extract>"""

    def xml(self):
        return f"""    <datasource caption='{self.sheet} (rosequarter_tables)' inline='true' name='{self.name}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='rosequarter_tables' name='{self.conn}'>
            <connection class='excel-direct' cleaning='no' compat='no' dataRefreshTime='' filename='{self.xlsx_rel}' interpretationMode='0' password='' server='' validate='no' />
          </named-connection>
        </named-connections>
        {self.relation_xml()}
      </connection>
      <aliases enabled='yes' />
{self.field_defs()}
{self.extract_xml()}
      <layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />
{self.style_xml()}
      <semantic-values>
        <semantic-value key='[Country].[Name]' value='&quot;United States&quot;' />
      </semantic-values>
      <object-graph>
        <objects>
          <object caption='{self.sheet}' id='{self.obj}'>
            <properties context=''>
              {self.relation_xml()}
            </properties>
            <properties context='extract'>
              <relation name='Extract' table='[Extract].[Extract]' type='table' />
            </properties>
          </object>
        </objects>
      </object-graph>
    </datasource>
"""


# ------------------------------------------------------------------------- worksheets
def dep(src, dims=(), measures=(), calcs=(), geo=(), dim_calcs=()):
    """The <datasource-dependencies> block: every field a sheet touches, with its
    column-instance (the [none:X:nk] / [sum:X:qk] / [clct:X:nk] names the shelves use)."""
    lines = []
    for name, caption, dtype, role, formula in calcs:
        lines.append(f"<column caption='{attr(caption)}' datatype='{dtype}' name='[{name}]' role='{role}' type='nominal'>"
                     f"<calculation class='tableau' formula='{attr(formula)}' /></column>")
    for c in dims:
        cap = f" caption='{attr(src.captions[c])}'" if c in src.captions else ""
        lines.append(f"<column{cap} datatype='{col_type(src.df[c])}' name='[{c}]' role='dimension' type='nominal' />")
    for c in measures:
        lines.append(f"<column datatype='{col_type(src.df[c])}' name='[{c}]' role='measure' type='quantitative' />")
    for c, kind in geo:
        lines.append(f"<column aggregation='Avg' datatype='real' name='[{c}]' role='measure' "
                     f"semantic-role='[Geographical].[{kind}]' type='quantitative' />")
    for name, caption, dtype, role, formula in dim_calcs:   # string calcs used on Label
        lines.append(f"<column caption='{attr(caption)}' datatype='{dtype}' name='[{name}]' role='{role}' type='nominal'>"
                     f"<calculation class='tableau' formula='{attr(formula)}' /></column>")
        lines.append(f"<column-instance column='[{name}]' derivation='None' name='[none:{name}:nk]' pivot='key' type='nominal' />")
    for name, *_ in calcs:
        lines.append(f"<column-instance column='[{name}]' derivation='Collect' name='[clct:{name}:nk]' pivot='key' type='nominal' />")
    for c in dims:
        lines.append(f"<column-instance column='[{c}]' derivation='None' name='[none:{c}:nk]' pivot='key' type='nominal' />")
    for c in measures:
        lines.append(f"<column-instance column='[{c}]' derivation='Sum' name='[sum:{c}:qk]' pivot='key' type='quantitative' />")
    body = "\n".join("            " + l for l in lines)
    return f"          <datasource-dependencies datasource='{src.name}'>\n{body}\n          </datasource-dependencies>"


def palette(field, colors):
    maps = "\n".join(f"              <map to='{c}'>\n                <bucket>&quot;{attr(v)}&quot;</bucket>\n              </map>"
                     for v, c in colors.items())
    return (f"          <style-rule element='mark'>\n            <encoding attr='color' field='{field}' type='palette'>\n"
            f"{maps}\n            </encoding>\n          </style-rule>")


def title_xml(text, size=None):
    fs = f" fontsize='{size}'" if size else ""
    return (f"      <layout-options>\n        <title>\n          <formatted-text>\n"
            f"            <run{fs}>{escape(text)}</run>\n          </formatted-text>\n        </title>\n      </layout-options>")


def sheet_bar(src, grams_calc):
    """Corridors: one bar per route, sorted by the mean change, colored by verdict, labeled.
    The row header carries the seeds agreeing and the change in grams (a string calc) next
    to the route name, so the percent never stands alone: the absolute size was the review
    ask, and Christof asked for absolute values in July."""
    detail = ["Ledger ID", "Registered Prediction", "Model"]
    dims = ["Route", "Seeds Agreeing", "Verdict"] + detail
    measures = ["Mean Change (%)", "SD (%)", "t", "Mean Change (g NOx)", "Open Baseline (g NOx)"]
    r, m = src.ref("none:Route:nk"), src.ref("sum:Mean Change (%):qk")
    rows = f"({r} / {src.ref('none:Seeds Agreeing:nk')} / {src.ref(f'none:{grams_calc[0]}:nk')})"
    lods = "\n".join(f"              <lod column='{src.ref(f'none:{d}:nk')}' />" for d in detail)
    lods += "\n" + "\n".join(f"              <lod column='{src.ref(f'sum:{x}:qk')}' />" for x in measures[1:])
    return f"""    <worksheet name='Corridors'>
{title_xml(TITLE_CORRIDORS, 10)}
      <table>
        <view>
          <datasources>
            <datasource caption='{src.sheet} (rosequarter_tables)' name='{src.name}' />
          </datasources>
{dep(src, dims, measures, (), (), [grams_calc])}
          <sort class='computed' column='{r}' direction='DESC' using='{m}' />
          <aggregation value='true' />
        </view>
        <style />   <!-- colors come from the datasource-level palette -->

        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='Bar' />
            <encodings>
              <color column='{src.ref('none:Verdict:nk')}' />
              <text column='{m}' />
{lods}
            </encodings>
            <style>
              <style-rule element='mark'>
                <format attr='mark-labels-show' value='true' />
              </style-rule>
            </style>
          </pane>
        </panes>
        <rows>{rows}</rows>
        <cols>{m}</cols>
      </table>
      <simple-id uuid='{{{str(uuid.uuid4()).upper()}}}' />
    </worksheet>
"""


def sheet_map(name, title, src, calc, color_field, colors, dims, measures=(), label=None,
              mark="Automatic", label_calc=None):
    """A map sheet in the stage-1 pattern: a spatial calculation on Geometry and Detail,
    Latitude/Longitude (generated) on the axes, color by a category with a fixed palette."""
    calc_name = calc[0]
    lods = [f"<lod column='{src.ref(f'clct:{calc_name}:nk')}' />"]
    lods += [f"<lod column='{src.ref(f'none:{d}:nk')}' />" for d in dims if d != color_field]
    lods += [f"<lod column='{src.ref(f'sum:{x}:qk')}' />" for x in measures if x != label]
    text = f"\n              <text column='{src.ref(f'sum:{label}:qk')}' />" if label else ""
    if label_calc:
        text = f"\n              <text column='{src.ref(f'none:{label_calc[0]}:nk')}' />"
    label_style = ("\n            <style>\n              <style-rule element='mark'>\n"
                   "                <format attr='mark-labels-show' value='true' />\n"
                   "              </style-rule>\n            </style>") if (label or label_calc) else ""
    return f"""    <worksheet name='{name}'>
{title_xml(title, 10)}
      <table>
        <view>
          <datasources>
            <datasource caption='{src.sheet} (rosequarter_tables)' name='{src.name}' />
          </datasources>
          <mapsources>
            <mapsource name='Tableau' />
          </mapsources>
{dep(src, dims, measures, [calc], src.geo, [label_calc] if label_calc else [])}
          <aggregation value='true' />
        </view>
        <style>
          <style-rule element='map'>
            <format attr='washout' value='0.0' />
          </style-rule>
        </style>
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='{mark}' />
            <encodings>
              <color column='{src.ref(f'none:{color_field}:nk')}' />{text}
              <geometry column='{src.ref(f'clct:{calc_name}:nk')}' />
{chr(10).join('              ' + l for l in lods)}
            </encodings>{label_style}
          </pane>
        </panes>
        <rows>{src.ref('Latitude (generated)')}</rows>
        <cols>{src.ref('Longitude (generated)')}</cols>
      </table>
      <simple-id uuid='{{{str(uuid.uuid4()).upper()}}}' />
    </worksheet>
"""


# -------------------------------------------------------------------------- dashboard
ZSTYLE = """<zone-style>
                <format attr='border-color' value='#000000' />
                <format attr='border-style' value='none' />
                <format attr='border-width' value='0' />
                <format attr='margin' value='4' />
              </zone-style>"""


def zone(zid, x, y, w, h, body="", **kw):
    """Coordinates are hundred-thousandths of the dashboard (Tableau's unit)."""
    extra = "".join(f" {k.replace('_', '-')}='{attr(str(v))}'" for k, v in kw.items())
    return f"<zone h='{h}' id='{zid}' w='{w}' x='{x}' y='{y}'{extra}>\n{body}\n{ZSTYLE}\n</zone>"


def text_zone(zid, x, y, w, h, paragraphs, size):
    # One run; Tableau joins separate runs inline, so paragraph breaks are explicit newlines.
    text = "&#10;&#10;".join(escape(p) for p in paragraphs)
    body = f"<formatted-text>\n<run fontsize='{size}'>{text}</run>\n</formatted-text>"
    return zone(zid, x, y, w, h, body, type_v2="text", forceUpdate="true")


def rich_text_zone(zid, x, y, w, h, runs):
    """Runs of (text, size, bold), one per line: the line break sits inside the run that
    precedes it, because text outside a <run> is dropped."""
    parts = []
    for i, (text, size, bold) in enumerate(runs):
        b = " bold='true'" if bold else ""
        nl = "&#10;" if i < len(runs) - 1 else ""
        parts.append(f"<run{b} fontsize='{size}'>{escape(text)}{nl}</run>")
    body = "<formatted-text>\n" + "\n".join(parts) + "\n</formatted-text>"
    return zone(zid, x, y, w, h, body, type_v2="text", forceUpdate="true")


def dashboard_xml(paired_ds, param_name, param_col_xml, footer):
    """Fixed 1300 x 1004, four bands. The headline (the registered call, the closure, the
    no-observed-data line); row 1, the paired map (56%) beside a column holding the
    parameter control, the map's color legend, the corridor bars, and the October note;
    row 2, stations, routes, and the text panel; the provenance footer. Heights are
    planned in pixels and converted to Tableau's hundred-thousandths. The October note's
    zone is where the predicted-versus-observed sheet will go, so the layout does not
    move later."""
    P = 100000
    top, left, W, H = 909, 615, 98770, 98182          # the outer margin Tableau uses
    px = lambda n: int(H * n / HEIGHT)                # pixel height to dashboard units
    head_h, row1_h, row2_h = px(92), px(540), px(352)   # 92: two bold lines plus the subline
    foot_h = H - head_h - row1_h - row2_h
    map_w = int(W * 0.56)
    right_x, right_w = left + map_w, W - map_w
    head = rich_text_zone(101, left, top, W, head_h, [(HEADLINE, 11, True), (SUBLINE, 10, False)])
    y1 = top + head_h
    r1 = [zone(103, left, y1, map_w, row1_h, name="Paired Map")]
    # right column in pixels. The parameter control and the legend get their titles on
    # top (the 37 px compact versions truncated "Min Seeds Agreeing" and "NO2 Change (g)"
    # on the hosted page); the bars need the height for a six-line title plus five rows.
    ys, parts = y1, []
    for n, kind in ((48, "param"), (50, "legend"), (322, "bars"), (120, "note")):
        h = px(n)
        if kind == "param":
            parts.append(zone(104, right_x, ys, right_w, h, param=param_name, type_v2="paramctrl"))
        elif kind == "legend":
            parts.append(zone(105, right_x, ys, right_w, h, name="Paired Map", pane_specification_id="0",
                              param=f"[{paired_ds}].[sum:NO2 Change (g):qk]", type_v2="color"))
        elif kind == "bars":
            parts.append(zone(106, right_x, ys, right_w, h, name="Corridors"))
        else:
            parts.append(text_zone(107, right_x, ys, right_w, h, [TEXT_OCTOBER], 10))
        ys += h
    # Absolute placement inside ONE layout-basic container. A layout-flow container
    # re-flows its children into even shares and ignores these sizes (seen on the hosted
    # page Sept 11: the bars got 15% instead of 62%); layout-basic honors x/y/w/h, which
    # is how the Powell workbook stores its sheet grid.
    y2 = y1 + row1_h
    w3 = [int(W * 0.27), int(W * 0.27)]   # the text panel takes the remaining 46%
    w3.append(W - sum(w3))
    r2 = [zone(108, left, y2, w3[0], row2_h, name="Stations"),
          zone(109, left + w3[0], y2, w3[1], row2_h, name="Routes"),
          text_zone(110, left + w3[0] + w3[1], y2, w3[2], row2_h, TEXT_PANEL, 9)]
    foot = text_zone(111, left, y2 + row2_h, W, foot_h, [footer], 8)
    inner = zone(100, left, top, W, H, "\n".join([head] + r1 + parts + r2 + [foot]), type_v2="layout-basic")
    root = f"<zone h='{P}' id='99' type-v2='layout-basic' w='{P}' x='0' y='0'>\n{inner}\n{ZSTYLE.replace(chr(39)+'4'+chr(39), chr(39)+'8'+chr(39))}\n</zone>"
    return f"""  <dashboards>
    <dashboard name='{DASHBOARD}'>
      <style />
      <size maxheight='{HEIGHT}' maxwidth='{WIDTH}' minheight='{HEIGHT}' minwidth='{WIDTH}' sizing-mode='fixed' />
      <datasources>
        <datasource name='Parameters' />
      </datasources>
      <datasource-dependencies datasource='Parameters'>
{param_col_xml}
      </datasource-dependencies>
      <zones>
{root}
      </zones>
      <simple-id uuid='{{{str(uuid.uuid4()).upper()}}}' />
    </dashboard>
  </dashboards>
"""


def window_xml(name, kind="worksheet", sheets=(), active=0):
    if kind == "dashboard":   # the Powell workbook's pattern: one viewpoint per sheet, an active zone
        vps = "\n".join(f"        <viewpoint name='{s}' />" for s in sheets)
        return (f"    <window class='dashboard' maximized='true' name='{name}'>\n      <viewpoints>\n{vps}\n"
                f"      </viewpoints>\n      <active id='{active}' />\n"
                f"      <simple-id uuid='{{{str(uuid.uuid4()).upper()}}}' />\n    </window>\n")
    return f"""    <window class='worksheet' name='{name}'>
      <cards>
        <edge name='left'>
          <strip size='160'>
            <card type='pages' />
            <card type='filters' />
            <card type='marks' />
          </strip>
        </edge>
        <edge name='top'>
          <strip size='31'>
            <card type='columns' />
          </strip>
          <strip size='31'>
            <card type='rows' />
          </strip>
          <strip size='31'>
            <card type='title' />
          </strip>
        </edge>
      </cards>
      <simple-id uuid='{{{str(uuid.uuid4()).upper()}}}' />
    </window>
"""


# ------------------------------------------------------------------------------ main
def insert_before(text, anchor, block):
    assert text.count(anchor) == 1, f"anchor not unique: {anchor!r}"
    return text.replace(anchor, block + anchor)


# Tableau rejects any element or attribute whose format change is not declared in the
# workbook's document-format-change-manifest. The stage-1 template never sorted a shelf
# and had no dashboard, so its manifest lacks the entries that the sorted Corridors bars
# (<shelf-sorts>) and the dashboard (enable-sort-zone-taborder) need. The names are the
# ones the Powell workbook (same Tableau build) declares for the same XML. Found Sept 11
# 2026 when Desktop refused the first generated file with "no declaration found for
# element 'shelf-sorts'".
FEATURE_GATES = {
    "<shelf-sorts>": ["IntuitiveSorting", "IntuitiveSorting_SP2"],
    "enable-sort-zone-taborder=": ["AccessibleZoneTabOrder"],
}


def declare_features(twb, names):
    """Add manifest entries, keeping Tableau's order (sorted by feature name, with any
    _.fcp.<flag>.true... prefix ignored)."""
    m = re.search(r"  <document-format-change-manifest>\n(.*?)  </document-format-change-manifest>\n", twb, re.S)
    entries = [l.strip() for l in m.group(1).splitlines() if l.strip()]
    for n in names:
        if f"<{n} />" not in entries:
            entries.append(f"<{n} />")
    entries.sort(key=lambda e: e.split("...")[-1].strip("<> /"))
    block = ("  <document-format-change-manifest>\n" + "".join(f"    {e}\n" for e in entries)
             + "  </document-format-change-manifest>\n")
    return twb[:m.start()] + block + twb[m.end():]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", required=True, help="the stage-1 .twbx from Tableau Public")
    ap.add_argument("--tables", required=True, help="rosequarter_tables.xlsx")
    ap.add_argument("--out", required=True, help=".twbx to write")
    a = ap.parse_args()
    random.seed(20260911)   # reproducible connection ids for a given run of inputs

    work = tempfile.mkdtemp(prefix="rqtwb_")
    with zipfile.ZipFile(a.template) as z:
        z.extractall(work)
    twb_path = next(os.path.join(work, f) for f in os.listdir(work) if f.endswith(".twb"))
    twb = open(twb_path, encoding="utf-8").read()

    # The stage-1 datasource and parameter, found rather than assumed.
    paired_ds = re.search(r"<datasource caption='rosequarter \(rosequarter_paired\)' inline='true' name='([^']+)'", twb).group(1)
    param_col = re.search(r"(<column caption='Min Seeds Agreeing'[^>]*>\s*<calculation[^>]*/>\s*<members>.*?</members>\s*</column>)", twb, re.S).group(1)
    param_name = re.search(r"name='(\[Parameter [^\]]+\])'", param_col).group(1)
    param_col_xml = "\n".join("        " + l.strip() for l in param_col.splitlines())

    # The three small tables, copied into the package beside the paired file.
    xlsx_dir = os.path.join(work, "Data", "rq")
    os.makedirs(xlsx_dir, exist_ok=True)
    shutil.copy(a.tables, os.path.join(xlsx_dir, "rosequarter_tables.xlsx"))
    xlsx_rel = "Data/rq/rosequarter_tables.xlsx"
    x = pd.ExcelFile(a.tables)
    # The change in grams beside each bar, as text: "+813 g on 959 g open".
    grams_calc = ("Calculation_rqgrams", "Change (g)", "string", "dimension",
                  'IF [Mean Change (g NOx)] >= 0 THEN "+" ELSE "" END + STR(INT([Mean Change (g NOx)]))'
                  ' + " g on " + STR(INT([Open Baseline (g NOx)])) + " g open"')
    corridors = Source("corridors", x.parse("corridors"), xlsx_rel, calcs=[grams_calc],
                       palette=("Verdict", VERDICT_COLORS), captions={"Seeds Agreeing": "Seeds"})
    # The headline states seed counts and verdicts in words; check them against the table.
    cdf = corridors.df.set_index("Route")
    assert (cdf.loc["I-405", "Seeds Agreeing"], cdf.loc["I-405", "Verdict"]) == ("8/8", "SUPPORTED"), cdf.loc["I-405"]
    assert (cdf.loc["I-205", "Seeds Agreeing"], cdf.loc["I-205", "Verdict"]) == ("4/8", "not at bar"), cdf.loc["I-205"]
    # Provenance for the footer and the NO2 factor for the map title, both read, not typed.
    here = os.path.dirname(os.path.abspath(__file__))
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=here,
                            capture_output=True, text=True, check=True).stdout.strip()
    f_no2 = re.search(r"^F_NO2\s*=\s*([0-9.]+)", open(os.path.join(here, "..", "config.py"), encoding="utf-8").read(), re.M).group(1)
    st_calc = ("Calculation_rqstation", "Station Point", "spatial", "measure", "MAKEPOINT([Lat],[Lon])")
    stations = Source("stations", x.parse("stations"), xlsx_rel, calcs=[st_calc],
                      geo=[("Lat", "Latitude"), ("Lon", "Longitude")],
                      palette=("Registered Direction", DIRECTION_COLORS))
    rt_calc = ("Calculation_rqroute", "Route Line", "spatial", "measure",
               "MAKELINE(MAKEPOINT([From Lat],[From Lon]), MAKEPOINT([To Lat],[To Lon]))")
    # The rank is a decimal column with blanks; label it as a clean integer string.
    rank_calc = ("Calculation_rqrank", "Rank Label", "string", "dimension",
                 'IF ISNULL([Frozen Rank]) THEN "" ELSE STR(INT([Frozen Rank])) END')
    routes = Source("routes", x.parse("routes"), xlsx_rel, calcs=[rt_calc, rank_calc],
                    geo=[("From Lat", "Latitude"), ("To Lat", "Latitude"),
                         ("From Lon", "Longitude"), ("To Lon", "Longitude")],
                    palette=("Registered Expectation", EXPECTATION_COLORS))
    for s in (corridors, stations, routes):
        assert not any("—" in str(v) for v in s.df.values.ravel()), "em dash in data"
        s.write_extract(work)

    sheets = (sheet_bar(corridors, grams_calc)
              + sheet_map("Stations", TITLE_STATIONS, stations, st_calc, "Registered Direction",
                          DIRECTION_COLORS, ["Registered Direction", "Location", "Group", "Graded in October"],
                          ["Station ID", "Milepost"], mark="Circle")
              + sheet_map("Routes", TITLE_ROUTES, routes, rt_calc, "Registered Expectation",
                          EXPECTATION_COLORS, ["Registered Expectation", "Pair", "Name", "Why", "Role"],
                          ["Frozen Rank", "Frozen Rank (base arm)"], mark="Line", label_calc=rank_calc))

    # The template's map title has no size and renders huge inside a dashboard zone.
    assert twb.count("<run>Where the model says") == 1
    twb = twb.replace("<run>Where the model says", "<run fontsize='10'>Where the model says")
    # The stage-1 title, extended with the seeds gloss and the NO2-versus-NOx sentence.
    old_title = re.search(r"<run fontsize='10'>Where the model says.*?</run>", twb, re.S).group(0)
    twb = twb.replace(old_title, f"<run fontsize='10'>{escape(TITLE_MAP.format(f_no2=f_no2))}</run>")
    twb = insert_before(twb, "  </datasources>\n  <mapsources>", corridors.xml() + stations.xml() + routes.xml())
    twb = insert_before(twb, "  </worksheets>\n", sheets)
    twb = insert_before(twb, "  <windows>\n", dashboard_xml(paired_ds, f"[Parameters].{param_name}", param_col_xml,
                                                            FOOTER.format(commit=commit)))
    twb = insert_before(twb, "  </windows>\n", window_xml("Corridors") + window_xml("Stations")
                        + window_xml("Routes")
                        + window_xml(DASHBOARD, "dashboard",
                                     ["Corridors", "Paired Map", "Routes", "Stations"], active=103))
    # The published stage-1 sheet window was maximized; the dashboard should open instead.
    twb = twb.replace("<window class='worksheet' maximized='true' name='Paired Map'>",
                      "<window class='worksheet' name='Paired Map'>")
    # Declare every format change the added XML uses (see FEATURE_GATES).
    for marker, feats in FEATURE_GATES.items():
        if marker in twb:
            twb = declare_features(twb, feats)
    assert "—" not in twb, "em dash in workbook text"

    # Well-formedness, and every shelf reference resolves to a declared column-instance.
    import xml.etree.ElementTree as ET
    ET.fromstring(twb.encode("utf-8"))
    for ws in re.findall(r"<worksheet name='([^']+)'>(.*?)</worksheet>", twb, re.S):
        name, body = ws
        declared = set(re.findall(r"name='(\[(?:none|sum|clct)[^']+\])'", body))
        used = set(re.findall(r"\[federated\.[^\]]+\]\.(\[(?:none|sum|clct)[^\]]+\])", body))
        missing = used - declared
        assert not missing, f"{name}: shelf fields without a column-instance: {missing}"

    open(twb_path, "w", encoding="utf-8").write(twb)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(work):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, work))
    shutil.rmtree(work)
    print(f"wrote {a.out} ({os.path.getsize(a.out) / 1e6:.1f} MB): sheets Paired Map, Corridors, "
          f"Stations, Routes; dashboard '{DASHBOARD}' {WIDTH}x{HEIGHT}; datasources +3 (live Excel, "
          f"extracted on publish)")


if __name__ == "__main__":
    main()
