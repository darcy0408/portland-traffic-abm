# Datasets

Public data the project needs, with where to get it and how usable it is. Built
from a research pass on Jun 22 (Christof's "spend ~30% finding the critical
datasets" ask). Synthetic stand-ins are fine for the prototype; this is the map of
what to wire in for realism later. Nothing here is downloaded yet.

Priority order to actually pull: **PORTAL** (time-of-day volumes/speeds) and **ODOT
AADT** (daily totals on Powell) for traffic; **NLCD via Earth Engine** for the
land-use predictors; **PBOT Traffic Signals** for signal locations; **SUMO's
HBEFA3 NOx(v,a) coefficients** for emissions in the prototype.

---

## 1. Street network (have it)

- **OSMnx / OpenStreetMap** — already cached (`data/network/graph.graphml`). Geometry
  plus a coarse `highway=` class. This is the ABM's road graph.
- **Metro RLIS Streets** (cross-check / alternative): regional centerlines with
  classification + address attributes, ODbL-style open license (attribution).
  https://rlisdiscovery.oregonmetro.gov/ . Not traffic volumes, just the network.

## 2. Traffic volumes and speeds (calibration)

These calibrate how many vehicles to spawn and how fast they should want to go.

- **PSU PORTAL (TREC)** — the richest, most relevant source, and it is PSU's own.
  Freeway loop detectors (I-5/205/405/84/OR-217) and arterial signal data: speed,
  volume, occupancy, travel time, at native 20-second resolution aggregatable to
  5 min / 1 hr / day. Free CSV/JSON download forms, no login. Use it for realistic
  time-of-day volume and speed profiles. https://new.portal.its.pdx.edu/downloads/
  (contact askportal@pdx.edu; acknowledge PORTAL/TREC).
- **ODOT AADT** — annual average daily traffic on state routes, including Powell
  (OR-8/US-26). Point counts at milepoints; covers arterials, not local streets.
  Web portal (TCDS, CSV export per station) plus a Python-friendly spatial layer via
  ODOT TransGIS ArcGIS REST. Use as the daily-volume anchor on Powell.
  https://www.oregon.gov/odot/data/pages/traffic-counting.aspx ·
  https://gis.odot.state.or.us/transgis/
- **PBOT Traffic Volume Counts** — 24 to 48 hr tube counts on city/local streets that
  ODOT misses. Point ADT values. GeoJSON/REST, reads straight into GeoPandas.
  https://gis-pdx.opendata.arcgis.com/datasets/traffic-volume-counts
- **PBOT Traffic Speed Counts** — point speed studies; good for calibrating the IDM
  desired (free-flow) speed. Same access.
  https://gis-pdx.opendata.arcgis.com/datasets/PDX::traffic-speed-counts/about

## 3. Traffic signals (for week-4 queueing)

- **PBOT Traffic Signals** — point locations of city signals, to snap onto OSMnx
  nodes. GeoJSON/REST/Shapefile, City of Portland open data.
  https://gis-pdx.opendata.arcgis.com/datasets/traffic-signals
- **Signal timing plans (cycle/split/offset) are NOT open data.** They live in PBOT's
  operational systems and would need a direct request. Documented modeling
  assumption: use standard cycle/split parameters for now; PORTAL arterial signal
  data is the closest open proxy for real operation.

## 4. Emission factors (NO2 path, week 5)

You have each vehicle's instantaneous speed and acceleration. Two parts: an
emission-factor source, and a rule mapping speed+accel to a rate.

- **SUMO HBEFA3 coefficients** (recommended for the prototype) — Eclipse SUMO ships
  continuous polynomials fitted to HBEFA 3.1 that take instantaneous v and a and
  return g/s for NOx (plus CO2, CO, etc.). Open source (EPL-2.0), free, extractable
  to plain Python without running SUMO. Feeds straight from the IDM's per-step v, a.
  Avoid the known-bad classes (`LDV`+NOx, `PC_G_EU0`+NOx); pick a PC diesel/gasoline
  Euro 4-6 class. https://sumo.dlr.de/docs/Models/Emissions/HBEFA3-based.html
- **HBEFA proper** (the source CLAUDE.md names) — g/km factors indexed by vehicle
  category and "traffic situation" (area x road type x speed limit x level of
  service), with NO2 given as a % of NOx. **Commercial, paid, no free version**
  (INFRAS). Native granularity is a congestion bin, not per-instant. https://www.hbefa.net/
- **US EPA MOVES** (US-native, for calibration with Christof) — official US model
  carrying the Oregon fleet mix. Internally bins running NOx by operating mode
  (VSP + speed). Free, public domain. Getting per-opMode rates means querying its
  default database; or export a g/mile-vs-speed curve. https://www.epa.gov/moves
- **pollemission / COPERT** — COPERT speed-NOx g/km curves by class and Euro standard,
  in Python. Coefficients are openly published in the EMEP/EEA guidebook; the repo
  license is unstated (use at risk). https://github.com/pollemission/pollemission

Mapping rule, two options: **(A) VSP / operating-mode binning** (US-standard, matches
MOVES; compute Vehicle Specific Power per step, bin it, look up the NOx rate, split
NOx into NO2) or **(B) the SUMO HBEFA3 polynomial** NOx(v, a) fed directly from the
IDM (lowest friction). Plan: prototype with B, cross-check with A/MOVES at calibration.

## 5. Land cover and geospatial predictors (Rao comparison, week 6)

These build the Rao-style land-use predictors so the comparison is apples-to-apples.

- **NLCD (National Land Cover Database)** — land cover, % impervious, % tree canopy at
  30 m. Tree canopy is annual 1985-2023; land cover at 2001/2006/.../2021. Public
  domain GeoTIFF. Easiest path is **Google Earth Engine**
  (`USGS/NLCD_RELEASES/2021_REL/NLCD`) for computing per-segment buffer averages in
  Colab. https://www.mrlc.gov/data
- **Road functional class** — **ODOT functional class** spatially joined onto the
  OSMnx edges gives each segment a real FHWA class (for ABM speed/capacity and for
  "road length by class within buffer" predictors). GIS layer by request to
  odotrics@odot.oregon.gov. FHWA NHPN is a national-scale cross-check (public domain).
- **Population** (for population-weighting the comparison, late stage) — US Census
  block-group population (TIGER/Line + ACS via `pygris`/API), or EPA **BenMAP-CE +
  PopGrid** to grid Census population onto your surface and compute health endpoints.
  Public domain. PopGrid ships with 2010 blocks (mind the vintage).
  https://www.epa.gov/benmap

## 6. NO2 monitoring (context only, NOT a validation spine)

- **Oregon DEQ / EPA AQS** ambient NO2 — only a handful of Portland-metro sites (one
  SE community site, near-road sites by I-5). Far too sparse for a surface, which is
  exactly why the project is framed model-to-model. Use as a 2 to 3 point magnitude
  spot check, stated honestly as such. Pre-generated CSVs:
  https://aqs.epa.gov/aqsweb/airdata/download_files.html

---

## Licensing summary

Public domain (no restriction): NLCD, MOVES, BenMAP/PopGrid, FHWA NHPN, EPA AQS,
ODOT data (government). Open with attribution: RLIS (ODbL-style), City of Portland
open data, PORTAL (acknowledge TREC), OpenStreetMap (ODbL). Open-source code:
SUMO (EPL-2.0). Paid/commercial: HBEFA proper. Use-at-risk: pollemission (license
unstated; underlying COPERT coefficients are openly published).
