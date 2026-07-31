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
STUDY_AREA_LABEL = "Portland metro 20 km (Cleveland HS center, full-metro Rao comparison)"
STUDY_CENTER = (45.49854, -122.63862)   # (latitude, longitude)
STUDY_RADIUS_M = 20000                   # meters from center. 20 km captures ~90% of
                                         # Rao's 352 metro sites (316) from this center;
                                         # recentering does not help (sites are already
                                         # centered here). The 5 km scale (5000; 9,015
                                         # nodes / 25,991 edges, 91 summer sites, 113 s/hr)
                                         # is the prior exploratory step, cached in
                                         # graph_metro5k_backup.graphml. The 1.5 km Powell
                                         # window (1500) is the committed baseline that
                                         # reproduces powell_through.
NETWORK_TYPE = "drive"

# --- Car-following (Intelligent Driver Model) ---
# These shape how every vehicle accelerates and brakes. Values are the standard
# IDM defaults from the traffic-flow literature; tune them later with the mentor
# once we can see the dynamics. Units are SI: meters, seconds, m/s, m/s^2.
IDM_A_MAX  = 1.5    # comfortable acceleration when the road ahead is open
IDM_B_COMF = 2.0    # comfortable braking when closing on a slower car
IDM_T      = 1.5    # safe time headway: seconds of gap a driver wants to keep
IDM_S0     = 2.0    # minimum bumper-to-bumper gap when fully stopped
IDM_DELTA  = 4.0    # acceleration exponent; 4 is the conventional choice
DT         = 1.0    # simulation time step in seconds (one step = one second)

# --- Vehicle ---
VEHICLE_LENGTH_M = 5.0   # bumper-to-bumper length; sets the minimum following gap

# --- Stuck-time accumulator (calibrated-demand plan, Phase 3) ---
# "Cars stuck" is measured, not inferred: an opt-in per-segment accumulator
# (generate.run_simulation stuck_stats=..., same pattern as speed_stats) sums the
# vehicle-seconds each segment carries below this speed. The threshold matches
# JAM_KMH in src/gridlock_diagnosis.py, which INFERS jam from throughput*length/
# value at analysis time -- this accumulator measures the same 5 km/h condition
# per vehicle per step instead of from the segment mean. Pure measurement: it
# never feeds back into the dynamics (kernel-regression proven bit-identical).
STUCK_SPEED_KMH = 5.0    # below this a vehicle-second counts as stuck

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
# range 0.20-0.30 (EMEP/EEA Guidebook; Carslaw et al. 2016). Raise with the mentor
# when we set calibration gates.
F_NO2 = 0.30
# Mixed fleet. When True, each vehicle is assigned one HBEFA3 class at spawn,
# drawn from the sourced Multnomah County mix (fleet.PORTLAND_FLEET, 10 classes
# incl. gasoline majority, diesel minority, light commercial, a bus sliver, and
# EVs), and emits with its OWN class polynomial each step. The class draw uses its
# own seeded RNG stream (RANDOM_SEED + 2), so the trip-generation stream is
# untouched and traffic (routes, activity, throughput) is bit-identical to the
# same-seed single-class run; only NOx changes. Mentor-approved as the live
# setting (calibration gate G2, set Jul 20): the realistic mix replaces the
# all-diesel upper bound. All-diesel overstates NOx ~3.76x (measured), so numbers
# from runs before this switch are upper bounds; set False to reproduce them.
FLEET_MIXED = True

# --- Road closure scenario (mentor request, Jun 23) ---
# A closure removes street segments from the network before routing, so vehicles
# must find a different way around the gap. This is the experiment a static
# land-use model cannot do: the land use is unchanged, but the traffic, and the
# NO2 and noise surfaces, shift. (the mentor's examples: a bridge maintenance
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
# honest test. Revisit at the calibration gate with the mentor. Set to None to disable
# decay (origins and destinations drawn independently).
# Kept at 1500 for the 5 km scale-up: the a-priori rationale is now "short end of
# urban trip lengths" alone (it no longer matches the study radius). A knob for
# the mentor's calibration gate, not retuned here.
GRAVITY_DECAY_SCALE_M = 1500.0

