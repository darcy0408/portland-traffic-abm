# Demo runbook (for Christof)

Everything Christof has asked for, in the order to show it, with the one command
to run and the one thing to say for each. The runs are fast (the whole demo runs
live in under a minute), but every figure is also pre-saved in `outputs/figures/`
as a backup, so nothing depends on a live run succeeding.

Setup once before the meeting:
    python src/generate.py            # produces the activity + NO2 results
    python src/generate.py closure    # produces the open vs closed results
    python src/scenarios.py           # runs the validation test-bench (4/4 pass)
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
about 330,000 vehicle-steps a second. It scales linearly, so a full-city run is a
matter of more time, not a wall. Vehicle count and network size are both config
knobs, the way you asked."

## 4. Closure experiment (your Jun 23 idea, the headline)

Ask it answers: where the ABM beats a static land-use model.

Run:  python src/generate.py closure
      python src/visualize.py closure
Show: outputs/figures/powell_no2_closure_diff.png

Say: "This is your bridge and I-5 point. I close a block of Powell, the vehicles
reroute, and I difference the NO2 surface before and after. The network total
barely moves, under a percent, but the pollution redistributes onto the parallel
detour routes: SE Holgate up about 96 percent, SE Division about 44 percent, some
quiet blocks several-fold. That redistribution is exactly what a static land-use
surface cannot produce, because the land use never changed. Changing three numbers
in config points this at the I-5 lane closure or a marathon instead."

## 5. Validating the traffic model (your Jun 23 question I could not answer)

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
from 9.3 to 4.5 m/s with 31 percent of cars stopped. Congestion is emergent, not
coded in. All four pass, so I can show the kernel behaves correctly."

Then add: "That is the behavior check. For the real-world check, the NO2 and noise
comparison stays model-to-model by design, because Portland has no dense sensor
truth. But the traffic layer can be checked against real numbers: simulated
volumes and speeds on Powell against the real PORTAL hourly counts, and the ODOT
AADT for the corridor, 34,900 in 2018 at SE 26th. The data is already pulled."

## 6. Weather, scoped as future work (your Jun 23 suggestion)

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
  forest wins, with the traffic layer checked against PORTAL and ODOT.

## Honest limitations to state before he asks

- Signal timing is a uniform assumed cycle, not real per-signal plans (not public).
- Demand is uniform random trips so far; the real time-of-day profile is pulled
  but not yet wired in.
- One emission class (diesel Euro 4) for now.
- Powell is the proof-of-concept and Plan B; the city-wide run is the next scale-up.
These are flagged in config.py as the knobs to set with you.
