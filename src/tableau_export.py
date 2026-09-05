"""Export saved simulation results as flat tables for the Tableau Public dashboard.

Read-only: this script never runs the simulation. It reads the per-segment parquet
files generate.py already wrote, joins them to the cached street graph for names and
coordinates, and writes CSV (or .xlsx, which Tableau's upload cap prefers). That keeps
the dashboard on the single-source-of-truth rule: every number a viewer hovers comes
from the same files the figures and the ledger use.

Three subcommands:

  closure     one before/after pair -> one table (the Powell corridor or metro map)
  scenarios   several closed runs against ONE shared open baseline -> one table with a
              Scenario column, for the dropdown menu
  validation  the held-out count comparison -> the scatter table (rank percentiles)

Column names are fixed to what the published workbook already binds to, so a re-upload
refreshes the extract without rebuilding sheets. Do not rename them casually.

Examples (run from the repo root):

  # corridor pair, main's data and graph (defaults from config)
  python src/tableau_export.py closure --open powell_through_open --closed powell_through_closed
      --scenario "SE Powell (corridor)" --out outputs/tableau/powell_closure.csv

  # metro pair, read from the metro worktree (the data lives there, see RESULTS_LEDGER sec. 2)
  python src/tableau_export.py closure --data-dir <metro>/data/processed
      --graph <metro>/data/network/graph.graphml
      --open metro20k_open --closed metro20k_closed --scenario "SE Powell"
      --out outputs/tableau/metro_closure.csv

  # scenario menu: NAME=RUN pairs, every one diffed against --open
  python src/tableau_export.py scenarios --data-dir ... --graph ... --open metro20k_open
      "SE Powell=metro20k_closed" "SE Division=scn_division_closed" --changed-only
      --out outputs/tableau/metro_scenarios.xlsx

  python src/tableau_export.py validation --run powell_through
      --out outputs/tableau/powell_validation_scatter.csv
"""
import argparse
import os
import sys

import osmnx as ox
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Tableau binds sheets to these exact headers; the published workbook uses them.
COLS = ["U", "V", "Key", "Street", "Road Type",
        "Lat U", "Lon U", "Lat V", "Lon V", "Lat", "Lon",
        "NO2 Before (g)", "NO2 During Closure (g)", "NO2 Change (g)",
        "NO2 Change Magnitude (g)",
        "Traffic Before (veh)", "Traffic During (veh)", "Traffic Change (veh)"]


def _first(val):
    """OSM stores some tags as lists ('name': ['A', 'B']) where simplification merged
    ways; keep the first, which is what the published workbook's filters already use."""
    if isinstance(val, list):
        val = val[0] if val else ""
    return "" if val is None else str(val)


def _street(d):
    """Display name for an edge: the OSM name, or '(unnamed <road type>)' so unnamed
    ramps and links still read sensibly in a tooltip."""
    name = _first(d.get("name", ""))
    return name if name else f"(unnamed {_road_type(d)})"


def _road_type(d):
    """OSM highway class with underscores as spaces ('motorway_link' -> 'motorway link')."""
    return _first(d.get("highway", "")).replace("_", " ")


def edge_table(G):
    """One row per directed edge: ids, street name, road class, end and mid coordinates.
    Coordinates come from the node x/y (lon/lat) so no geometry parsing is needed."""
    rows = []
    for u, v, k, d in G.edges(keys=True, data=True):
        nu, nv = G.nodes[u], G.nodes[v]
        rows.append({
            "U": u, "V": v, "Key": k,
            "Street": _street(d),
            "Road Type": _road_type(d),
            "Lat U": nu["y"], "Lon U": nu["x"], "Lat V": nv["y"], "Lon V": nv["x"],
            "Lat": (nu["y"] + nv["y"]) / 2, "Lon": (nu["x"] + nv["x"]) / 2,
        })
    return pd.DataFrame(rows)


def load_run(data_dir, run):
    """Per-segment results for one run, keyed like the graph edges."""
    path = os.path.join(data_dir, f"{run}_segments.parquet")
    df = pd.read_parquet(path).rename(columns={"u": "U", "v": "V", "key": "Key"})
    return df[["U", "V", "Key", "nox_g", "throughput"]]


