"""Real origin-destination commute demand from LEHD LODES8 (the honest demand lever).

The gravity demand in generate.py (build_demand_weights) approximates trips as a
PRODUCT: origin weight (resident population) times destination weight (jobs) times a
distance-decay term. That is a guess at the joint home->work distribution built from
its two marginals. LODES gives us the real JOINT distribution directly.

This module pulls the LODES8 Origin-Destination file for Oregon (or_od_main), which
lists, for every home census block, how many workers commute to every work census
block (column S000 = total jobs/flows). We aggregate those block-level flows up to
block-GROUP pairs (so they line up with the population/jobs centroids landuse_data
already uses) and keep only pairs whose home AND work block groups both fall inside
the study area. That yields a real internal home->work flow matrix for the corridor.

Why this is an honest input, not tuning: LODES is Census commute data, completely
independent of the held-out PBOT traffic counts we validate against. It informs WHERE
trips go, it is never fit to the counts we score on. (McDonald 2026, Table 6.5:
demand-aware predictors reach Spearman 0.7-0.9 vs ~0.3 for pure structure, so real
demand is the principled lever to move the traffic-count agreement.)

"main" (or_od_main) covers workers whose home and work are both in Oregon; the
separate "aux" file covers workers living out of state. We use main only: both ends of
an internal corridor trip are in Oregon, and cross-state commuters are regional
through-traffic, which the through-traffic feature already models separately.

Run it with:
    python src/lodes_od.py            # use cached pull if present
    python src/lodes_od.py --refresh  # force a fresh pull from the LODES server
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import landuse_data

# LODES8 Origin-Destination, Oregon, "main" (home and work both in-state). JT00 = all
# jobs. The year is the same knob as the WAC jobs pull so the two vintages match.
LODES_OD_URL = ("https://lehd.ces.census.gov/data/lodes/LODES8/or/od/"
                "or_od_main_JT00_{year}.csv.gz")

# read the big OD file in chunks so a multi-million-row statewide file never has to
# sit in memory all at once; each chunk is filtered to the study area before we keep it
_CHUNK = 500_000


def _study_area_bgs(year=None, radius_m=None, force=False):
    """The set of block-group GEOIDs inside the study area, with their centroids.
    Reuses landuse_data.landuse_table so the OD ends map onto the exact same block
    groups (and centroids) the gravity demand already uses. Returns (bg_set, table)."""
    lu = landuse_data.landuse_table(year=year, radius_m=radius_m, force=force)
    return set(lu["bg_geoid"]), lu


def od_table(year=None, radius_m=None, force=False):
    """Real home-bg -> work-bg commute flows for the study area.

    Returns a DataFrame with columns h_bg, w_bg (12-char block-group GEOIDs) and flow
    (total commuters S000), restricted to pairs whose home and work block groups are
    both inside the study area. Intrazonal pairs (h_bg == w_bg) are kept: people who
    live and work in the same block group still make a trip inside the corridor.
    """
    year = config.LODES_YEAR if year is None else year
    bg_set, _ = _study_area_bgs(year=year, radius_m=radius_m, force=force)

    url = LODES_OD_URL.format(year=year)
    path = landuse_data._download(
        url, os.path.join(config.RAW_DIR, f"or_od_main_{year}.csv.gz"), force)

    # h_geocode / w_geocode are 15-digit block GEOIDs; read as strings so leading
    # zeros survive. S000 is the total worker count for that home->work block pair.
    kept = []
    for chunk in pd.read_csv(path, usecols=["h_geocode", "w_geocode", "S000"],
                             dtype={"h_geocode": str, "w_geocode": str},
                             chunksize=_CHUNK):
        chunk["h_bg"] = chunk["h_geocode"].str[:12]   # block -> block group
        chunk["w_bg"] = chunk["w_geocode"].str[:12]
        # keep only trips with BOTH ends inside the corridor (internal demand)
        m = chunk["h_bg"].isin(bg_set) & chunk["w_bg"].isin(bg_set)
        if m.any():
            kept.append(chunk.loc[m, ["h_bg", "w_bg", "S000"]])

    if not kept:
        return pd.DataFrame(columns=["h_bg", "w_bg", "flow"])
    od = pd.concat(kept, ignore_index=True)
    od = od.groupby(["h_bg", "w_bg"], as_index=False)["S000"].sum()
    return od.rename(columns={"S000": "flow"})


if __name__ == "__main__":
    force = "--refresh" in sys.argv
    bg_set, lu = _study_area_bgs(force=force)
    od = od_table(force=force)

    out = os.path.join(config.PROCESSED_DIR, "lodes_od.parquet")
    od.to_parquet(out, index=False)

    total = od["flow"].sum()
    internal = od[od["h_bg"] != od["w_bg"]]["flow"].sum()
    print(f"LODES OD commute demand near {config.STUDY_AREA_LABEL}:")
    print(f"  {len(bg_set)} block groups in the study area (LODES {config.LODES_YEAR})")
    print(f"  {len(od):,} home->work block-group pairs, {int(total):,} total commuters")
    print(f"  {int(internal):,} cross-block-group ({100*internal/total:.0f}% of flow) "
          f"vs {int(total-internal):,} live-and-work-in-same-BG")
    print(f"  saved to {out}")
    if len(od):
        print("\n  heaviest home->work flows:")
        name = {r.bg_geoid: f"({r.lat:.4f},{r.lon:.4f})" for r in lu.itertuples()}
        for r in od.sort_values("flow", ascending=False).head(6).itertuples():
            tag = "  [same BG]" if r.h_bg == r.w_bg else ""
            print(f"    {int(r.flow):>4} workers  {name.get(r.h_bg,'?')} "
                  f"-> {name.get(r.w_bg,'?')}{tag}")
