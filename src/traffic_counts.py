"""Pull real PBOT traffic-volume counts for validating the ABM (Christof, Jun 25).

Christof's Jun 25 email: validate the ABM against real traffic counts the city has
already collected. This module pulls the City of Portland (PBOT) "Traffic Volume
Counts" layer, point ADT (average daily traffic) counts on city streets, from the
PortlandMaps ArcGIS REST service, restricted to the Powell study area. No scraper
needed: it is a clean REST endpoint that returns GeoJSON.

Service (one layer of COP_OpenData_Transportation, ~24,700 count points citywide):
  https://www.portlandmaps.com/od/rest/services/COP_OpenData_Transportation/MapServer/250
Key field: ADTVolume (average daily traffic). Also AM/PM volumes, StartDate/EndDate,
and LocationDesc/CountLocDesc for the street. Geometry is points (lon/lat).

This is a data-pull script (the generate side): it fetches and caches, no plotting.
The validation comparison (snap each count to the nearest ABM segment, compare real
ADT vs the model's volume) builds on the table this writes.

Run it with:
    python src/traffic_counts.py            # use cached pull if present
    python src/traffic_counts.py --refresh  # force a fresh pull from the API
"""
import os
import sys
import json
import math
import urllib.parse
import urllib.request

import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# the single ArcGIS layer holding the PBOT volume counts, query endpoint
SERVICE = ("https://www.portlandmaps.com/od/rest/services/"
           "COP_OpenData_Transportation/MapServer/250/query")


def _study_bbox():
    """Lon/lat bounding box around the study center, sized to the study radius.
    Used to ask the API for only the counts near Powell, not all ~24,700 citywide."""
    lat0, lon0 = config.STUDY_CENTER
    r = config.STUDY_RADIUS_M
    dlat = r / 111_000.0
    dlon = r / (111_320.0 * math.cos(math.radians(lat0)))
    return (lon0 - dlon, lat0 - dlat, lon0 + dlon, lat0 + dlat)


PAGE_SIZE = 200   # the layer caps each response at 200 records, so we page through


def _fetch_page(bbox, offset):
    """One page of the count query, starting at record `offset`. Ordering by
    OBJECTID makes paging stable (each record appears in exactly one page)."""
    xmin, ymin, xmax, ymax = bbox
    params = {
        "where": "1=1",
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",                       # bbox is in lon/lat (WGS84)
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "ADTVolume,StartDate,EndDate,LocationDesc,CountLocDesc",
        "returnGeometry": "true",
        "outSR": "4326",                      # return geometry in lon/lat too
        "orderByFields": "OBJECTID",
        "resultOffset": str(offset),
        "resultRecordCount": str(PAGE_SIZE),
        "f": "geojson",
    }
    url = SERVICE + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


def fetch_counts(force=False):
    """Fetch ALL count points inside the study bbox as one GeoJSON dict, paging past
    the layer's 200-record cap so nothing is silently dropped. Caches the assembled
    result to data/raw so repeat runs need no network. force=True re-pulls (the city
    updates this layer weekly)."""
    raw_path = os.path.join(config.RAW_DIR, "pbot_traffic_counts.geojson")
    if os.path.exists(raw_path) and not force:
        with open(raw_path) as f:
            return json.load(f)

    bbox = _study_bbox()
    features, offset = [], 0
    while True:
        page = _fetch_page(bbox, offset)
        page_feats = page.get("features", [])
        features.extend(page_feats)
        # a short page (fewer than the cap) means we have reached the end
        if len(page_feats) < PAGE_SIZE:
            break
        offset += len(page_feats)
        if offset > 20_000:                   # safety stop; the area is far smaller
            print("WARNING: stopped paging at 20,000 records as a safety cap.")
            break

    data = {"type": "FeatureCollection", "features": features}
    with open(raw_path, "w") as f:
        json.dump(data, f)
    return data


def counts_dataframe(force=False):
    """Tidy the GeoJSON into one row per count point: lon, lat, ADT, street, year."""
    gj = fetch_counts(force)
    rows = []
    for feat in gj.get("features", []):
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if not coords:
            continue
        props = feat.get("properties", {})
        rows.append({
            "lon": coords[0], "lat": coords[1],
            "adt": props.get("ADTVolume"),
            "location": props.get("LocationDesc") or props.get("CountLocDesc"),
            "start_ms": props.get("StartDate"),
        })
    df = pd.DataFrame(rows)
    if len(df):
        # ArcGIS returns dates as epoch milliseconds; pull out the count year
        df["year"] = pd.to_datetime(df["start_ms"], unit="ms", errors="coerce").dt.year
        df = df.drop(columns="start_ms")
    return df


if __name__ == "__main__":
    df = counts_dataframe(force="--refresh" in sys.argv)
    out = os.path.join(config.PROCESSED_DIR, "pbot_traffic_counts.parquet")
    df.to_parquet(out, index=False)

    print(f"PBOT traffic counts in the Powell study area: {len(df)} points")
    if len(df):
        adt = df["adt"].dropna()
        print(f"  ADT (average daily traffic): {len(adt)} with a value, "
              f"range {int(adt.min())}-{int(adt.max())}, median {int(adt.median())}")
        if df['year'].notna().any():
            print(f"  count years: {int(df['year'].min())}-{int(df['year'].max())}")
        print(f"  saved to {out}")
        print("\n  busiest few in the area:")
        top = df.dropna(subset=["adt"]).sort_values("adt", ascending=False).head(6)
        for r in top.itertuples():
            print(f"    {int(r.adt):>6} ADT  {r.location}")