# --- Real origin-destination demand from LODES (Jul 2) ---
# The gravity model above is a GUESS at the home->work distribution: it multiplies a
# population marginal by a jobs marginal and a distance-decay term. LODES gives the
# real JOINT distribution: actual counts of commuters from each home block group to
# each work block group (src/lodes_od.py, LEHD LODES8 OD file). With this flag on,
# trips draw a real home-BG -> work-BG pair in proportion to that flow, then map each
# end to a network node, instead of the gravity product. This is an honest INPUT, not
# tuning: LODES is Census commute data, independent of the held-out PBOT counts we
# score against (cf. McDonald 2026: demand-aware predictors reach Spearman 0.7-0.9 vs
# ~0.3 for pure structure, so real demand is the principled lever). CAVEAT: at the
# 1.5 km Powell scale the internal OD is thin (~575 commuters, 210 BG pairs), because
# most corridor traffic is through-traffic or has one end outside the window; the OD
# payoff grows with the study area, so this pairs naturally with the metro scale-up.
# At corridor scale this is left off so powell_no2 stays the gravity baseline; set with the mentors.
DEMAND_LODES_OD = True        # ON for the 20 km metro run: at metro scale the internal OD is
                              # rich (531k commuters, 1003 BGs) so real commute flows now drive
                              # demand. Off at corridor scale (see caveat above). metro20k run.

# --- Through-traffic (regional cordon demand, Jul 1) ---
# The gravity model above makes every trip start AND end inside the 1.5 km circle.
# But a real arterial like Powell carries heavy through-traffic: cars that started
# miles away and are only passing through. Without it the arterials are under-fed and
# get ranked too low against the real counts, while shortest-path routing over-uses
# quiet side streets as shortcuts (the SE 26th failure in the traffic validation).
# THROUGH_TRAFFIC_FRACTION of trips are instead "through trips" that enter at one edge
# of the network and leave at another, crossing the area. Entry/exit points are the
# perimeter nodes (beyond THROUGH_BOUNDARY_FRAC of the study radius from center),
# weighted toward the fastest roads that cross the boundary, so regional traffic comes
# in on the arterials the way it really does. The fraction and boundary are set A
# PRIORI from geometry and road class, NEVER tuned against the held-out PBOT counts, so
# the validation stays an honest test. Set the fraction to 0.0 to disable (reproduces
# the local-only gravity runs, e.g. powell_no2).
THROUGH_TRAFFIC_FRACTION = 0.15
# Jul 1 through-traffic experiment: an a-priori 30% through-trip share (RUN_NAME
# "powell_through", seed 42) raised the traffic-count rank correlation from 0.328 to
# 0.387 (activity 0.195 -> 0.270), the predicted direction: feeding the arterials with
# regional traffic and starving the side-street shortcuts. The 0.30 was set a priori,
# NOT tuned to the held-out PBOT counts. Set to 0.30 (Jul 2) so the closure sweep and
# the abstract's numbers all come from ONE model that matches the powell_through
# validation run (Spearman 0.39). The 0.0 local-only gravity setting reproduces the
# older powell_no2 baseline. Making the through share a permanent default is the mentors' call.
# Carried over unchanged for the 5 km scale-up. In a wider window more trips are
# internal, so the true through share should be LOWER than the corridor's 0.30.
# metro20k (20 km): re-derived a priori to 0.15. LODES OD is now ON and supplies
# 531k real internal commuters, so the window internalizes ~90% of metro activity;
# 0.15 is the residual interstate/freight/non-commute regional flow that still feeds
# the freeways. Halved from the corridor value on that scale argument, NOT tuned to
# held-out counts. Revisit with the mentor at the scale-up gate.
THROUGH_BOUNDARY_FRAC = 0.80   # a node is a boundary entry/exit if it lies beyond this
                               # fraction of STUDY_RADIUS_M from the study center

