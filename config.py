"""Central configuration.

Every tunable value, every path, and the random seed live here, not scattered
through the other scripts. A year from now you can read this one file and know
exactly how a run was set up. That is part of reproducibility.
"""
import os

# --- Reproducibility ---
RANDOM_SEED = 42          # set once here, applied wherever randomness happens

# --- Paths ---
# In Colab, point everything at mounted Google Drive so data survives a disconnect.
# Locally, paths resolve to folders next to this file.
IN_COLAB = os.path.exists("/content/drive")
if IN_COLAB:
    BASE_DIR = "/content/drive/MyDrive/PSU REU/abm"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

NETWORK_DIR   = os.path.join(BASE_DIR, "data", "network")
RAW_DIR       = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
FIGURES_DIR   = os.path.join(BASE_DIR, "outputs", "figures")

for d in (NETWORK_DIR, RAW_DIR, PROCESSED_DIR, FIGURES_DIR):
    os.makedirs(d, exist_ok=True)

# --- Study area ---
# Defined by an explicit center point and radius, not a place-name string. A name
# like "SE Powell Blvd" geocodes to a tiny wrong fragment (a single road segment),
# so we anchor by coordinates instead. This is reproducible and lets you tune the
# study-area size with one number, which is what the runtime benchmark needs.
# Center sits on SE Powell Blvd by Cleveland High School (Powell & SE 26th).
# Widen the radius toward the full city later, and bump RUN_NAME so you do not
# overwrite earlier results.
STUDY_AREA_LABEL = "SE Powell Blvd corridor (Cleveland HS center, 1.5 km radius)"
STUDY_CENTER = (45.49854, -122.63862)   # (latitude, longitude)
STUDY_RADIUS_M = 1500                    # meters from center; 1.5 km -> ~3 km square
NETWORK_TYPE = "drive"

# --- Car-following (Intelligent Driver Model) ---
# These shape how every vehicle accelerates and brakes. Values are the standard
# IDM defaults from the traffic-flow literature; tune them later with Christof
# once we can see the dynamics. Units are SI: meters, seconds, m/s, m/s^2.
IDM_A_MAX  = 1.5    # comfortable acceleration when the road ahead is open
IDM_B_COMF = 2.0    # comfortable braking when closing on a slower car
IDM_T      = 1.5    # safe time headway: seconds of gap a driver wants to keep
IDM_S0     = 2.0    # minimum bumper-to-bumper gap when fully stopped
IDM_DELTA  = 4.0    # acceleration exponent; 4 is the conventional choice
DT         = 1.0    # simulation time step in seconds (one step = one second)

# --- Vehicle ---
VEHICLE_LENGTH_M = 5.0   # bumper-to-bumper length; sets the minimum following gap

# --- Traffic signals (week 4) ---
# Signalized intersections run a simple two-phase cycle: one phase serves the
# roughly east-west approaches, the other the north-south ones, so cross streets
# alternate. Real OSM-tagged signal nodes are used when present. Timing here is a
# documented assumption (per-signal timing plans are not open data; see DATASETS.md).
SIGNAL_CYCLE_S = 60.0      # full cycle length in seconds (one green for each phase)
SIGNAL_GREEN_SPLIT = 0.5   # fraction of the cycle the east-west phase holds green

# --- Emissions (NO2 path, week 5) ---
# Per-vehicle NOx comes from SUMO's HBEFA3 polynomial in instantaneous speed and
# acceleration (the formula, coefficients, and source live in src/emissions.py).
# We pick one representative passenger-car class for the prototype.
EMISSION_CLASS = "PC_D_EU4"   # passenger car, diesel, Euro 4 (HBEFA3); diesel = the NOx-relevant case
# Primary-NO2 fraction of NOx for this class. The simulation accumulates NOx grams
# per segment; the NO2 surface is NO2 = F_NO2 * NOx, applied later in analysis and
# visualization. Keeping it here (not baked into the sim) means it can be retuned
# without rerunning the expensive run. Central literature value ~0.30; plausible
# range 0.20-0.30 (EMEP/EEA Guidebook; Carslaw et al. 2016). Raise with Christof
# when we set calibration gates.
F_NO2 = 0.30

