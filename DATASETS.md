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

  **PULLED (Jun 23), real data, no account needed.** There is a public JSON/CSV API
  with no token required (docs: https://adus.github.io/portal-documentation/ ).
  - Freeway volume + speed endpoint:
    `https://new.portal.its.pdx.edu/highways/api/freewaydata/`
    params: `start_date`, `end_date`, `highway_id` (repeatable), `detector_id`,
    `resolution` (e.g. `01:00:00`), `format=csv`.
    GOTCHA: `end_date` is exclusive-style. `start_date=2024-05-14&end_date=2024-05-14`
    returns only the 00:00 hour; ask for a 2-day window
    (`end_date=2024-05-15`) and keep the first day to get all 24 hours. The
    `detector_id` filter appeared to be ignored in testing; filter by `highway_id`
    and then by station/detector in code instead.
  - Metadata endpoints (also CSV, no auth):
    `.../highways/api/stationmetadata/?format=csv` (has lat/lon `x_coord`/`y_coord`),
    `.../highways/api/detectormetadata/?format=csv` (detector -> station -> lane).
  - **Powell Blvd has no PORTAL volume loop.** PORTAL covers Powell only as
    travel-time segments (Bluetooth/DCU travel time, not volume) and one classifier
    entry "Powell (2R032) to SB I-205". For a clean hourly **volume + speed** curve
    near the study center, the nearest freeway station is **station 3032, "Madison
    (2DS042) @ NB I-5 MP300.8"** (detectors 100280/100281/100282, 3 lanes), about
    2.8 km from Powell & SE 26th. Use its **time-of-day SHAPE** only, not its
    absolute volume (the daily total comes from ODOT AADT below).
  - Sample saved to `data/portal_powell_sample.csv` (Tue 2024-05-14, hourly,
    volume+speed). Loader: `src/demand_data.py` turns it into 24 normalized hourly
    fractions. Real-data weekday shape confirmed: light overnight, AM peak ~08:00,
    sustained midday, PM peak ~15:00, evening taper.
- **ODOT AADT** — annual average daily traffic on state routes, including Powell.
  Point counts at milepoints; covers arterials, not local streets.
  Web portal (TCDS, CSV export per station) plus a Python-friendly spatial layer via
  ODOT TransGIS ArcGIS REST. Use as the daily-volume anchor on Powell.
  https://www.oregon.gov/odot/data/pages/traffic-counting.aspx ·
  https://gis.odot.state.or.us/transgis/

  **FOUND (Jun 23), verified value.** Inner-SE Powell Blvd is ODOT's **Mt. Hood
  Highway No. 26** (milepoint measured from OR-99W in Portland; this is the city
  segment, not the rural US-26 mainline near Mt. Hood). From the published
  "2018 Traffic Volumes on State Highways" report (TVT_2018.pdf):
  - **AADT 34,900 (year 2018), MP 2.09, "0.02 mile east of SE 26th Avenue"** — this
    point is essentially at our study center (Powell & SE 26th, Cleveland HS). Use
    this as the daily-volume anchor.
  - Corridor context within the 1.5 km radius (all 2018, Mt. Hood Hwy No. 26):
    MP 1.79 SE 21st = 37,200; MP 1.83 = 35,200; MP 2.89 W of Cesar Chavez = 33,900;
    MP 2.93 E of Cesar Chavez = 37,100; MP 3.23 E of SE 45th = 39,400. So the corridor
    runs roughly **34,000-39,000 AADT**.
  Source PDF: https://www.oregon.gov/odot/Data/Documents/TVT_2018.pdf (Mt. Hood
  Highway No. 26 section). Newer single-station counts can be pulled from ODOT's
  TCDS / TransGIS portals; 2018 is the published-report value verified here.
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

## 5b. Spatial demand: where trips start and end (gravity model)