# --- Hourly demand profile (Phase A1, REAL_DEMAND_UPGRADE_PLAN.md, Jul 31) ---
# The base model holds the active fleet CONSTANT: every finished trip respawns
# immediately, so a 24 h run is a permanent rush hour -- and the Jul 29 metro day
# runs showed no finite network survives one (both arms seize). With this flag on,
# demand follows an hour-of-day shape m(h): each hour has an active-fleet QUOTA of
# round(N * m(h)/m_peak) vehicles, where N is the spawned fleet, so N_VEHICLES
# becomes the PEAK-hour fleet (matching how the metro demand ladder was scaled).
# A trip that finishes while the fleet is over quota PARKS (the car leaves the
# network, joining a parked pool) instead of respawning; when the quota rises,
# parked cars rejoin as fresh trips. Cars never vanish mid-trip -- a demand drop
# only stops respawns, so the active fleet decays to the new quota at the rate
# trips actually finish, which is the honest physics of an ebbing rush hour.
# The shape comes from demand_data.hourly_demand_profile(): the real PORTAL
# hour-of-day curve if data/portal_powell_sample.csv is present, else its clearly
# marked synthetic fallback -- a-priori either way, NEVER fit to the held-out
# validation counts. Off by default: every committed run reproduces unchanged.
DEMAND_PROFILE_ENABLED = False
DEMAND_PROFILE = None          # None -> demand_data.hourly_demand_profile();
                               # or an explicit 24-value shape (gates use this)
DEMAND_PROFILE_START_HOUR = 0  # clock hour at simulation t=0 (0 = midnight, so a
                               # 24 h run walks the profile once, hour 0 to 23)

# --- Left-turn pockets (Phase B1, REAL_DEMAND_UPGRADE_PLAN.md, Jul 31) ---
# The named corridor mechanism behind the peak-hour ceiling: a left-turner today
# waits in the through lane and DAMS it, so one car waiting for a gap stops every
# car behind it. Real arterials solve this with a turn pocket -- a short dedicated
# left-turn lane at the intersection. With this flag on, a car whose next route
# edge is a left turn moves OUT of the through queue into a pocket queue once it
# is within TURN_POCKET_LENGTH_M of the stop line, on segments OSM says have a
# dedicated left lane (src/turn_lanes.py sidecar). The pocket holds a finite
# number of cars; turners arriving at a full pocket stay in the through lane and
# dam it exactly as before -- which is the real failure mode, not an edge case.
# Requires MOBIL_ENABLED: pockets are a statement about lane identity, and only
# the explicit-lane model has any (refused loudly otherwise, like green-wave
# requiring Webster). Off by default; no committed number moves.
TURN_POCKETS_ENABLED = False
TURN_POCKET_LENGTH_M = 30.0   # a-priori storage length. AASHTO/NACTO practice for
                              # an urban arterial left-turn bay is ~25-45 m; 30 m is
                              # mid-range and NOT tuned to the held-out counts. At
                              # VEHICLE_LENGTH_M + IDM_S0 = 7 m per queued car this
                              # holds 4 cars, the capacity the kernel derives.

# --- Multi-lane capacity experiment (lanes-experiment worktree, Jul 10) ---
# The base model gives every directed segment ONE following lane, which caps a
# signalized segment near 1,070 veh/hr, below Powell's real peak (see
# calibrate_demand.py). This experiment tests how much that ceiling matters by
# giving each segment its real OSM-tagged lane count as VIRTUAL lanes: a car
# follows the car N positions ahead in the segment queue instead of the car
# directly ahead, so N cars can move abreast and queue discharge scales with N.
# No lane-change or merge behavior is modeled; virtual lanes assume perfect,
# frictionless lane use, so the capacity gain is an UPPER BOUND on what real
# lanes would add. Lane counts come from the OSM 'lanes' tag: list values (from
# merged edges) take the minimum (a road narrowing to 2 lanes carries what the
# 2-lane bottleneck allows), two-way streets halve the tag (OSM counts both
# directions; our graph has one directed edge per direction), untagged edges
# default to 1. All a priori from map data, never tuned to the held-out PBOT
# counts. Off by default: the single-lane model is the project's committed
# spec; this flag exists to produce EVIDENCE for the rank-vs-absolute-scale
# question (Nik Jul 8, Christof Jul 19), not to change the model.
LANES_ENABLED = False
LANES_MAX = 3         # per-direction cap; keeps a mistagged edge from getting absurd capacity