# --- Road closure scenario (Christof, Jun 23) ---
# A closure removes street segments from the network before routing, so vehicles
# must find a different way around the gap. This is the experiment a static
# land-use model cannot do: the land use is unchanged, but the traffic, and the
# NO2 and noise surfaces, shift. (Christof's examples: a bridge maintenance
# closure, the planned I-5 lane closure that pushes traffic onto I-205, marathon
# street closures.)
# CLOSURE is a (lat, lon, radius_m) zone; every street segment whose midpoint
# falls inside the circle is closed. Set it to None for an ordinary single run.
# The closure experiment (python src/generate.py closure) runs the network once
# open and once closed and saves both, so visualize.py can difference them.
# Default zone: ~a block of SE Powell at the study center (Powell & SE 26th), so
# the main arterial is cut and traffic has to divert onto parallel streets.
CLOSURE = (45.49854, -122.63862, 150.0)

# --- Spatial demand (gravity model from population + jobs) ---
# Trip origins are drawn with probability proportional to resident population, and
# destinations proportional to jobs, both from real Census/LODES data near the study
# area (see src/landuse_data.py). This replaces the uniform-random origin/destination
# draw so traffic concentrates where people actually live and work. Set False to fall
# back to the uniform draw (e.g. for the runtime benchmark). The masses come only from
# population and jobs, never from the PBOT counts, so those counts stay a held-out
# validation set.
DEMAND_GRAVITY = True
LODES_YEAR = 2021   # LEHD LODES8 workplace-jobs vintage; 2021 avoids the 2020 anomaly
# Gravity distance-decay length (meters). Destinations are drawn conditional on the
# origin, with each job's pull multiplied by exp(-distance / this scale), so nearer
# jobs are likelier and trips stay mostly local instead of all funneling to the one
# big job center. This is the classic gravity-model deterrence term. The value is set
# a priori (comparable to the study-area radius and the short end of urban trip
# lengths), NOT tuned against the held-out PBOT counts, so the validation stays an
# honest test. Revisit at the calibration gate with Christof. Set to None to disable
# decay (origins and destinations drawn independently).
GRAVITY_DECAY_SCALE_M = 1500.0

# --- Rao-style predictors (NO2 comparison, week 6) ---
# Rao et al. describe every location by aggregating each predictor over circular
# buffers of increasing radius around it, so a point "sees" its neighborhood and
# not just the single segment it sits on. We reuse the same buffer radii for the
# ABM traffic predictors, so the baseline (land-use) forest and the ABM forest are
# built on identical spatial footing and the only difference is the predictor
# source. Rao used 12 buffers from 100 to 1200 m; we start with a representative
# subset and can widen it later.
BUFFER_RADII_M = (100, 200, 400, 800, 1200)

# --- Simulation parameters ---
# N_VEHICLES and the network size are the two knobs to scale for the runtime
# benchmark (Christof, Jun 22): turn them up and watch how wall time grows.
N_VEHICLES = 500
N_STEPS = 3600                # example: one simulated hour at one-second steps
CHECKPOINT_EVERY = 300        # save state every 300 steps, so a crash loses at most this much work
RUN_NAME = "powell_no2"       # names the output files; change it for each new experiment
                              # (this run: spillback + HBEFA3 NOx -> NO2 surface)
# Jun 29 saturation-vs-rank test: re-ran at N_VEHICLES=240 (RUN_NAME "powell_n240")
# to see if unsaturating raised the traffic-count rank correlation. It did NOT
# (rho 0.328 -> 0.329), so the weak ordering is about demand STRUCTURE/routing, not
# magnitude. Reproduce by setting N_VEHICLES=240 and RUN_NAME="powell_n240" here.
