# Cold-start factors, sourced (Aug 12 2026)

Companion to COLDSTART_DESIGN.md. This file records the sourced methodology
and the exact tables, per the design doc's rule: nothing implemented until the
factors are sourced. All table and equation numbers below were read directly
from the primary PDF, not from secondary summaries.

## Primary source (RECOMMENDED)

EMEP/EEA air pollutant emission inventory guidebook 2023, Update 2025,
chapter 1.A.3.b.i-iv "Road transport" (passenger cars, light commercial
trucks, heavy-duty vehicles including buses, mopeds and motorcycles).
Version: Guidebook 2023, software COPERT 5.9, updated 2025.
Lead authors Ntziachristos and Samaras.
PDF: https://copert.emisia.com/wp-content/uploads/2025/10/1.A.3.b.i-iv-Road-transport-2025.pdf
(also published via https://www.eea.europa.eu/publications/emep-eea-guidebook-2023)

Applicability stated by the guidebook: the cold-start methodology covers
passenger cars and light commercial vehicles only, and cold-start factors are
NOT a function of vehicle age (p. 52). Cold-start emissions are attributed to
urban driving, secondarily rural (equations 10 and 11, pp. 52-53).

## The method in one paragraph

Total = hot + cold (equation 6, p. 48). Cold-start emissions are an EXCESS on
top of hot emissions, applied to the fraction beta of mileage driven with a
cold engine (equation 10, p. 52):

    E_COLD;i,k = beta_i,k x N_k x M_k x e_HOT;i,k x (eCOLD/eHOT|i,k - 1)

For the ABM this translates per vehicle: a cold-started trip's first
d_cold = beta x l_trip kilometers emit at q = eCOLD/eHOT times the hot rate,
the rest of the trip is hot. That matches the design doc's multiplicative
warm-up factor with a warm-up distance.

## Beta (cold-mileage fraction), Table 3-39, p. 68

    beta = 0.6474 - 0.02545 x l_trip - (0.00974 - 0.000385 x l_trip) x t_a

l_trip is the mean trip length in km, t_a the ambient temperature in deg C
(monthly mean is the stated practical choice). The guidebook says l_trip
should be between 8 and 15 km, and proposes the European default 12.4 km
(Andre et al. 1998) when no national estimate exists (p. 52). Table 3-35
(p. 65) lists national values 9 to 17 km.

WARNING for the ABM: the formula is a fleet-average regression, not a
per-trip law. It goes NEGATIVE near l_trip ~ 25 km (at 5.5 deg C), and metro
ABM trips average ~26 km. Do not feed per-trip lengths into it. The safe
translation is: evaluate beta at the default l_trip = 12.4 km and t_a, then
use d_cold = beta x 12.4 km as a FIXED warm-up distance for every cold start.
At t_a = 5.5 deg C that gives beta = 0.30 and d_cold = 3.8 km, i.e. a cold
engine is warm after about 4 km, which is physically sensible and independent
of how long the rest of the trip is. Short trips (< d_cold) never fully warm,
which the per-vehicle mechanism captures automatically.

## NOx quotients q = eCOLD/eHOT (the tables that matter for us)

Diesel passenger cars, pre-Euro-1 through Euro 5 (Table 3-44, p. 72; valid
-10 to 30 deg C; the guidebook makes NO distinction among diesel classes here
and applies equation 10 directly, no beta-reduction factor):

    q_NOx = 1.3 - 0.013 x t_a
    (CO: 1.9 - 0.03 t_a; VOC: 3.1 - 0.09 t_a; PM: 3.1 - 0.1 t_a)

This is THE factor for the live single-class sim (PC_D_EU4) and for every
pre-Euro-6 diesel class in the mixed fleet.

Petrol passenger cars:
- Conventional (pre-Euro-1), Table 3-38, p. 68, -10 to 30 deg C:
  q_NOx = 1.14 - 0.006 x t_a.
- Euro 1 to Euro 5, Table 3-40, p. 69: q = A x V + B x t_a + C with V the
  MEAN TRIP SPEED in km/h (not instantaneous), two speed bands. NOx rows
  (temp range "> -20"):
    Mini/Small  5-25 km/h: A=4.61E-02, B=7.38E-03, C=0.755
    Mini/Small 26-45 km/h: A=5.13E-02, B=2.34E-02, C=0.616
    Medium      5-25 km/h: A=4.58E-02, B=7.47E-03, C=0.764
    Medium     26-45 km/h: A=4.84E-02, B=2.28E-02, C=0.685
    Large-SUV   5-25 km/h: A=3.43E-02, B=5.66E-03, C=0.827
    Large-SUV  26-45 km/h: A=3.75E-02, B=1.72E-02, C=0.728
  If computed q < 1, use 1 (table note).
- Post-Euro-1 petrol REDUCTION comes through the beta-reduction factor bc
  (Table 3-41, p. 70), applied per equation 26 (p. 70), and the excess is
  anchored to the EURO 1 hot factor and Euro 1 quotient, not the vehicle's
  own:
    E_COLD;i,k = bc_i,k x beta_i,Euro1 x N_k x M_k x e_hot,i,Euro1
                 x (eCOLD/eHOT - 1)|i,Euro1
  bc for NOx: Euro 2 = 0.72, Euro 3 = 0.32, Euro 4 and Euro 5 = 0.18.
  Implementation note: this Euro 1 anchoring matters. A petrol Euro 4 car's
  cold excess is 18 percent of a EURO 1 car's cold excess, which is NOT the
  same as multiplying the Euro 4 car's own hot rate by the quotient.
- Euro 6 petrol (Table 3-42, p. 71; bands split at 0 deg C, valid 5-45 km/h):
  NOx: t_a < 0: A=0.097, B=-0.181, C=5.651; t_a > 0: A=0.089, B=0, C=7.257.
  bc for Euro 6 petrol NOx (Table 3-43): bc = 0.1573 - 0.005 x l_trip.

Diesel Euro 6 (Table 3-45, p. 72, split at 0 deg C; Table 3-46 bc, p. 73):
  NOx t_a > 0: 6a/b/c: A=0.005, B=0, C=2.327; 6d-temp: A=0.038, B=0,
  C=11.929; 6d/e: A=0.048, B=0, C=14.661. bc_NOx = 0.1719 - 0.0055 x l_trip.
  The big quotients reflect tiny Euro 6 hot NOx, not big absolute excess.

General limits: cold-start effect negligible above 25 deg C for CO and 30 deg
C for VOC (p. 70); quotient tables cover -10 to 30 deg C (Euro 6 tables have
their own two-region split at 0 deg C).

## Portland numbers (the winter story)

Portland (PDX) January normal daily mean temperature: 41.9 deg F = 5.5 deg C
(NOAA 1991-2020 climate normals; NWS Portland climate book,
https://www.weather.gov/media/pqr/climate/ClimateBookPortland/pg19.pdf, and
https://www.currentresults.com/Weather/Oregon/Places/portland-weather-in-january.php).

Worked at t_a = 5.5 deg C, l_trip = 12.4 km:
- beta = 0.30, d_cold = 3.8 km.
- Diesel pre-Euro-6 q_NOx = 1.3 - 0.013 x 5.5 = 1.23.
- Trip-level NOx excess for the live diesel class: 0.30 x 0.23 = +7 percent
  on a 12.4 km trip, concentrated on the first 3.8 km.
- Same at a summer 20 deg C: beta = 0.23, q = 1.04, excess about +1 percent.
  The winter minus summer contrast is therefore roughly +6 points of extra
  NOx at trip origins, which is the seasonal signal the branch exists to add.
- Sanity check passes the design doc's expectation (single-digit to low-teens
  percent of urban totals; we land at the low end because NOx cold excess is
  small compared with CO and VOC).

## HBEFA alternative (secondary source, not recommended for now)

HBEFA models cold starts as an EXCESS PER START in grams, interpolated over
ambient temperature, parking time before the start (a proxy for engine
temperature), and trip distance; factors derive from the PHEM engine model,
with updated measurements and nonlinear parking-time effects in HBEFA 4.2
(HBEFA methodology page https://www.hbefa.net/en/methodology and the 4.1
quick reference
https://assets-global.website-files.com/6207922a2acc01004530a67e/64dbad6a13b1ba802b85491f_HBEFA41_help_en.pdf).
Per-start grams with a known parking time is conceptually the better fit for
a per-vehicle ABM, and it stays in the family the hot emissions already use.
But the cold-start tables ship inside the licensed HBEFA application (the
project only has the SUMO-embedded HBEFA3 hot polynomials, which contain no
cold-start module), so the numbers are not freely extractable or citable the
way the EMEP/EEA tables are. Recommendation: implement with EMEP/EEA
(equation 10, Tables 3-39 and 3-44 for the diesel path), and cite HBEFA's
approach as the design alternative in the limitations text. EPA MOVES start
rates remain the US cross-check listed in the design doc, unsourced for now.

## Open gaps before implementation

1. Fleet mapping: each of the 40 HBEFA3 classes in src/fleet.py needs a
   (fuel, Euro band, size) tag to pick its quotient path (diesel pre-Euro-6
   vs petrol Euro 1-5 vs Euro 6 tables). Petrol post-Euro-1 needs the Euro 1
   hot NOx anchor (equation 26), which means carrying one extra reference
   rate per size class, not just a multiplier.
2. The quotient is defined against the trip-average hot factor at mean trip
   speed V. Applying it multiplicatively to the instantaneous per-step
   polynomial while cold is an approximation; document it in the design doc
   when implementing (same spirit as the noise path's documented deviation).
3. Beta per-trip breakdown: use the fixed d_cold translation above, never the
   raw beta formula with per-trip lengths (it goes negative past ~25 km).
4. AMBIENT_TEMP_C config values: 5.5 (January mean) and 20 (summer proxy for
   the existing runs) are the two obvious settings; the exact summer value
   should match the season of the PORTAL demand profile before the winter
   re-test is pre-registered.
5. Through trips enter warm by design, so the V range limit (5-45 km/h) on
   the quotient tables does not bite on freeway entries; internal trips in
   the metro graph rarely average above 45 km/h, but clamp V into [5, 45]
   defensively.