These ground WHERE trips begin and end (origins by population, destinations by
jobs), the spatial complement to PORTAL's time-of-day shape (section 2). They feed
the gravity demand model in `src/landuse_data.py` + `generate.py`
(`build_demand_weights`). Both are no-account, no-API-key downloads, and BOTH are
independent of the PBOT counts the model is validated against, so those counts stay
a clean held-out test set.

- **Census 2020 Centers of Population, block groups (PULLED, Jun 25).** One file per
  state gives every block group its resident POPULATION and population-weighted
  centroid lat/lon in a single small CSV. Oregon (state FIPS 41) within the 1.5 km
  study radius: **19 block groups, 23,548 residents**. Used as the origin (home-end)
  mass. Public domain. No key.
  https://www2.census.gov/geo/docs/reference/cenpop2020/blkgrp/CenPop2020_Mean_BG41.txt
- **LEHD LODES8 Workplace Area Characteristics, Oregon (PULLED, Jun 25).** Jobs by
  workplace census block (column C000 = total jobs); we aggregate blocks to block
  group (first 12 digits of the 15-digit GEOID) and join to the centers-of-population
  centroids. Study area: **12,389 jobs**, with one dominant job center near the study
  middle. Used as the destination (work-end) mass. Year is `config.LODES_YEAR` (2021,
  avoiding the 2020 anomaly). Public domain. No key.
  https://lehd.ces.census.gov/data/lodes/LODES8/or/wac/or_wac_S000_JT00_2021.csv.gz

  **Validation finding (Jun 25).** Two changes were tested against the held-out PBOT
  counts (Spearman rank of real ADT vs model throughput on 247 segments):
  (1) routing vehicles by travel TIME instead of distance raised the correlation from
  **0.26 to 0.38** (a clear, principled win, kept); (2) adding the population->jobs
  gravity demand did NOT improve it (0.38 -> 0.35, and 0.33 with distance decay),
  because this metric is dominated by network structure, which uniform demand already
  captures via betweenness on the arterials. The gravity model is kept on by default
  anyway (`config.DEMAND_GRAVITY`) because the closure and time-of-day experiments
  need realistic destinations; the decay scale was set a priori (1.5 km), NOT tuned
  against PBOT, to keep the test set honest.

## 6. NO2 monitoring (context only, NOT a validation spine)

- **Oregon DEQ / EPA AQS** ambient NO2. Confirmed against the source (2023 Oregon
  Annual Ambient Criteria Pollutant Air Monitoring Network Plan, DEQ to EPA Region 10):
  the entire Portland-Vancouver-Hillsboro metro (2.5M people) has exactly TWO regulatory
  NO2 monitors. (1) SE Lafayette community / NCore site, AQS 41-051-0080, at
  45.4966, -122.6029 (5824 SE Lafayette, Portland), the nearest monitor to the Powell
  study area, a couple km east of center. (2) One freeway near-road site, AQS 41-067-0005,
  on I-5 at MP 290.14 in Tualatin (AADT 153,822, 2021), 27 m from the freeway; a second
  near-road site is pending but low priority because the existing one reads well below the
  NAAQS. Neither is on Powell. Two points for the whole metro is far too sparse to validate
  a street-segment surface, which is exactly why the project is framed model-to-model. At
  most, pull the SE Lafayette annual mean from EPA AQS as a single-point magnitude sanity
  check, stated honestly as such (a Christof decision, not the spine). Pre-generated CSVs:
  https://aqs.epa.gov/aqsweb/airdata/download_files.html  Plan PDF (network plan, not
  measurements) is the primary source: see REFERENCES.md [6].

## 7. Calibration data availability (Jun 26 hunt, for the post-demo calibration work)

Two of the three "calibration work left" items on the demo deck were data-scouted to see
if they are even gettable for a remote student. Result: one is gated, one is buildable.

