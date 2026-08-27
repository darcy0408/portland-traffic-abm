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

# --- Freeway closure scenario (mentor redirect, Jul 30) ---
# "Closing Powell is not really that interesting... closures is one thing you use
# to sell your model." The mentor asked for I-205 or I-5 instead, which have real
# precedent (the nighttime I-205 closures for Abernethy Bridge repair).
# A freeway closure cannot use CLOSURE above: that removes every edge in a circle,
# and freeway segments are so long that any circle big enough to cut the freeway
# also deletes the surface streets underneath it (measured: an 800 m circle on
# I-205 closes 245 edges, 240 of them surface streets). So this spec selects by
# route and road class, leaving the local grid open to receive the detour.
# Set to None for an ordinary run. Give either `name` or `center` + `radius_m`.
#   ref         the route as OSM tags it ('I 205', 'I 5')
#   name        an OSM-named structure to close, e.g. 'Abernethy Bridge'
#   center      (lat, lon) to close a stretch around instead of a named structure
#   radius_m    how far along the freeway that stretch reaches
#   close_ramps also close the on/off ramps stranded inside the closed stretch,
#               so cars cannot drive onto a shut freeway. The ramps at the two
#               ends stay open and become the diversion points.
# Default: the Abernethy Bridge, the stretch with the real closure precedent.
# NOTE the tradeoff before citing a run: Abernethy sits 15.2 km from the study
# center where the outer network is under-loaded, while the I-205 stretch beside
# Powell is 5.7 km out where demand is best supported. Choose with the mentor.
FREEWAY_CLOSURE = {
    "ref": "I 205",
    "name": "Abernethy Bridge",
    "center": None,
    "radius_m": None,
    "close_ramps": True,
}

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

# --- En-route rerouting (Phase C1, DEMAND_EXIT_PLAN.md, Aug 2) ---
# The structural gap Phase A2 measured: a vehicle can leave this network ONLY by
# reaching its destination (respawn, or park under the demand profile). When the
# network gridlocks, completions stop, so nothing leaves and the fleet freezes --
# A2's profiled arms held 9,591 and 13,455 stuck vehicle-hours at exact integers
# for hours while the PORTAL curve asked for 2,876 active cars. Routes are planned
# ONCE at spawn against free-flow travel times and never revised, so every car
# queues for a path that stopped being good long ago.
# With this flag on, a vehicle stuck (below STUCK_SPEED_KMH, the same threshold the
# stuck measurement uses) for REROUTE_STUCK_S seconds re-plans from the node it is
# heading toward to its UNCHANGED destination, on congestion-aware weights. It
# keeps its id, destination, emission class, IDM parameters and position, and it is
# never removed -- rerouting conserves total demand and moves only its spatial
# distribution, which is what separates it from trip abandonment (C2, unbuilt on
# purpose: a mechanism that deletes stuck cars would flatter the stuck-time metric
# by construction). Off by default; no committed number moves.
REROUTE_ENABLED = False
REROUTE_STUCK_S = 120.0       # how long a car tolerates being stuck before seeking
                              # an alternative. A-priori and admittedly the softest
                              # constant here: navigation apps re-plan within a
                              # minute or two of detecting delay, and 2 minutes is a
                              # plausible unaided-driver patience. NOT fit to the
                              # held-out counts; treat as a sensitivity knob and say
                              # so with any C1 result.
REROUTE_COOLDOWN_S = 300.0    # a car that just re-planned does not re-plan again for
                              # this long. Without it a still-stuck car would call
                              # Dijkstra every step and thrash between two paths.
REROUTE_MAX_PER_STEP = 20     # COMPUTE BUDGET, NOT PHYSICS -- label it as such in any
                              # result. In the A2 freeze essentially every vehicle is
                              # stuck and would qualify, so an uncapped pass would
                              # re-plan ~13,000 routes per step. Longest-stuck first,
                              # ties by vehicle id, so the choice stays deterministic.

