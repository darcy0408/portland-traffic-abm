# Demo runbook (for Christof)

Everything Christof has asked for, in the order to show it, with the one command
to run and the one thing to say for each. The runs are fast (the whole demo runs
live in under a minute), but every figure is also pre-saved in `outputs/figures/`
as a backup, so nothing depends on a live run succeeding.

Setup once before the meeting:
    python src/generate.py            # produces the activity + NO2 + throughput results
    python src/generate.py closure    # produces the open vs closed results
    python src/static_vs_abm.py       # static-vs-ABM closure contrast figure (section 5)
    python src/scenarios.py           # runs the validation test-bench (4/4 pass)
    python src/traffic_counts.py      # pulls the real PBOT counts (once, cached)
    python src/validate_traffic.py    # validates the model against those counts
    python src/visualize.py           # activity map
    python src/visualize.py no2       # NO2 map
    python src/visualize.py closure   # before/after closure map

---

## 1. The core ABM, the part that justifies the method

Ask it answers: why an agent-based model at all, not statistics.

Run:  python src/generate.py
Show: outputs/figures/powell_no2_segment_map.png  (traffic activity)

Say: "Every vehicle drives the real Powell network and follows the car ahead with
the Intelligent Driver Model. 21 real signalized intersections cycle, cars queue
at red, and queues spill back across intersections. The congestion on the map is
not assigned, it emerges from the cars interacting. That interaction is the whole
reason to use an ABM instead of a static estimate."

## 2. The NO2 surface (week 5, done early)

Ask it answers: the first of the two output surfaces.

Run:  python src/visualize.py no2
Show: outputs/figures/powell_no2_no2_map.png

Say: "Each car's instantaneous speed and acceleration drive the HBEFA3 emission
model, so NOx accumulates per street segment, and the NO2 surface is that NOx
scaled by a primary-NO2 fraction. The arterials and intersections concentrate
harder than a land-use map would, because the surface comes from where the cars
actually slow, stop, and queue."

## 3. Runtime scaling (your Jun 22 question)

Ask it answers: how the model scales, the computational-complexity read you asked for.

Run:  python src/generate.py benchmark
Show: the printed table (runs instantly)

Say: "Holding the network fixed and turning vehicles up from 50 to 1000, the
runtime grows right in step with the vehicle count and throughput stays flat at
about 300,000 vehicle-steps a second. It scales linearly, so a full-city run is a
matter of more time, not a wall. Vehicle count and network size are both config
knobs, the way you asked."

## 4. Closure experiment (your Jun 23 idea, the headline)

Ask it answers: where the ABM beats a static land-use model.

Run:  python src/generate.py closure
      python src/visualize.py closure
Show: outputs/figures/powell_no2_closure_diff.png

Say: "This is your bridge and I-5 point. I close a block of Powell, the vehicles
reroute, and I difference the NO2 surface before and after. The network total
rises only a little, about 2 percent, because the detours are longer and slower,
but the pollution redistributes onto the parallel routes: SE Powell drops about 82
percent in the closed stretch, SE Division more than doubles at plus 132 percent,
SE Holgate up about 54 percent, and some quiet side streets several-fold. That
redistribution is exactly what a static land-use surface cannot produce, because
the land use never changed. Changing three numbers in config points this at the
I-5 lane closure or a marathon instead."

## 5. Why a static land-use model can't do this (the contribution, in one picture)

Ask it answers: what is the geospatial contribution, made undeniable. This is the
punchline of the closure result and the centerpiece of the SIGSPATIAL abstract.

Run:  python src/static_vs_abm.py
Show: outputs/demo/5_static_vs_abm_closure.png

Say: "Same closure, same color scale, two methods side by side. The left is a
land-use random forest, the same method Rao uses. It is blank: zero change on every
segment. Not because my land-use model is weak, but because a road closure changes
nothing about land use, so any model built on land use is frozen. The right is my
agent model, and it lights up: NO2 comes off SE Powell and lands on the parallel
arterials, SE Division and SE Holgate. That network-responsive surface is the
contribution, and it needs nothing from Rao's data."

If he pushes ("is that a fair static model, or a strawman?"): "It does not matter how
good the static model is. Even Rao's full, well-tuned forest would show exactly zero
change here, because its inputs do not move when a road closes. Only a source-based
model can respond. That is the whole argument." Backup point in reserve: that land-use
forest barely predicts the NO2 surface at all (out-of-bag R2 of -0.16), because the
pollution concentrates on the road network, which land use describes only crudely. So
the agent model is both more faithful to where pollution is and the only one that
responds to network change.

## 5b. The redistribution is robust and general (not one lucky seed)

Ask it answers: is the closure result real, or an artifact of one random run?

Run:  python src/closure_robustness.py
Show: outputs/demo/7_closure_robustness.png

Say: "To check it is not noise, I closed three different arterials, Powell, Division,
and Holgate, each under six random seeds. The headline is the closed street's own drop:
it loses 68 to 80 percent of its NO2 every single time, with a spread of only a few
points across seeds. That is rock-solid, not a fluke. And it generalizes: close any one
arterial and its pollution collapses and reroutes onto the parallels. So this is a
method, not a one-off. One honest detail: the size of the gain on each parallel varies
more by seed than the drop does, and I report that rather than hide it."

Note if he asks about the +132% on the earlier slide: that is the pinned seed-42 run
that every map is rendered from, the reproducible representative. The 6-seed average
for SE Division is +93%, so seed 42 sits near the top of the range. Both are honest;
I lead with the reproducible run and show the ensemble as the robustness check.

