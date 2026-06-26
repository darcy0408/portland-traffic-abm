"""Real residential and employment mass, for grounding WHERE trips start and end.

Right now generate.py draws each trip's origin and destination uniformly at random
over the network's nodes, so every street corner is an equally likely place to
start or finish a trip. That is the obvious unrealistic piece left in the model:
real trips start where people live and end where people work. This module supplies
that spatial pattern from real public data so generate.py can replace the uniform
draw with a gravity-style weighted draw (origins by population, destinations by
jobs). It is the spatial counterpart to demand_data.py, which supplies only the
time-of-day shape.

Two public sources, both no-account, no-API-key downloads, and BOTH independent of
the PBOT traffic counts we validate against. That independence is the point: demand
is calibrated only from population and jobs, never from the counts, so the PBOT
counts stay a clean held-out test set (the same independent-test-set discipline as
the Roberts spatial-cross-validation paper).

1. Origins, the home end: US Census 2020 "Centers of Population" for block groups.
   One file per state gives every block group its resident POPULATION and the
   population-weighted centroid LATITUDE/LONGITUDE in a single small CSV. Oregon is
   state FIPS 41.
   https://www2.census.gov/geo/docs/reference/cenpop2020/blkgrp/CenPop2020_Mean_BG41.txt

2. Destinations, the work end: LEHD LODES8 Workplace Area Characteristics (WAC) for
   Oregon. Counts jobs by workplace census block (column C000 = total jobs). We
   aggregate blocks up to block group (the first 12 digits of the 15-digit block
   GEOID) and join to the population file on the block-group GEOID.
   https://lehd.ces.census.gov/data/lodes/LODES8/or/wac/or_wac_S000_JT00_<year>.csv.gz

The result is one row per block group near Powell: a centroid (lat, lon), a resident
population, and a job count. generate.py snaps each centroid to the nearest network
node and uses population as the origin weight and jobs as the destination weight.

This is a production-attraction gravity setup: population produces trips at the home
end, employment attracts them at the work end. A distance-decay term (closer pairs
more likely) is the usual third ingredient; it is deliberately left out of this first
version because the study area is only ~3 km across, so every pair is already close.
Add it later if the comparison needs it (it matters more at city scale).

Run it with:
    python src/landuse_data.py            # use cached downloads if present
    python src/landuse_data.py --refresh  # force fresh downloads
"""
import os
import sys
import math
import urllib.request

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# Oregon = state FIPS 41. Block-group centers of population (resident pop + centroid).
CENPOP_URL = ("https://www2.census.gov/geo/docs/reference/cenpop2020/blkgrp/"
              "CenPop2020_Mean_BG41.txt")
# LODES8 workplace jobs for Oregon; the year is a config knob (LODES_YEAR).
LODES_WAC_URL = ("https://lehd.ces.census.gov/data/lodes/LODES8/or/wac/"
                 "or_wac_S000_JT00_{year}.csv.gz")


def _download(url, dest, force=False):
    """Download url to dest once and reuse it. Census/LODES files are static, so a
    cached copy in data/raw means repeat runs need no network."""
    if os.path.exists(dest) and not force:
        return dest
    print(f"  downloading {url}")
    urllib.request.urlretrieve(url, dest)
    return dest


def _load_population(force=False):
    """Block-group resident population and centroid. Returns a DataFrame with
    bg_geoid (12-char string), lat, lon, population."""
    path = _download(CENPOP_URL, os.path.join(config.RAW_DIR, "cenpop2020_bg_or.txt"),
                     force)
    # Keep the FIPS pieces as strings so leading zeros survive (county 001, etc.).
    df = pd.read_csv(path, dtype={"STATEFP": str, "COUNTYFP": str,
                                  "TRACTCE": str, "BLKGRPCE": str})
    # 12-digit block-group GEOID = state(2) + county(3) + tract(6) + block group(1)
    df["bg_geoid"] = (df["STATEFP"] + df["COUNTYFP"]
                      + df["TRACTCE"] + df["BLKGRPCE"])
    return df.rename(columns={"POPULATION": "population",
                              "LATITUDE": "lat", "LONGITUDE": "lon"})[
        ["bg_geoid", "lat", "lon", "population"]]


def _load_jobs(year, force=False):
    """Jobs per block group from LODES WAC. Returns bg_geoid (12-char), jobs."""
    url = LODES_WAC_URL.format(year=year)
    path = _download(url, os.path.join(config.RAW_DIR, f"or_wac_{year}.csv.gz"), force)
    # w_geocode is the 15-digit workplace block GEOID; C000 is total jobs. Read the
    # GEOID as a string so its leading zeros and full width are preserved.
    wac = pd.read_csv(path, usecols=["w_geocode", "C000"], dtype={"w_geocode": str})
    wac["bg_geoid"] = wac["w_geocode"].str[:12]      # block -> block group
    jobs = wac.groupby("bg_geoid", as_index=False)["C000"].sum()
    return jobs.rename(columns={"C000": "jobs"})


def _haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters between scalar lat1/lon1 and array lat2/lon2."""
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def landuse_table(year=None, radius_m=None, force=False):
    """One row per block group near the study center: bg_geoid, lat, lon,
    population, jobs. Block groups with no jobs in LODES get jobs = 0 (a residential
    area still produces trips). Restricted to centroids within radius_m of the study
    center so the masses line up with the cached network's footprint."""
    year = config.LODES_YEAR if year is None else year
    radius_m = config.STUDY_RADIUS_M if radius_m is None else radius_m

    pop = _load_population(force)
    jobs = _load_jobs(year, force)
    df = pop.merge(jobs, on="bg_geoid", how="left")
    df["jobs"] = df["jobs"].fillna(0.0)

    lat0, lon0 = config.STUDY_CENTER
    df["dist_m"] = _haversine_m(lat0, lon0, df["lat"].to_numpy(), df["lon"].to_numpy())
    near = df[df["dist_m"] <= radius_m].drop(columns="dist_m").reset_index(drop=True)
    return near


if __name__ == "__main__":
    force = "--refresh" in sys.argv
    df = landuse_table(force=force)
    out = os.path.join(config.PROCESSED_DIR, "landuse_bg.parquet")
    df.to_parquet(out, index=False)

    print(f"Land-use mass near {config.STUDY_AREA_LABEL}:")
    print(f"  {len(df)} block groups within {config.STUDY_RADIUS_M} m of the center "
          f"(LODES {config.LODES_YEAR})")
    print(f"  total population {int(df['population'].sum()):,}, "
          f"total jobs {int(df['jobs'].sum()):,}")
    print(f"  saved to {out}")
    if len(df):
        print("\n  most populated block groups:")
        for r in df.sort_values("population", ascending=False).head(4).itertuples():
            print(f"    pop {int(r.population):>5}  jobs {int(r.jobs):>5}  "
                  f"({r.lat:.4f}, {r.lon:.4f})")
        print("  most jobs:")
        for r in df.sort_values("jobs", ascending=False).head(4).itertuples():
            print(f"    pop {int(r.population):>5}  jobs {int(r.jobs):>5}  "
                  f"({r.lat:.4f}, {r.lon:.4f})")
