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
more likely) is the usual third ingredient, and it is included: destinations are drawn
conditional on the origin, with each job's pull damped by
exp(-distance / config.GRAVITY_DECAY_SCALE_M), so trips stay mostly local instead of
all funneling to the single largest job center. The decay math lives in generate.py
(build_demand_weights and make_vehicle); this module only supplies the population and
job masses those functions weight.

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

# State-parameterized versions of the same two sources, for the polygon table below
# (the metro window crosses the Columbia into Clark County WA, so the feature side
# needs both states; the OR-only files above are kept as-is because the sim's demand
# was generated from them and must stay reproducible).
CENPOP_URL_TMPL = ("https://www2.census.gov/geo/docs/reference/cenpop2020/blkgrp/"
                   "CenPop2020_Mean_BG{fips}.txt")
LODES_WAC_URL_TMPL = ("https://lehd.ces.census.gov/data/lodes/LODES8/{st}/wac/"
                      "{st}_wac_S000_JT00_{year}.csv.gz")
# Census cartographic-boundary block-group polygons (500k scale, clipped to
# shoreline, so river/water area is excluded from a block group's area).
CB_BG_URL_TMPL = ("https://www2.census.gov/geo/tiger/GENZ2020/shp/"
                  "cb_2020_{fips}_bg_500k.zip")
STATE_FIPS = {"or": "41", "wa": "53"}
# Projected CRS for polygon-area math: UTM zone 10N covers the Portland metro.
AREA_CRS = "EPSG:26910"


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


def _load_nonwork_attraction(year, force=False):
    """Retail/service jobs per block group from LODES WAC: the attraction mass for
    shopping/errand trips (config.NONWORK_SECTORS: retail trade, accommodation +
    food services, other services). Same file and aggregation as _load_jobs, so no
    new download; only the columns differ. Returns bg_geoid, nonwork_attr."""
    url = LODES_WAC_URL.format(year=year)
    path = _download(url, os.path.join(config.RAW_DIR, f"or_wac_{year}.csv.gz"), force)
    cols = list(config.NONWORK_SECTORS)
    wac = pd.read_csv(path, usecols=["w_geocode"] + cols, dtype={"w_geocode": str})
    wac["bg_geoid"] = wac["w_geocode"].str[:12]      # block -> block group
    wac["nonwork_attr"] = wac[cols].sum(axis=1)
    attr = wac.groupby("bg_geoid", as_index=False)["nonwork_attr"].sum()
    return attr


def nonwork_table(year=None, radius_m=None, force=False):
    """One row per block group near the study center: bg_geoid, lat, lon,
    population, nonwork_attr (retail/service jobs). The origin mass (population)
    is the same one landuse_table uses; only the attraction column differs. Kept in
    its OWN parquet (landuse_nonwork_bg.parquet) so landuse_bg.parquet, the
    committed runs' demand input, stays byte-identical."""
    year = config.LODES_YEAR if year is None else year
    radius_m = config.STUDY_RADIUS_M if radius_m is None else radius_m

    pop = _load_population(force)
    attr = _load_nonwork_attraction(year, force)
    df = pop.merge(attr, on="bg_geoid", how="left")
    df["nonwork_attr"] = df["nonwork_attr"].fillna(0.0)

    lat0, lon0 = config.STUDY_CENTER
    df["dist_m"] = _haversine_m(lat0, lon0, df["lat"].to_numpy(), df["lon"].to_numpy())
    near = df[df["dist_m"] <= radius_m].drop(columns="dist_m").reset_index(drop=True)
    return near


def _load_population_state(st, force=False):
    """Block-group population + centroid for one state ('or' or 'wa'). Same format
    as _load_population, which stays OR-hardcoded for the sim-demand path."""
    fips = STATE_FIPS[st]
    path = _download(CENPOP_URL_TMPL.format(fips=fips),
                     os.path.join(config.RAW_DIR, f"cenpop2020_bg_{st}.txt"), force)
    df = pd.read_csv(path, dtype={"STATEFP": str, "COUNTYFP": str,
                                  "TRACTCE": str, "BLKGRPCE": str})
    df["bg_geoid"] = (df["STATEFP"] + df["COUNTYFP"]
                      + df["TRACTCE"] + df["BLKGRPCE"])
    return df.rename(columns={"POPULATION": "population",
                              "LATITUDE": "lat", "LONGITUDE": "lon"})[
        ["bg_geoid", "lat", "lon", "population"]]