## 5c. Who breathes it: population exposure (the human stake)

Ask it answers: who cares, in human terms.

Run:  python src/exposure.py
Show: outputs/demo/6_exposure_change.png

Say: "A closure does not just move pollution, it moves whose air it lands in. Using
Census block-group population, closing one block of Powell raises modeled NO2 for about
11,000 residents and lowers it for about 12,000, a roughly 9 percent rise in the
population-weighted average. The neighborhoods on the detour routes see the biggest
increases. This is modeled NO2, a relative comparison and not measured air quality, but
it turns a pollution map into an exposure-and-equity result, which is the health stake
behind the whole project."

## 6. Validating the traffic model (your Jun 23 question I could not answer)

Ask it answers: how I know the traffic is realistic. You said I do not have to
understand every line, but I have to be able to SHOW it works. So this is in two
parts: behavior first, then real numbers.

Run:  python src/scenarios.py
Show: the PASS/FAIL output (4/4 pass) and outputs/figures/scenarios.png

Say: "I built a test-bench that runs the exact scenarios you named through the
real simulation kernel, not a copy of it, and checks each against what it must do.
One car on an open road accelerates to the limit and holds. A follower keeps a
safe gap and never overlaps the leader, settling at the 9.5 m headway the model
predicts. A car at a red light stops two meters short of the line, never runs it,
and departs on green. And placing 1,500 cars on the network drops the mean speed
from 9.6 to 3.5 m/s with 34 percent of cars stopped. Congestion is emergent, not
coded in. All four pass, so I can show the kernel behaves correctly."

Then, the real-world check (your Jun 25 count data):

Run:  python src/traffic_counts.py      # ~2,200 real PBOT counts in the Powell area
      python src/validate_traffic.py    # snaps each to the model and scores it

Say: "That was the behavior check. For a real-world check I used the city's own
counts, the PBOT volume data you sent. I pulled the roughly 2,200 count points in
the Powell area and snapped each to the nearest street in the model. I score it
with a rank correlation, because the absolute levels should not match yet; the fair
first question is whether the model puts heavy traffic where the city actually
measures it. And one honest thing I caught doing this: my first comparison used
time-occupied per segment, which over-counts congested blocks where cars sit in
queues; switching to a true vehicle count through each segment raised the correlation
from 0.16 to 0.26. From there, two changes drove it further. Routing cars by travel
time instead of shortest distance raised the held-out correlation from 0.26 to 0.38,
the real win. Then I calibrated demand with a gravity model drawn from real Census
population and LODES jobs, kept independent of these PBOT counts so the test stays
honest. The full model sits at 0.33: the gravity demand costs a little on this one
rank metric, because the metric is dominated by network structure that betweenness
already captures, but it is what makes the closure and time-of-day results meaningful,
so I keep it on. That is an honest negative, and I report it rather than quietly
switching to the config that scores highest. The NO2 and noise surfaces stay model-to-model by design,
because Portland has no dense sensor truth; this count check is for the traffic
layer specifically."

## 7. Weather, scoped as future work (your Jun 23 suggestion)

Ask it answers: the wind and rain idea, kept simple.

Say: "I scoped the weather idea you raised. Rain is the easy piece, a tunable
factor that lowers the NO2 surface on rainy hours, and the data is a clean API
pull, not web scraping. Wind actually moves pollution across space, so I would
keep that as a later, simpler approximation, not a full dispersion model. I have a
first version of the rain piece working off real Portland rain hours, but I am
treating it as future work, behind the Rao comparison, the way you suggested."

(Optional, only if he wants to see it: the rain prototype lives outside the repo
in a private sandbox. Run `python sandbox/weather/rain.py`.)

---

## Have ready for his usual questions

Research vs engineering: "The research is whether feeding the same random forest
ABM traffic predictors instead of land-use predictors changes the NO2 surface,
especially near busy roads, closures, and intersections. The routing and rerouting
are engineering I use to get there, not the contribution."

What tools did you use: "Python, OSMnx, NetworkX, NumPy, pandas, Matplotlib, the
HBEFA3 emission factors from SUMO, and Claude Code as a pair-programming assistant
for the build."

Heilmeier, in plain language:
- What are you trying to do: build traffic as moving, interacting cars and turn
  that into NO2 and noise surfaces, then test if it beats a static land-use model.
- Why is it hard / why now: static models smooth over exactly the places that
  matter, busy roads and closures; an ABM can represent those, and the network
  and emission tools are now open and fast enough to run.
- What is new: the predictors come from a source-based agent simulation, not from
  describing the land around a point.
- Who cares: NO2 worsens childhood asthma, so this is a health and planning
  question, especially under disruptions like the I-5 closure.
- How do you measure success: a rigorous model-to-model comparison, valid whichever
  forest wins, with the traffic layer validated against the city's real traffic
  counts (held-out rank correlation 0.33 for the full model, up from 0.26 after
  switching to travel-time routing).

## Honest limitations to state before he asks

- Signal timing is a uniform assumed cycle, not real per-signal plans (not public).
- Demand uses a gravity model from real Census population and LODES jobs (held out
  from the PBOT counts), not uniform random trips. On the PBOT rank check the full
  model scores 0.33; gravity does not beat uniform demand on that one metric (an
  honest negative, since the metric is dominated by network structure), but it is
  required for the closure and time-of-day experiments to be meaningful.
- One emission class (diesel Euro 4) for now.
- Powell is the proof-of-concept and Plan B; the city-wide run is the next scale-up.
These are flagged in config.py as the knobs to set with you.