- **Real per-signal timing: NOT gettable, becomes a documented limitation.** Neither PBOT
  nor ODOT publishes signal timing (cycle/split/offset) as open data; there is no public
  ATSPM dashboard in Oregon. The only path is a public-records request (slow). More
  fundamentally, the Powell corridor runs **SCATS adaptive control** (installed Oct 2011,
  ~SE 11th to SE 72nd), so a fixed timing plan largely does not exist there: the system
  recomputes splits/offsets in real time from detectors. So the uniform 60 s / 50%-green
  cycle is a deliberate, citable simplification, not a data gap to fill. Cite the PSU
  evaluation (REFERENCES.md [7]) and frame matching adaptive control as future work.
  Locations-only layer (already have via OSM): https://gis-pdx.opendata.arcgis.com/datasets/traffic-signals
- **Mixed vehicle fleet: BUILDABLE from public data, sharpens the NO2 surface (not the
  count match).** Replaces the single PC_D_EU4 class with a real type / fuel / age mix.
  - PRIMARY: EPA MOVES county database for **Multnomah County, FIPS 41051** (from the 2020
    NEI onroad inputs). Three tables give all three weights, county-specific, public domain,
    no MOVES GUI run needed: `sourceTypeAgeDistribution` (age), `avft` (gas/diesel split),
    `sourceTypeYear`/`sourceTypePopulation` (type mix). Schema:
    https://github.com/USEPA/EPA_MOVES_Model/blob/master/docs/MOVESDatabaseTables.md ;
    NEI onroad TSD: https://www.epa.gov/system/files/documents/2023-01/NEI2020_TSD_Section5_Onroad_0.pdf
  - FAST FALLBACK: weighted basket of SUMO HBEFA4 classes using the documented 2022
    average-fleet shares (mostly PC_petrol_Euro-*, a diesel minority, a few % rigid-truck/LCV).
    Same NOx(v,a) machinery, per class. Label as European-average until reweighted to MOVES.
    https://sumo.dlr.de/docs/Vehicle_Type_Parameter_Defaults.html
  - TYPE-ONLY CROSS-CHECK (free, local): Oregon DMV registrations by county (Multnomah ~95%
    passenger). https://www.oregon.gov/odot/dmv/pages/news/vehicle_stats.aspx
  - LOCAL Powell heavy-vehicle share: PBOT **layer 253 "Vehicle Class Counts"** (separate from
    the layer-250 volumes the project pulls) carries `PctTrucks` / `PctCars` / `TwoAxleCF`. 2014
    counts on SE Powell at SE 28th give volume-weighted **%Trucks = 5.4%**, but `TwoAxleCF ~ 0.99`
    means ~99% are TWO-AXLE light commercial (vans), not heavy multi-axle (~0.05%). So Powell's
    "trucks" are mostly light-commercial diesel, with transit buses hidden in the 2-axle count.
    PORTLAND_FLEET now reflects this. Endpoint (same no-key REST pattern as traffic_counts.py):
    https://www.portlandmaps.com/od/rest/services/COP_OpenData_Transportation/MapServer/253/query
  - Open knob (Christof decision): how finely to resolve the diesel / heavy-duty / bus split
    inside that 5.4%, since those dominate per-vehicle NOx. The MOVES `avft` table for 41051 and
    the layer-253 axle split settle it locally.
- **Real time-of-day volumes: already prototyped.** The `day` mode (24 hourly runs scaled by
  the PORTAL profile) adds the temporal dimension; see section 5 / PROGRESS.md.

---

## Licensing summary

Public domain (no restriction): NLCD, MOVES, BenMAP/PopGrid, FHWA NHPN, EPA AQS,
ODOT data (government). Open with attribution: RLIS (ODbL-style), City of Portland
open data, PORTAL (acknowledge TREC), OpenStreetMap (ODbL). Open-source code:
SUMO (EPL-2.0). Paid/commercial: HBEFA proper. Use-at-risk: pollemission (license
unstated; underlying COPERT coefficients are openly published).
