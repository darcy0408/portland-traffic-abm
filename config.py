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

# --- Simulation parameters ---
# N_VEHICLES and the network size are the two knobs to scale for the runtime
# benchmark (Christof, Jun 22): turn them up and watch how wall time grows.
N_VEHICLES = 500
N_STEPS = 3600                # example: one simulated hour at one-second steps
CHECKPOINT_EVERY = 300        # save state every 300 steps, so a crash loses at most this much work
RUN_NAME = "powell_signals"   # names the output files; change it for each new experiment