def diff_table(edges, open_df, closed_df, f_no2):
    """Join open and closed runs onto the edge table and compute the change columns.
    NO2 = F_NO2 * NOx, applied here (config.F_NO2), the same place visualize.py does it."""
    o = open_df.rename(columns={"nox_g": "nox_o", "throughput": "thr_o"})
    c = closed_df.rename(columns={"nox_g": "nox_c", "throughput": "thr_c"})
    df = edges.merge(o, on=["U", "V", "Key"], how="left")
    df = df.merge(c, on=["U", "V", "Key"], how="left")
    # A segment removed by the closure has no closed-run row: it carried nothing.
    num = ["nox_o", "thr_o", "nox_c", "thr_c"]
    df[num] = df[num].fillna(0.0)
    df["NO2 Before (g)"] = (f_no2 * df["nox_o"]).round(2)
    df["NO2 During Closure (g)"] = (f_no2 * df["nox_c"]).round(2)
    df["NO2 Change (g)"] = (df["NO2 During Closure (g)"] - df["NO2 Before (g)"]).round(2)
    df["NO2 Change Magnitude (g)"] = df["NO2 Change (g)"].abs()
    df["Traffic Before (veh)"] = df["thr_o"].astype(int)
    df["Traffic During (veh)"] = df["thr_c"].astype(int)
    df["Traffic Change (veh)"] = df["Traffic During (veh)"] - df["Traffic Before (veh)"]
    return df[COLS]


def write(df, out):
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if out.lower().endswith(".xlsx"):
        df.to_excel(out, index=False)
    else:
        df.to_csv(out, index=False)
    print(f"wrote {len(df):,} rows -> {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


def cmd_closure(a):
    G = ox.load_graphml(a.graph)
    edges = edge_table(G)
    df = diff_table(edges, load_run(a.data_dir, a.open),
                    load_run(a.data_dir, a.closed), config.F_NO2)
    if a.scenario:
        df.insert(0, "Scenario", a.scenario)
    write(df, a.out)


def cmd_scenarios(a):
    G = ox.load_graphml(a.graph)
    edges = edge_table(G)
    open_df = load_run(a.data_dir, a.open)
    parts = []
    for spec in a.pairs:
        name, run = spec.split("=", 1)
        df = diff_table(edges, open_df, load_run(a.data_dir, run), config.F_NO2)
        if a.changed_only:
            # keep only segments the closure touched; the full baseline is its own table
            touched = (df["NO2 Change (g)"] != 0) | (df["Traffic Change (veh)"] != 0)
            df = df[touched]
        df.insert(0, "Scenario", name)
        print(f"  {name:<24} {run:<24} {len(df):>8,} rows, "
              f"net NO2 {df['NO2 Change (g)'].sum():+.1f} g")
        parts.append(df)
    write(pd.concat(parts, ignore_index=True), a.out)


def cmd_validation(a):
    """The held-out PBOT count comparison as a scatter table. Rank percentiles use
    pandas' average method, so the two rank columns are what validate_traffic.py's
    Spearman correlates (rho 0.59 for powell_through, ledger V1)."""
    path = os.path.join(a.data_dir, f"{a.run}_count_validation.parquet")
    d = pd.read_parquet(path)
    out = pd.DataFrame({
        "Segment": d["seg"],
        "Observed ADT (veh/day)": d["adt"].round(1),
        "Simulated Throughput (veh)": d["throughput"],
        "PBOT Count Visits": d["n_counts"],
        "Observed Rank (pct)": (d["adt"].rank(pct=True) * 100).round(1),
        "Simulated Rank (pct)": (d["throughput"].rank(pct=True) * 100).round(1),
    })
    rho = d["adt"].corr(d["throughput"], method="spearman")
    print(f"{a.run}: {len(d)} segments, Spearman rho = {rho:.3f}")
    write(out, a.out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data-dir", default=config.PROCESSED_DIR)
    common.add_argument("--graph", default=os.path.join(config.NETWORK_DIR, "graph.graphml"))
    common.add_argument("--out", required=True)

    p = sub.add_parser("closure", parents=[common])
    p.add_argument("--open", required=True)
    p.add_argument("--closed", required=True)
    p.add_argument("--scenario", default=None, help="optional Scenario column value")
    p.set_defaults(fn=cmd_closure)

    p = sub.add_parser("scenarios", parents=[common])
    p.add_argument("--open", required=True, help="the shared open baseline run")
    p.add_argument("pairs", nargs="+", metavar="NAME=RUN")
    p.add_argument("--changed-only", action="store_true")
    p.set_defaults(fn=cmd_scenarios)

    p = sub.add_parser("validation", parents=[common])
    p.add_argument("--run", default=config.RUN_NAME)
    p.set_defaults(fn=cmd_validation)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
