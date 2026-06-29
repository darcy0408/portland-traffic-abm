# Source-Based Interaction Modeling Captures Traffic Pollution Redistribution That Static Estimation Cannot

**Darcy VanPelt**
Portland State University, Teuscher Lab (NSF REU)
[your contact email]

> DRAFT for ACM SIGSPATIAL 2026 Student Research Competition (undergraduate track).
> Target: 2-page extended abstract, ACM `acmart` sigconf template, one figure.
> Deadline: July 10, 2026 (firm). Submit via EasyChair (sigspatial2026phdsrc).
> Placeholders in [brackets] need your input or a citation you hold.

---

## Abstract

Street-segment surfaces of traffic NO2 and noise are increasingly used as spatial
data products, yet most are produced by static estimation that regresses
pollution onto fixed geographic predictors such as land use, road class, and
population density. Such estimators have a structural blind spot for spatial
systems: their inputs do not depend on the state of traffic on the network, so
the most basic network what-if, removing an edge to close a street, leaves their
predicted surface unchanged. We present an agent-based model in which individual
vehicles interact on an OSMnx street network, following one another, queuing at
signals, and backing up in congestion, and we use the resulting simulated traffic
to generate the pollution predictors, mapped to per-segment NO2 (HBEFA emission
factors) and noise (the EU CNOSSOS method). Under an edge-removal (road-closure)
experiment, the agent model redistributes 68 to 80 percent of a closed arterial's
NO2 onto the parallel routes that detouring traffic takes up, a behavior the
static surface cannot reproduce by construction. The contribution is a
demonstration of capability, not a claim of greater accuracy: source-based
interaction modeling captures the spatial redistribution of traffic pollution
that static estimation, by the nature of its inputs, cannot.

**Keywords:** road networks, what-if and counterfactual analysis, spatial
surfaces, agent-based modeling, traffic simulation, urban computing, air quality,
NO2, environmental noise, OSMnx.

---

## 1. Introduction

Fine-scale urban surfaces of NO2 and road-traffic noise are increasingly treated
as spatial data products, per-segment maps that downstream systems query for
routing, facility siting, and exposure analysis. Most are produced by static
estimation: a model (land-use regression, or a land-use random forest) is fit on
fixed geographic predictors, land use, road classification, population density,
distance to major roads, and predicts pollution at street-segment resolution.
These estimators are accurate where conditions are stable and are inexpensive to
deploy.

They share one structural limitation that matters specifically for spatial
systems. Their predictors describe the fixed configuration of the city, not the
state of traffic on the network. Consider the most basic counterfactual a spatial
system might pose to such a surface: remove an edge (close a street) and ask how
the pollution map responds. Because none of the estimator's land-use inputs
depend on the network's traffic state, its prediction is provably invariant under
the edge removal: the surface cannot change in response to the very perturbation
that changed the traffic. The model is blind, by construction, to network-level
redistribution.

We show that source-based interaction modeling supplies exactly what the static
surface lacks, and we make the claim falsifiable with an edge-removal experiment
on a real road network. We build an agent-based model (ABM) of vehicles that
follow, queue, and congest on the Portland arterial network, derive per-segment
NO2 and noise surfaces from the simulated traffic, and compare against a strong
static baseline under the same closure. Dynamic chains linking microscopic
traffic to NO2 and noise exist [Tirico 2025]; our contribution is not the chain
but the spatial comparison against static estimation, and the demonstration of a
redistribution effect, traffic and its pollution moving onto parallel routes when
an edge is cut, that static spatial estimators cannot represent.

## 2. Method

**Network and vehicle dynamics.** We model individual vehicles on an OSMnx street
network of the SE Powell Boulevard corridor in Portland (978 nodes, 2,838
directed edges). Vehicles are assigned origin-destination routes that minimize
travel time and advance segment by segment under an intelligent-driver
car-following kernel [Treiber 2000], adjusting speed to the vehicle ahead. They
queue at 21 OSM-tagged signalized intersections under a two-phase cycle, and a
vehicle with no leader on its own segment brakes for a queue spilling back from
the next segment and holds at the stop line rather than overlapping into it. From
these interactions congestion emerges: mean speed drops and queues stack, the
behavior that justifies an ABM rather than a static flow assignment.

**Emissions and noise.** From each vehicle's instantaneous speed and acceleration
we accumulate NOx per segment using an HBEFA-derived NOx(v, a) factor [HBEFA].
The NO2 surface is reported as a fixed NO2/NOx fraction applied in
post-processing, so the fraction retunes without rerunning the simulation. The
same simulated traffic drives a second surface: per-segment road-traffic noise in
dB(A), computed with the EU CNOSSOS method [EU 2015/996] over octave bands with
A-weighting, made congestion-aware by recovering realized mean speed per segment.