# --- Signed-detour compliance (the fwrqc arm) ---
# A real closure ships with an OFFICIAL detour: ODOT signs I-405 SB for I-5
# through traffic during the Rose Quarter closure. Every other closed arm lets
# each displaced vehicle pick its own fastest route, which models drivers who
# all ignore the signage. This arm models the plan instead: a trip is
# DETOUR-ELIGIBLE when its route on the OPEN network crosses the closed span's
# south exit (those are the through drivers the "THRU TRAFFIC" signs address),
# and each eligible trip follows the signage with probability
# DETOUR_COMPLIANCE_SHARE. A compliant trip routes origin -> via -> destination
# on the closed network, with the via node pinned partway down the signed
# detour so that passing it commits the trip to the loop; the rest of its
# route stays free. Non-compliant and ineligible trips route exactly as
# before. Compliance is decided once at spawn (route-once discipline, same as
# every arm: no replanning) using a DEDICATED RNG stream (RANDOM_SEED + 4,
# alongside +1 signals, +2 fleet, +3 drivers), so the trip stream, and with it
# every registered arm, stays bit-identical while the flag is off.
DETOUR_COMPLIANCE_ENABLED = False
DETOUR_COMPLIANCE_SHARE = 0.5   # P(an eligible trip follows the signage). A
                                # priori with no data behind it, which is why
                                # the campaign registers three levels
                                # (0.25 / 0.50 / 0.75) rather than one guess.
DETOUR_VIA_NODE = 40379068      # I-405 SB near W Burnside: past the I-5
                                # diverge and the first exits, upstream of the
                                # US-26 junction, so routing through it commits
                                # a trip to the signed loop (probed Aug 27; the
                                # arm's --check re-verifies it on the live graph)
DETOUR_MARKER_EDGE = (40413533, 3427976322)   # the closed span's final SB
                                # mainline edge; an OPEN-network route crossing
                                # it is through traffic by definition
DETOUR_GRAPH_FILE = "graph_metro20k_lanes.graphml"   # the OPEN network the
                                # eligibility test routes on, loaded fresh and
                                # prepared under the live flags
# Congested link cost = free-flow time + deterministic queueing delay,
#   t = travel_time_s + (cars on the link) * IDM_T / lanes,
# i.e. how long the queue ahead takes to discharge at saturation headway. This is
# the standard point-queue delay of dynamic traffic assignment, and it introduces
# NO new constant: the saturation headway IS config.IDM_T, the same time gap the
# car-following model already enforces, so the router's estimate and the kernel's
# own physics cannot disagree about how fast a queue drains.
#
# Deliberately NOT the BPR function t = t0*(1 + 0.15*(v/c)^4), despite BPR's
# constants being famously a-priori: BPR's v/c is an HOURLY FLOW ratio from static
# assignment, and applying it to instantaneous queue occupancy is a category
# error. Measured here on the C1 gate: at 90% jam occupancy BPR returns a 1.10x
# penalty, so a fully blocked link still looks essentially free and no driver
# ever diverts. Queueing delay charges that same link ~3.7x, which is the
# behavior a re-plan needs.

# --- Non-work (shopping/errand) demand layer (REAL_DEMAND_UPGRADE_PLAN.md B3, Aug 13) ---
# Every internal trip above is a COMMUTE: LODES OD and the gravity model both send
# people from homes to jobs. Real household vehicle travel is mostly NOT commuting:
# per the 2022 NHTS (FHWA-HPL-24-009, Table 3-6), work trips are 25.7% of household
# vehicle trips while shopping + family/personal errands are 38.6%. With this flag on,
# that measured share of internal (non-through) trips instead draws its origin from
# resident population and its destination from RETAIL/SERVICE employment (the WAC
# sectors below), with a shorter gravity decay, so retail frontage like Powell's gets
# loaded the way real ADT loads it. Origins, attractions, share, and decay are all
# public data set A PRIORI, never tuned against the held-out PBOT counts. Off by
# default: the committed model stays the pure-commute spec until a comparison says
# otherwise; a run with this on must say so in its RUN_NAME.
DEMAND_NONWORK_ENABLED = False
# Share of INTERNAL trips that are non-work. NHTS 2022 Table 3-6 (household vehicle
# trips/yr: work 324, shopping 229, errands 258, all purposes 1,262): (229+258)/1262.
# Applied after the through-traffic split: through trips model a different population
# (regional pass-through), so the household share applies to the internal remainder.
# Social/recreational trips (25.8%) stay on the commute pattern: we have no attraction
# data for them, and that simplification is documented, not hidden.
NONWORK_SHARE = 0.386
# Gravity decay for non-work destinations. NHTS 2022 Table 3-5: shopping trips average
# 5.8 mi and errands 8.7 mi, trip-weighted mean 7.3 mi = 11.7 km, about half the
# 13.5 mi work trip. For an exponential deterrence over a uniform 2D opportunity
# field the mean trip length is ~2x the scale, so scale = 11.7/2 km. A derivation
# with an idealized assumption, stated so it can be checked: nonwork_check.py MEASURES
# the realized mean and reports it rather than re-tuning this number.
NONWORK_DECAY_SCALE_M = 5900.0
# LODES WAC sectors that attract shopping/errand trips: CNS07 retail trade
# (NAICS 44-45), CNS18 accommodation + food services (NAICS 72), CNS19 other
# services incl. repair/personal/laundry (NAICS 81). Chosen a priori as "places
# household errands go"; groceries and big-box are in retail, restaurants in 72.
NONWORK_SECTORS = ("CNS07", "CNS18", "CNS19")

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

