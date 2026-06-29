"""Loader for Rao's passive-sampler NO2 data, the shared target of the week-6
model-to-model forest comparison.

Dr. Meenakshi Rao sent this directly (Jun 28, 2026); it is her unpublished
field data, so the file lives in the gitignored data/rao/ folder and must never
be committed. Source sheet 'nox_all_lurvars' in no2_for_Darcy.xlsx:

  pan_id site_id Latitude Longitude no2 no nox year season   (NO2 in ppb)

603 readings at 352 unique sites in four rounds:
  2012r1 summer (171), 2012r2 summer (176), 2013 summer (174), 2014 winter (82).
The 174-summer / 82-winter rounds are the exact campaign in Rao et al. 2017
(IJERPH 14(7):750), the baseline this project compares against.

The comparison's target is NO2 (the quantity Rao's land-use forest predicts and
the quantity the ABM produces as NO2 = F_NO2 * NOx). Every row has an NO2 value;
the no/nox columns have gaps we do not need here.

This module only reads and tidies data. It runs no simulation and draws nothing.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

RAO_PATH = os.path.join(config.BASE_DIR, "data", "rao", "no2_for_Darcy.xlsx")
SHEET = "nox_all_lurvars"


def load_raw():
    """Return the full sheet as-is (one row per site-round reading)."""
    if not os.path.exists(RAO_PATH):
        raise SystemExit(
            f"Rao data not found at {RAO_PATH}. It is unpublished field data kept "
            f"out of git; copy no2_for_Darcy.xlsx into data/rao/ first.")
    return pd.read_excel(RAO_PATH, sheet_name=SHEET)


def rao_targets(season="summer", year=None, average_rounds=True):
    """Return a tidy target table: one row per site with a single NO2 value.

    Columns: site_id, lat, lon, no2, n_readings.

    season: 'summer' (default) or 'winter'. Rao fit summer and winter models
        separately; summer is the larger campaign (three rounds here), so it is
        the natural primary target.
    year:  keep only this round (e.g. '2013' for the exact published summer model,
        '2014' for the published winter model). None keeps every round in the
        season.
    average_rounds: when a site was measured in more than one round of the chosen
        season, average its NO2 into one stable per-site value (the default).
        Set False to keep every reading as its own row.

    Sites with measurements in several summer rounds get a more stable target by
    averaging; this is a modeling choice, documented here, not a tuned knob. To
    reproduce Rao's published forest exactly instead, pass year='2013' (summer).
    """
    df = load_raw().copy()
    df["year"] = df["year"].astype(str)
    df = df[df["season"] == season]
    if year is not None:
        df = df[df["year"] == str(year)]
    if len(df) == 0:
        raise SystemExit(f"No Rao rows for season={season!r} year={year!r}.")

    df = df.rename(columns={"Latitude": "lat", "Longitude": "lon"})
    df = df[df["no2"].notna()]

    if not average_rounds:
        return df[["site_id", "lat", "lon", "no2"]].reset_index(drop=True)

    # one row per site: mean NO2 across the season's rounds, coords from the first
    g = (df.groupby("site_id")
           .agg(lat=("lat", "first"), lon=("lon", "first"),
                no2=("no2", "mean"), n_readings=("no2", "size"))
           .reset_index())
    return g


def summary():
    """Print a quick profile (rounds, site counts, value range). For a sanity check."""
    df = load_raw()
    df["year"] = df["year"].astype(str)
    print(f"{len(df)} readings, {df.site_id.nunique()} unique sites")
    print("by round:")
    print(df.groupby(["year", "season"]).size().to_string())
    print(f"\nlat {df.Latitude.min():.3f}..{df.Latitude.max():.3f}  "
          f"lon {df.Longitude.min():.3f}..{df.Longitude.max():.3f}")
    print(f"NO2 ppb: min {df.no2.min():.2f}  median {df.no2.median():.2f}  "
          f"mean {df.no2.mean():.2f}  max {df.no2.max():.2f}")
    s = rao_targets("summer")
    w = rao_targets("winter")
    print(f"\ntargets: summer {len(s)} sites (pooled), winter {len(w)} sites")


if __name__ == "__main__":
    summary()
