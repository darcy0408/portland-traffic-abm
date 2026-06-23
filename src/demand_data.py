"""Real time-of-day demand profile, for grounding the simulation's trip generation.

Right now generate.py spawns a fixed number of vehicles and respawns each one the
moment it finishes, so the count on the network is constant for the whole run. That
is fine for a runtime benchmark but it is not how a real day looks: traffic is light
overnight, climbs to a morning peak, holds through midday, peaks again in the
afternoon, then tapers. This module supplies that shape from real data so a later
version of generate.py can make the spawn rate follow the clock.

What "demand profile" means here: 24 numbers, one per hour of the day, each the
fraction of the day's total traffic that happens in that hour. They sum to 1.0. So
0.08 at hour 8 means 8 percent of the day's trips start in the 8 am hour. This is a
SHAPE, not an absolute count. You multiply it by however many vehicles you want in a
day to get an hour-by-hour spawn target.

Data source (see DATASETS.md and the header of data/portal_powell_sample.csv):
PSU PORTAL freeway loop detectors. We use station 3032 on NB I-5 (MP 300.8), the
nearest open volume+speed station to the study center at Powell and SE 26th, about
2.8 km away. Powell Boulevard itself has no PORTAL volume loop, so we borrow the
freeway's time-of-day curve. We use only its shape, never its absolute volume: the
absolute daily total on Powell comes from ODOT AADT (about 34,900 vehicles/day at
SE 26th in 2018, see DATASETS.md), not from this file.

The PORTAL CSV was pulled with no account required, via:
  GET https://new.portal.its.pdx.edu/highways/api/freewaydata/
      ?start_date=2024-05-14&end_date=2024-05-15
      &highway_id=1&resolution=01:00:00&format=csv
Note that end_date behaves exclusive-style: to get all 24 hours of one day you ask
for a two-day window and keep the first day. 2024-05-14 is a representative Tuesday.

How this plugs into generate.py (not wired in yet, on purpose):
  1. Call hourly_demand_profile() once at startup to get the 24 fractions.
  2. Pick a daily vehicle budget (a new config value, e.g. N_VEHICLES_PER_DAY).
  3. Each simulated hour h, the spawn target is profile[h] * budget. Spawn that many
     new vehicles over that hour instead of respawning one-for-one on arrival.
  4. With DT = 1 s and N_STEPS = 3600 (one hour), a run currently covers a single
     hour, so you would index the profile by the hour-of-day the run represents.
Everything tunable (which hour a run represents, the daily budget, the CSV path)
belongs in config.py when this gets wired in, matching the project convention that
parameters live there and not in the module.
"""
import os
import csv

# The sample file lives in data/, which is gitignored. Resolve it relative to this
# file so the loader works whether run from the repo root or from src/.
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_CSV = os.path.join(_HERE, os.pardir, "data", "portal_powell_sample.csv")

# Clearly-marked synthetic fallback, used only if the real CSV is missing. It is a
# smooth stand-in with the same two-peak weekday shape (light night, AM and PM
# peaks) so code paths still run, but it is NOT real data. The numbers are raw
# hourly weights; hourly_demand_profile() normalizes whatever it gets to sum to 1.
# Keep this in sync with the real CSV's schema (one value per hour, hour 0..23).
_SYNTHETIC_HOURLY_WEIGHTS = [
    20, 12, 12, 18, 35, 70, 120, 160, 175, 150, 130, 130,   # 00..11
    125, 130, 140, 150, 150, 140, 125, 100, 85, 70, 50, 30,  # 12..23
]


def _read_portal_csv(path):
    """Read the PORTAL sample CSV and return a dict {hour: volume_vph}.

    The file has comment lines starting with '#' (provenance, units, the exact API
    call) ahead of a 'hour,volume_vph,mean_speed_mph' header. We skip the comments,
    then read the volume column. Returns None if the file is absent so the caller
    can fall back to the synthetic shape.
    """
    if not os.path.exists(path):
        return None
    volumes = {}
    with open(path, newline="") as f:
        # drop comment lines first; csv has no native comment support
        clean = (line for line in f if not line.lstrip().startswith('#')
                 and not line.lstrip().startswith('"#'))
        reader = csv.DictReader(clean)
        for row in reader:
            # be forgiving about stray blank rows
            if not row.get("hour"):
                continue
            volumes[int(row["hour"])] = float(row["volume_vph"])
    return volumes if volumes else None


def hourly_demand_profile(csv_path=None):
    """Return 24 fractions (hour 0..23) of the day's traffic, summing to 1.0.

    Reads the real PORTAL sample if present, otherwise falls back to the clearly
    marked synthetic shape. Either way the result is normalized, so it is a pure
    shape you can multiply by a daily vehicle budget to get per-hour spawn targets.

    Returns a list of 24 floats. profile[h] is the share of the day's trips in
    hour h. Missing hours in the source are treated as zero before normalizing.
    """
    path = _DEFAULT_CSV if csv_path is None else csv_path
    volumes = _read_portal_csv(path)

    if volumes is None:
        # synthetic fallback: same shape, clearly not real data
        weights = list(_SYNTHETIC_HOURLY_WEIGHTS)
    else:
        weights = [volumes.get(h, 0.0) for h in range(24)]

    total = sum(weights)
    if total <= 0:
        # degenerate source: hand back a flat profile rather than dividing by zero
        return [1.0 / 24] * 24
    return [w / total for w in weights]


def is_using_real_data(csv_path=None):
    """True if the real PORTAL CSV is present and readable, False if we would fall
    back to the synthetic shape. Handy for printing an honest note in a run log."""
    path = _DEFAULT_CSV if csv_path is None else csv_path
    return _read_portal_csv(path) is not None


if __name__ == "__main__":
    # quick self-check: print the profile and confirm it sums to 1
    profile = hourly_demand_profile()
    src = "real PORTAL data" if is_using_real_data() else "SYNTHETIC fallback"
    print(f"hourly demand profile ({src}):")
    for h, frac in enumerate(profile):
        bar = "#" * int(round(frac * 200))
        print(f"  {h:02d}:00  {frac:6.4f}  {bar}")
    print(f"sum = {sum(profile):.4f}  (should be 1.0)")
    peak = max(range(24), key=lambda h: profile[h])
    print(f"peak hour = {peak:02d}:00")