**Common-ground comparison.** Per-segment traffic predictors aggregated over
multiple buffer radii (100 to 1200 m) form the inputs a static model would use.
This lets the agent-based and static approaches be compared on the same features
and the same network, isolating what the interaction dynamics add.

## 3. Experiment and Results

We compare the agent model against a static baseline: a random forest fit on
land-use and network predictors, with an out-of-bag R squared of 0.51. The
baseline is well fit and is not a strawman.

We then pose the edge-removal counterfactual: close a 150 m zone on the arterial
(24 directed segments) and rerun the same travel demand so vehicles reroute
around it. The static surface does not
change, because none of its land-use inputs change. The agent model strips 68 to
80 percent of the closed arterial's NO2 from the closed stretch and redistributes
it onto the parallel routes that detouring traffic takes up; on SE Powell the
closed stretch drops about 82 percent while parallel arterials such as SE
Division rise sharply. The net network-total NO2 changes only slightly (the
detours are longer and slower), so the effect is redistribution, not a change in
magnitude, exactly what a static surface cannot produce.

The result is robust across six random seeds and generalizes across three
different arterials, and it corresponds to a shift in modeled NO2 exposure for
roughly 11,000 residents when the per-segment surface is intersected with
block-group population.

**Figure 1.** The same closure shown two ways on a single change scale: the
static land-use model (zero change on every segment) beside the agent model
(NO2 stripped from the closed arterial and redistributed onto the parallels).
[Generated by `static_vs_abm.py`.]

## 4. Discussion, Limitations, and Ongoing Work

The contribution is a demonstration of capability, not a claim of greater
absolute accuracy. Portland has sparse pollution ground truth, only two
regulatory NO2 monitors in the metro, so we frame this honestly as a comparison
between methods rather than against measurement. What the experiment establishes
is that an interaction-based model reproduces a spatial redistribution of traffic
pollution that static estimation, by the nature of its inputs, cannot. The same
pipeline yields a second surface, road-traffic noise, extending the result beyond
a single pollutant.

Current simplifications are flagged for calibration with domain mentors: an
assumed uniform signal cycle (Powell runs adaptive SCATS control, with no
published fixed plan), a single emission class, and an NO2/NOx fraction taken
from the literature range. Ongoing work compares the agent-generated NO2 surface
against a published land-use random-forest baseline for the same city [Rao 2017],
holding the statistical method fixed so that only the predictor source differs and
using spatial block cross-validation [Roberts 2017] so the comparison is not
inflated by spatial autocorrelation between nearby segments; the noise surface is
compared against the U.S. FHWA Traffic Noise Model [FHWA TNM] as a mechanistic
reference.

## Acknowledgements

This work was conducted in the NSF REU "Computational Modeling Serving Portland"
at the Portland State University Teuscher Lab, advised by Christof Teuscher. AI
assistance (a coding and writing assistant) was used in developing the software
and preparing this abstract.

## References

- [Tirico 2025] M. Tirico, Y. Gao, D. Sengelin, P. Gastineau, et al. Modeling
  traffic-related air and noise pollution: Multi-criteria assessment case study
  around schools. *Transportation Research Part D*, 149:105029, 2025.
- [Boeing 2017] G. Boeing. OSMnx: New methods for acquiring, constructing,
  analyzing, and visualizing complex street networks. *Computers, Environment and
  Urban Systems*, 65:126-139, 2017.
- [Treiber 2000] M. Treiber, A. Hennecke, D. Helbing. Congested traffic states in
  empirical observations and microscopic simulations. *Physical Review E*,
  62(2):1805, 2000.
- [HBEFA] Handbook Emission Factors for Road Transport (HBEFA), version 3.
  NOx(v, a) factors as implemented in the SUMO emission model [SUMO].
- [SUMO] P. A. Lopez, M. Behrisch, L. Bieker-Walz, et al. Microscopic traffic
  simulation using SUMO. In *IEEE Intelligent Transportation Systems Conference
  (ITSC)*, 2018.
- [EU 2015/996] Directive (EU) 2015/996 establishing common noise assessment
  methods (CNOSSOS-EU). Official Journal of the European Union, 2015.
- [Rao 2017] M. Rao, L. A. George, V. Shandas, T. N. Rosenstiel. Assessing the
  potential of land use modification to mitigate ambient NO2 and its consequences
  for respiratory health. *International Journal of Environmental Research and
  Public Health*, 14(7):750, 2017.
- [Roberts 2017] D. R. Roberts, V. Bahn, S. Ciuti, et al. Cross-validation
  strategies for data with temporal, spatial, hierarchical, or phylogenetic
  structure. *Ecography*, 40(8):913-929, 2017.
- [FHWA TNM] U.S. Federal Highway Administration. Traffic Noise Model (TNM).
  [fill exact technical-manual citation, e.g. Menge et al., FHWA-PD-96-010, 1998.]