def _load_jobs_state(st, year, force=False):
    """Jobs per block group from one state's LODES WAC ('or' or 'wa')."""
    url = LODES_WAC_URL_TMPL.format(st=st, year=year)
    path = _download(url, os.path.join(config.RAW_DIR, f"{st}_wac_{year}.csv.gz"),
                     force)
    wac = pd.read_csv(path, usecols=["w_geocode", "C000"], dtype={"w_geocode": str})
    wac["bg_geoid"] = wac["w_geocode"].str[:12]
    jobs = wac.groupby("bg_geoid", as_index=False)["C000"].sum()
    return jobs.rename(columns={"C000": "jobs"})


def landuse_polygons(year=None, radius_m=None, margin_m=None, states=("or", "wa"),
                     force=False):
    """Block-group POLYGONS with population and jobs, for areal-weighted buffer
    features. Returns a GeoDataFrame in AREA_CRS (meters) with columns bg_geoid,
    population, jobs, geometry, area_m2.

    Two deliberate differences from landuse_table (the sim-demand input):
      1. POLYGONS, not centroids, so a buffer can take each block group's mass in
         proportion to the overlap area (uniform-density assumption, the standard
         areal-weighting method) instead of all-or-nothing on a centroid.
      2. BOTH states. The 20 km window crosses the Columbia into Clark County WA;
         the OR-only table leaves ~40 of Rao's 352 sites with a demographic hole,
         which handicaps the land-use baseline and flatters the ABM.
    This function writes NOTHING to landuse_bg.parquet: that file is the sim's
    demand input and must stay byte-identical to what the committed runs used.

    Selection: keep block groups whose polygon intersects the study circle grown
    by margin_m (default: the largest buffer radius), so a buffer drawn around any
    in-window site never silently misses a just-outside block group.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    year = config.LODES_YEAR if year is None else year
    radius_m = config.STUDY_RADIUS_M if radius_m is None else radius_m
    margin_m = max(config.BUFFER_RADII_M) if margin_m is None else margin_m

    frames = []
    for st in states:
        fips = STATE_FIPS[st]
        shp = _download(CB_BG_URL_TMPL.format(fips=fips),
                        os.path.join(config.RAW_DIR, f"cb_2020_{fips}_bg_500k.zip"),
                        force)
        gdf = gpd.read_file(shp)[["GEOID", "geometry"]].rename(
            columns={"GEOID": "bg_geoid"})
        pop = _load_population_state(st, force)[["bg_geoid", "population"]]
        jobs = _load_jobs_state(st, year, force)
        gdf = gdf.merge(pop, on="bg_geoid", how="left")
        gdf = gdf.merge(jobs, on="bg_geoid", how="left")
        frames.append(gdf)

    gdf = pd.concat(frames, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=frames[0].crs)
    gdf["population"] = gdf["population"].fillna(0.0).astype(float)
    gdf["jobs"] = gdf["jobs"].fillna(0.0).astype(float)

    gdf = gdf.to_crs(AREA_CRS)
    lat0, lon0 = config.STUDY_CENTER
    center = gpd.GeoSeries([Point(lon0, lat0)], crs="EPSG:4326").to_crs(AREA_CRS)[0]
    window = center.buffer(radius_m + margin_m)
    gdf = gdf[gdf.geometry.intersects(window)].reset_index(drop=True)
    gdf["area_m2"] = gdf.geometry.area
    return gdf


if __name__ == "__main__":
    force = "--refresh" in sys.argv
    if "--nonwork" in sys.argv:
        # build ONLY the non-work attraction table; landuse_bg.parquet untouched
        df = nonwork_table(force=force)
        out = os.path.join(config.PROCESSED_DIR, "landuse_nonwork_bg.parquet")
        df.to_parquet(out, index=False)
        print(f"Non-work (retail/service) attraction near {config.STUDY_AREA_LABEL}:")
        print(f"  {len(df)} block groups within {config.STUDY_RADIUS_M} m "
              f"(LODES {config.LODES_YEAR}, sectors {'+'.join(config.NONWORK_SECTORS)})")
        print(f"  total attraction jobs {int(df['nonwork_attr'].sum()):,}")
        print(f"  saved to {out}")
        if len(df):
            print("  biggest attractors:")
            for r in df.sort_values("nonwork_attr", ascending=False).head(4).itertuples():
                print(f"    attr {int(r.nonwork_attr):>6}  pop {int(r.population):>5}  "
                      f"({r.lat:.4f}, {r.lon:.4f})")
        sys.exit(0)
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