# --- MOBIL lane changing (traffic-realism Phase 3) ---
# Phase 1 (LANES_ENABLED) models a segment's lanes as VIRTUAL lanes with implicit,
# freely-reshuffling identity: a frictionless upper bound on capacity, no real
# passing. Phase 3 gives each vehicle a REAL lane index on its segment and decides
# changes with MOBIL (Kesting, Treiber & Helbing 2007, "General lane-changing model
# MOBIL for car-following models"). A vehicle changes to an adjacent lane iff it is
# SAFE (the prospective new follower brakes no harder than MOBIL_B_SAFE) AND the
# INCENTIVE holds (its own IDM acceleration gain exceeds the politeness-weighted
# disadvantage it imposes on its old and new followers, by more than
# MOBIL_A_THRESHOLD). Overtaking then EMERGES: a fast car stuck behind a slow one
# pulls out, passes, and merges back only when doing so helps without cutting anyone
# off. The three lane modes are mutually exclusive and both others stay unchanged:
# base (single file), LANES_ENABLED (Phase 1 virtual lanes), MOBIL_ENABLED (this).
# Off by default; the committed spec is the single-lane model. All accelerations are
# the SAME idm_acceleration kernel, so MOBIL adds a lane-change decision on top of
# the verified car-following, never a second physics. Standard literature values
# below; a-priori, not tuned to the held-out counts. See src/mobil.py.
MOBIL_ENABLED = False
MOBIL_POLITENESS = 0.2      # p: weight on the (dis)advantage a change does to others.
                            # 0 = selfish (change whenever it helps me), ~0.5 = polite.
MOBIL_A_THRESHOLD = 0.2     # m/s^2: minimum net acceleration gain to bother changing.
                            # Hysteresis: stops cars flip-flopping between equal lanes.
MOBIL_B_SAFE = 4.0          # m/s^2: the hardest deceleration a change may impose on the
                            # new follower. A change forcing harder braking is unsafe.

# --- Driver heterogeneity (traffic-realism Phase 2) ---
# The base model gives every vehicle the single IDM parameter set above, so a
# segment's cars are dynamically identical and its speed VARIANCE is zero. With
# this flag on, each vehicle draws its OWN IDM parameters at spawn: a
# multiplicative factor per parameter, N(1, sigma) truncated to [1-2*sigma,
# 1+2*sigma], centered on the config defaults (Treiber & Kesting's recommended
# heterogeneity method; src/drivers.py). The draws use a DEDICATED seeded RNG
# stream (RANDOM_SEED + 3, alongside +1 signals and +2 fleet), so enabling the
# flag consumes no trip/route/fleet draw and the same seed reproduces the same
# INITIAL vehicle population; the realized traffic then diverges (different
# dynamics -> different finish times -> different respawn timing), which is the
# effect being measured. Off by default: the committed
# spec is the homogeneous model; this flag exists to QUANTIFY the
# homogeneous-driver limitation -- a nonzero per-segment speed spread, which the
# CNOSSOS noise model (nonlinear in speed) turns into a shift in the noise surface
# even at equal mean speed -- not to change the cited numbers. With every sigma 0
# the machinery is provably inert (bitwise identical to the base model:
# src/driver_scenarios.py Gate A). Sigmas are a-priori literature-range spreads,
# NOT tuned against the held-out counts; revisit with the mentor at a calibration
# gate. Each is a FRACTIONAL sd (0.12 = ~12% spread), and must stay < 0.5.
DRIVER_HETEROGENEITY = False
DRIVER_SIGMA_V0 = 0.12   # desired-speed multiplier spread. The dominant knob: it sets
                         # how far a platoon disperses and the per-segment speed spread
                         # (~+-24% of the limit at the 2-sigma truncation bound).