# --- Corrected lane counts (real-capacity branch, Aug 17) ---
# The rules above lose road capacity three ways, all measured on the 20 km metro
# graph by src/capacity_audit.py and src/lane_tag_survey.py:
#   1. OSMnx's default download never requested 'lanes:forward'/'lanes:backward',
#      so a two-way street had its lane total halved AND floored: a 3-lane street
#      became 1 lane each way instead of 2 and 1. That hit 20.6% of two-way
#      tagged arterials;
#   2. the 32% of arterial edges with no 'lanes' tag silently fell back to 1;
#   3. one flat LANES_MAX clamped freeways to a residential street's ceiling,
#      catching 100 of the 438 motorway edges.
# With this on, src/lanes_real.py supplies the count instead: directional tags
# win where OSM has them, one-way tags are taken as-is, two-way splits preserve
# the tagged total rather than flooring both directions, untagged edges impute
# the median of their own road class IN THIS GRAPH, exclusive bus/HOV lanes are
# subtracted, and the cap becomes per-class. All from map data; nothing here is
# tuned to the held-out PBOT counts.
# Requires the widened graph from src/build_capacity_graph.py: on the old cached
# graph the directional tags are simply absent and the result degrades to the
# tag-only rules. Off reproduces the committed spec exactly.
LANES_REAL = True
LANES_REAL_GRAPH = "graph_metro20k_lanes.graphml"   # cache written by build_capacity_graph.py

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

# --- Merge entry (capacity branch, freeway-blackspot fix) ---
# The blackspot trace (src/blackspot_trace.py) localized 4 of the 5 too-hard
# freeway jams to junctions where the ENTRY RULE, not road capacity, throttles
# flow: feeders discharge ~1,000 veh/hr per contested lane into a downstream
# edge running free. Two kernel behaviors cause that. (1) A car may only cross
# into the next segment once the rearmost car there has cleared a full jam
# spacing (L + s0) past the entrance, and until then it is held at the line
# with its speed ZEROED, so the discharge serializes into stop-restart cycles
# instead of propagating like a queue wave on a continuous road. (2) With
# explicit MOBIL lanes a crossing car keeps its lane index (clamped), so a
# 2-lane feeder can never enter a 3-lane road's third lane at the junction;
# the extra lane only fills later by lane changes, wasting it exactly at the
# bottleneck. With this flag on: a car crosses as soon as there is physical
# room for its body past the line (rear pos - overhang >= L + eps), keeping
# whatever approach speed the IDM left it, and an entering car targets the
# lane with the MOST ROOM at the entrance (the code's own long-standing
# "a fuller model would pick the emptiest" note) with the spillback-leader
# lookup using that same target lane, so the accel pass and the crossing
# agree. Both changes reuse the existing IDM/spillback machinery; no second
# physics. Off by default: the committed spec and every published number are
# the legacy rule. A-priori design from the trace mechanism, not tuned to
# PORTAL speeds; the 91-station harness stays a held-out grader.
MERGE_ENTRY_IMPROVED = False
MERGE_ENTRY_EPS_M = 0.25    # m: clearance beyond the car body required to cross

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
