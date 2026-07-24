# Noise-path accuracy backlog

Captured 2026-07-24. Improvements to the CNOSSOS noise surface (`src/noise.py`),
ranked by how much they'd actually matter for a Portland arterial (Powell), and
flagged where an item is *on-brand for the ABM* (something a static model can't do
but our interaction model can). None of these are built. All are honestly listed
today as dropped terms in the `src/noise.py` module docstring (see the "Terms we
DROP" list, ~line 74-83).

Context for the chapter: the whole comparison is CNOSSOS (EU-fitted) vs FHWA TNM
(US-fitted) — see `NOISE_TNM_DESIGN.md`. Several items below (road surface,
vehicle fleet) are exactly the US-vs-Europe divergence that comparison surfaces,
so they double as limitations-section material, not just code TODOs.

## Prioritized tasks

1. **Heavy vehicles (trucks + buses).** Biggest gap for an arterial, likely bigger
   than road surface. We implement CNOSSOS category 1 (light vehicles) only;
   categories 2 (medium) and 3 (heavy) are ~8-10 dB louder *each* and dominate a
   truck/bus route like Powell. Add the cat 2/3 coefficient tables and energy-sum
   per category weighted by fleet share. **Reachable:** the parked `src/fleet.py`
   experiment already carries a vehicle mix — wire that share into the noise source
   instead of assuming all cars.

2. **Acceleration/deceleration correction at junctions.** *ABM's home advantage —
   highest strategic value.* CNOSSOS defines a junction correction that raises
   propulsion noise where vehicles accelerate away from a stop. A static model has
   to guess where that happens; our ABM *knows* — it simulates queueing and
   discharge at signals. Building this lets the noise path demonstrate the same
   "source-based interaction modeling beats static estimation" thesis as the NO2
   path. Needs per-segment accel state exported from a run (not currently saved).

3. **Road-surface correction (US vs European reference pavement).** The rolling-noise
   coefficients (`AR_CAT1`/`BR_CAT1`) are defined for the CNOSSOS *virtual reference
   road surface* — a European average (~dense asphalt concrete 0/11 + stone mastic
   asphalt 0/11). We apply zero correction, so every Portland segment is implicitly
   assumed European-paved. CNOSSOS provides an explicit dL_WR(surface) term to adjust
   from the reference surface to the actual one; Portland has different asphalt mixes
   and some rigid Portland-cement-concrete sections (louder). Systematic bias on the
   rolling term (dominant above ~30-40 km/h). Even a single network-wide constant
   offset would be more honest than zero. Doubles as a chapter limitation and is part
   of the US-vs-EU story.

4. **Studded-tire correction (Oregon-specific).** Legal in Oregon Nov-Mar; CNOSSOS
   has a studded-tire correction adding several dB to rolling noise. Out of scope for
   a summer run, but a real Portland-accuracy factor — at minimum a limitations
   sentence, at most a winter-scenario variant.

5. **Propagation terms (ground effect, barriers/building facades, finite segment
   geometry vs. our infinite-line assumption, atmospheric + meteorological
   correction).** These are the largest *absolute*-level gaps, but they are exactly
   what TNM does and our v1 deliberately doesn't — our CNOSSOS surface is
   source-focused by design, keeping the two pipelines symmetric (see
   `NOISE_TNM_DESIGN.md` sec 3). Best framed as "that's the propagation side, held
   identical/dropped on both sides of the comparison," not as bolt-ons that compete
   with TNM. Lower priority for *this* project's research question.

6. **Temperature correction to rolling noise.** Minor. Lowest priority.

## Recommended order if/when this is picked up
#2 (accel-at-junctions) first — it's the one that both improves accuracy *and*
proves the ABM thesis. #1 and #3 are the most honest bias terms to name in the
chapter regardless of whether they're coded. #5 stays framed as TNM's job.