DRIVER_SIGMA_A  = 0.15   # comfortable-acceleration spread
DRIVER_SIGMA_B  = 0.15   # comfortable-braking spread
DRIVER_SIGMA_T  = 0.15   # safe-time-headway spread
DRIVER_SIGMA_S0 = 0.10   # jam-spacing (standstill gap) spread

# --- Webster signal timing (traffic-realism Phase 4) ---
# The base model (SIGNAL_CYCLE_S / SIGNAL_GREEN_SPLIT above) gives every
# signalized intersection the SAME uniform 60 s cycle split 50/50, regardless of
# how lopsided its actual approach volumes are. Webster's formula (Webster, F.V.
# 1958, "Traffic signal settings", Road Research Technical Paper 39 -- the
# standard research fallback for a location without published signal-timing
# cards; Portland runs SCATS, an adaptive controller, with no public timing
# plans) instead derives a per-intersection cycle length and green split from
# the MODELED approach flows, so a heavy approach gets more green and a light
# one gets less. See src/webster.py for the pure computation. Off by default:
# the committed spec is the uniform signal; this flag exists to QUANTIFY that
# limitation (how much a heavy approach is under-served by a fixed 50/50 split),
# not to change the cited numbers. Not wired into the simulation yet (increment
# 1 is the decision core only; increment 2 will wire it into generate.py).
# All values below are standard a-priori traffic-engineering constants (HCM /
# Webster's own recommended defaults), NOT tuned to the held-out PBOT counts.
WEBSTER_ENABLED = False
WEBSTER_SAT_FLOW = 1900.0    # saturation flow, veh/h per lane (HCM-standard value:
                              # the maximum discharge rate of a single lane on
                              # continuous green, once queued traffic is moving).
WEBSTER_LOST_TIME_S = 4.0    # lost time per phase, s (startup delay as the queue
                              # gets moving + clearance as it empties; standard value).
WEBSTER_CYCLE_MIN_S = 30.0   # shortest cycle Webster's formula may return
WEBSTER_CYCLE_MAX_S = 120.0  # longest cycle Webster's formula may return -- also
                              # the practical fallback when demand is oversaturated
                              # and the optimal-cycle formula has no valid answer.
WEBSTER_MIN_GREEN_S = 7.0    # floor on any phase's green, s -- a pedestrian
                              # crossing / driver-expectation minimum, not a
                              # capacity number; Webster's optimum can undercut it
                              # for a very lightly loaded approach.
# Increment 2 (wired into the simulation). The two constants below are the DISPLAY
# clearance shown at every phase change -- the yellow then the all-red during which
# neither phase is green, so a car that reaches the line as its green ends stops
# rather than sailing through the cross traffic's start. They are the displayed
# safety interval, kept SEPARATE from WEBSTER_LOST_TIME_S above (which is Webster's
# capacity parameter inside the cycle-length formula); the two need not be equal and
# are documented as distinct. Standard ITE values (~3.5 s yellow, ~1.5 s all-red).
WEBSTER_YELLOW_S = 3.5        # yellow interval per phase change, s
WEBSTER_ALL_RED_S = 1.5      # all-red interval per phase change, s
# Measurement pre-pass: Webster needs a per-approach volume (veh/h) to time each
# intersection, and the base kernel does not produce one as a byproduct. When
# WEBSTER_ENABLED, a short SEEDED warmup runs first with the uniform base signals
# (its own RNG stream, so the authoritative run that follows is byte-for-byte the
# same population it would be with the flag off) and the realized approach crossings
# over the second half of that window become the flows. This many warmup steps (at
# DT s each); flows are averaged over the last half, after the network has filled.
WEBSTER_WARMUP_STEPS = 1200

# --- Green-wave signal coordination (traffic-realism Phase 4, increment 2b) ---
# Webster (2a) times each signal INDEPENDENTLY -- every node gets its own cycle
# fitted to its own approach flows. A progression ("green wave") needs the
# opposite: a shared cycle across a chain of signals, so a platoon that leaves
# the first signal's green arrives at each downstream signal during ITS green
# too. This flag adds that coordination on top of the per-node Webster plans,
# for ONE named corridor; every other signal in the network keeps its own
# independent 2a plan, untouched. Requires WEBSTER_ENABLED -- there is no
# per-node Webster cycle to coordinate without it, so turning this on with
# Webster off is refused loudly (see generate.prepare_signals), the same
# refusal style build_mobil_context uses for LANES_ENABLED+MOBIL_ENABLED. Off
# by default: the committed spec is per-node Webster with no coordination.
WEBSTER_GREENWAVE_ENABLED = False
# Case-insensitive substring match against each edge's OSM 'name' tag, which can
# itself be a list when OSM records more than one name for a way (e.g. a shared
# state-route designation) -- handled element-wise. Any signalized node touching
# a matching edge is a candidate chain member. NOTE the Jul 19 audit finding:
# NONE of the 21 real OSM-tagged signals in the committed 1.5 km corridor graph
# touch a Powell edge, so on the real cached graph this flag currently finds NO
# chain at all -- it is exercised end to end only on the synthetic graphs in
# src/greenwave_scenarios.py. No claim is made anywhere about Powell-scale
# green-wave effects.
WEBSTER_GREENWAVE_STREET = "Powell"
# Progression design speed, km/h -- the speed the coordination band assumes a
# platoon travels at (NOT each edge's own posted/free-flow speed, which the base
# IDM still uses for actual car-following). ~50 km/h / 30 mph is the standard
# urban arterial speed limit and the textbook default design speed for a
# fixed-time progression band; a-priori, NOT tuned to the held-out PBOT counts.
WEBSTER_PROGRESSION_SPEED_KPH = 50.0

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
# benchmark (mentor request, Jun 22): turn them up and watch how wall time grows.
# Scaled by study-area ratio for the 5 km run: the Jun 26 AADT calibration
# recommended 240 vehicles for the 1.5 km window (matches Powell AADT/24
# directional); (5000/1500)^2 = 11.1x the area gives ~2,700. Set a priori from
# geometry, NOT tuned to the held-out PBOT counts. The demand density of the
# wider area (less uniformly dense than the corridor) is a calibration question
# for the mentor at the scale-up gate. The 1.5 km baseline value was 500.
N_VEHICLES = 16500            # 20 km a-priori scaling. Raw area scaling (240*(20/1.5)^2 = 42.7k)
                              # over-counts: the outer metro has far fewer roads per km^2 (the
                              # 20 km graph is 7x the 5 km node count, not 16x the area). So scale
                              # by road size instead: 2700 * (159410/25991 edges) = 16.5k keeps the
                              # 5 km run's per-edge vehicle density. A priori from geometry, NOT
                              # tuned to held-out counts.
N_STEPS = 3600                # example: one simulated hour at one-second steps
CHECKPOINT_EVERY = 300        # save state every 300 steps, so a crash loses at most this much work
# metro5k: the exploratory 5 km scale-up run (worktree metro5k-scaleup). The
# committed-repo baseline behind every number cited in the SIGSPATIAL abstract is
# "powell_through" (1.5 km, N_VEHICLES=500, 30% through-traffic, seed 42); do not
# reuse that name here or its saved results could be overwritten.
RUN_NAME = "metro20k"         # names the output files; change it for each new experiment
# Jun 29 saturation-vs-rank test: re-ran at N_VEHICLES=240 (RUN_NAME "powell_n240")
# to see if unsaturating raised the traffic-count rank correlation. It did NOT
# (rho 0.328 -> 0.329), so the weak ordering is about demand STRUCTURE/routing, not
# magnitude. Reproduce by setting N_VEHICLES=240 and RUN_NAME="powell_n240" here.
