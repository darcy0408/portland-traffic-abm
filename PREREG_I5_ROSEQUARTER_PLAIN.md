# Pre-registration, in plain language: Rose Quarter I-5 Southbound Closure

**Closure starts September 11, 2026**

**Author:** Darcy Van Pelt
**Advisor:** Christof Teuscher, Portland State University

> This page is a plain-language restatement, written August 14, 2026, after
> the campaign ran. The binding document is `PREREG_I5_ROSEQUARTER.md` as
> committed at `f76d27c`, before any campaign task ran; this page changes no
> rules, no metrics, and no verdicts.

ODOT's Rose Quarter project, project no. 19071, will completely close
**southbound I-5** between the **I-405 and I-84 interchanges** starting
**September 11, 2026**. The closure will run **24 hours a day for up to five
weeks**.

Drivers will be officially detoured onto **I-405 southbound**, while regional
traffic will also be directed toward **I-205**.

This gives us a rare chance to test the model against a real freeway closure.
The model can make its predictions now, before the closure happens, and then
we can compare those predictions with real traffic data from ODOT's PORTAL
loop detectors.

The purpose of this document is to lock in:

* exactly how the closure will be modeled,
* which measurements will be used,
* what counts as a supported result,
* and how the model will later be compared with reality.

Nothing gets changed after we see the answers.

---

## 1. How the closure is modeled

The Rose Quarter closure is defined as:

`SCENARIOS["rosequarter"]`

in:

`src/freeway_runs.py`

The model identifies I-5 around:

**45.5355, -122.6690**

using an **800-meter radius**.

The closure is set to direction **"S"**, meaning only the **southbound** side
of I-5 is removed. **Northbound I-5 stays open.**

### Exactly what is removed

The model removes exactly **5 network edges**.

Three of them are southbound I-5 mainline edges:

* `(40382443, 40397036, 0)`
* `(40397036, 40413533, 0)`
* `(40413533, 3427976322, 0)`

Together, those mainline pieces cover **1,628 meters**, approximately the
I-405-to-I-84 closure area.

The model also removes **2 ramp edges** that would otherwise be stranded
inside the closed section.

Every campaign task checks these five edges before running. If the graph does
not match this exact closure, the task refuses to run.

That check is implemented in:

`src/freeway_rosequarter.py`

### Experimental setup

There are two versions of each simulation:

**Open:** I-5 operates normally.

**Closed:** the Rose Quarter southbound closure is in place.

Everything else stays the same.

The same random seed is used for both versions so they can be compared
directly.

The campaign uses these **8 established seeds**:

**42, 7, 13, 99, 314, 777, 2024, and 8**

There are:

* **8 seeds**
* **2 conditions**
* **16 total simulation tasks**

The campaign prefix is:

`fwrq`

The model uses the same base configuration as the earlier freeway experiments
so the results remain comparable.

The mixed vehicle fleet is used when calculating absolute emissions in grams.

The freeway and highway routes tracked are:

* I-5
* I-405
* I-205
* OR-213
* OR-99E
* US-26

---

## Important model limitations

These limitations are being stated **before** comparing the model with
reality.

### Time

The simulation represents **one steady-state hour**.

The real closure lasts **24 hours a day for as long as five weeks**.

### Local-access lane

The real closure will leave a local-access lane serving Broadway/Weidler.

The model does **not** represent that special lane.

Instead, the modeled span closes completely.

### Ramp closures

The model's stranded-ramp removals are an approximation of ODOT's announced
ramp closures.

### Travel demand

The model uses:

* **2021 LODES commuting data**
* plus a fixed **15% through-traffic share**

That means it does **not** include many other kinds of trips, such as
shopping or errands.

It also cannot currently represent people reacting to the closure by:

* deciding not to travel,
* traveling at a different time,
* switching to transit,
* or switching transportation modes.

### Route choice

Vehicles choose their route once when they enter the simulation.

They choose using **free-flow travel times**.

They do **not** change routes later because of congestion.

---

## 2. How diversion will be measured

The most important question is:

**Where do the drivers who would normally use the closed I-5 section go
instead?**

For this analysis, an **affected trip** means:

> A trip whose planned route in the normal, open-road simulation uses at
> least one of the five edges in the frozen closure area.

### Keeping the comparison fair

For each seed, the origins and destinations are generated once.

Those **exact same trips** are then routed twice:

1. on the normal network,
2. and on the network with I-5 southbound closed.

If a trip has no possible path after the closure, it is dropped and counted.

Before running the experiment, the expectation was **0 dropped trips**,
because a southbound detour route exists.

### D1: How many affected drivers use the detour freeways?

For both **I-405** and **I-205**, calculate the percentage of affected trips
whose route uses that freeway.

Compare:

**open network vs. closed network**

for every seed.

### D2: How many drivers actually increase their use of the detour freeway?

For each affected trip, measure whether the closure causes that trip to
travel a greater distance on:

* I-405,
* or I-205.

This is stronger evidence of diversion than simply asking whether the trip
touches the freeway at all.

### D3: How much additional freeway travel is created?

Calculate the additional mainline vehicle-kilometers caused by the closure
on:

* I-405,
* and I-205.

This is calculated for each seed using the exact same trip population in the
open and closed networks.

### Secondary measurements

The simulations also report the normal corridor totals for:

* NOx emissions,
* and throughput.

Those totals are useful, but they are treated as **secondary evidence**.

Earlier work showed that a relatively small amount of freeway diversion can
disappear inside normal seed-to-seed noise when looking only at an entire
corridor total.

That is why the trip-level D1-D3 measurements are the main diversion test.

---

## 3. What counts as a supported result?

The rules are frozen before looking at the outcome.

There are **8 paired seeds**.

A directional claim counts as **SUPPORTED** only if:

1. all **8 seeds point in the same direction**, and
2. the paired test gives **|t| > 3**.

Trip-level percentages will be reported using the:

**mean ± standard deviation**

No parameters will be adjusted after seeing the results.

If the result is null, it will be reported as null.

---

## 4. Predictions made before the real closure

Before running the real-world validation, the predicted direction of change
is:

### Closed I-5 section

Traffic on the modeled southbound closure span will go to **zero**, because
those roadway edges are removed.

### I-405 southbound

Traffic will go **UP**.

### I-205

Traffic will go **UP**.

The exact numbers and the rank order of the detour routes are calculated from
the campaign and added below before the September 11 closure.

---

## 5. How the predictions will be compared with reality

ODOT's **PORTAL** system stores hourly loop-detector traffic volumes on:

* I-5,
* I-405,
* and I-205.

The real-world comparison follows rules decided in advance.

### Rule 1: Compare the direction

For each freeway corridor, ask whether traffic went:

* up,
* down,
* or did not clearly change

from before the closure to during the closure.

### Rule 2: Compare the ranking

Compare which detour corridor experiences the larger **relative increase**.

### Rule 3: Do not compare absolute model and real-world traffic volumes

The model has fixed demand.

Real drivers can:

* cancel trips,
* travel at different times,
* change routes,
* change transportation modes,
* or gradually adapt over the five-week closure.

So the important comparison is the **direction and relative size of the
changes**, not whether the model reproduces the exact number of vehicles.

The first days of the closure are preferred because drivers will have had
less time to adapt.

### Rule 4: Each detector is compared with itself

A PORTAL detector is compared:

**before closure vs. during closure**

The analysis does **not** directly compare traffic counts from one detector
against another detector.

That matters because different stations may cover different numbers of lanes.

### Frozen PORTAL station list

These stations were checked and confirmed to be reporting live data on
**August 13, 2026**.

Only mainline **"2DS"** stations are used.

Ramp-meter stations are excluded because their lane definitions are less
reliable.

**Inside the I-5 southbound closure area.** Prediction: traffic falls to
approximately the remaining local-access traffic.

* **3121 (Broadway)**
* **10642 (Russell)**

**I-5 southbound approaching the closure.** Prediction: traffic goes down.

* **3172 (I-405 split)**
* **10640 (Alberta)**

**I-5 southbound downstream of the I-84 merge.**

* **3120 (N. Morrison Br)**
* **3185 (Madison)**

**I-405 southbound, the official signed detour.** Prediction: traffic goes
up.

* **3122 (the SB I-5 to SB I-405 transfer itself)**
* **3196 (Broadway)**
* **3110 (Jefferson)**

**I-205 southbound, the regional detour.** Prediction: traffic goes up.

* **10579 (Government Island)**
* **3107 (Prescott)**
* **10582 (Maywood Park)**
* **3105 (Halsey)**

If one of these stations stops reporting before September 11, it can be
removed only by rerunning the coverage check on a **pre-closure baseline
day**, before looking at any closure-period results.

Baseline days will use the **same weekday before September 11**, while
avoiding **Labor Day week**.

---

## 6. Possible demand-realism version

A second version of the model is being developed that adds non-work trips
such as:

* shopping,
* errands,
* and other everyday travel.

If that version is ready before September 11, its predictions can be added as
a **separate, clearly labeled pre-registered analysis**.

It must be added in a dated appendix **before the actual closure begins**.

It will not replace the primary experiment described above.

---

## Appendix A (August 14, 2026): numeric predictions are now calculated and banked

Nothing in the rules above has been changed.

The simulation campaign has now run:

**SLURM array 126285**

All:

**16 of 16 tasks completed**

on **August 13, 2026**.

The trip-level D1-D3 analysis was run using:

`src/rosequarter_d123.py`

on **August 14, 2026**.

This second analysis performs routing calculations only. It does not rerun
the traffic simulation.

These are now the model's official numeric predictions for the September 11
closure.

### A.1 Corridor-level results

These numbers compare:

**closed minus open**

for each paired seed.

The frozen rule remains:

A result is supported only if all 8 seeds agree on the direction **and
|t| > 3**.

The percentages below refer to the route's NOx total.

| Route                                  | Mean change |   SD |             Range | Same-direction seeds | Verdict                 |
| -------------------------------------- | ----------: | ---: | ----------------: | -------------------: | ----------------------- |
| **I-405 (signed detour)**              |  **+84.9%** | 16.7 | +55.6% to +108.3% |                  8/8 | **SUPPORTED, t = 14.4** |
| **I-205 (regional detour)**            |   **+3.1%** |  8.1 |   -4.1% to +17.7% |                  4/8 | Not supported, t = 1.1  |
| **I-5 (whole route, both directions)** |   **-0.8%** |  2.0 |    -5.0% to +1.8% |                  3/8 | Not supported, t = 1.1  |
| **OR-213**                             |   **+2.9%** | 10.9 |  -10.4% to +26.9% |                  5/8 | Not supported, t = 0.8  |
| **US-26**                              |   **-0.6%** |  3.6 |    -6.0% to +3.9% |                  4/8 | Not supported, t = 0.4  |

OR-99E is on the tracked-route list but has no row here: the network graph
carries no motorway-class edge tagged with that route, so the campaign
records no mainline values for it.

### What those percentages mean in actual emissions

The percentages need to be read alongside their starting values because the
freeways are very different sizes.

**I-405.** I-405 increases by:

**+813 ± 159 grams of NOx per simulated hour**

from an open-road starting value of:

**959 grams**

That is why the percentage increase is so large.

**I-205.** I-205 increases by:

**+450 ± 1,249 grams of NOx per simulated hour**

from an open-road starting value of:

**16,333 grams**

I-205 is already carrying a much larger amount of traffic and emissions, so
even several hundred additional grams produce a relatively small percentage
change.

### Main prediction

The predicted ranking is:

**1. I-405: largest relative increase**
**2. I-205: much smaller and weak increase**
**3. Surface alternatives: changes too inconsistent to separate from seed
noise**

The frozen PORTAL station predictions are therefore:

* **I-5 inside the closure:** down to roughly the local-access residual
* **I-5 approaching the closure:** down
* **I-405 southbound:** up strongly
* **I-205 southbound:** up weakly

### A.2 What happens to the individual trips?

Across the 8 seeds, between:

**575 and 667 trips per seed**

would normally travel through the closed I-5 section.

That is about **620 affected trips per seed**, which is **3.8% of each
seed's 16,500 spawned vehicles** (4,962 affected trips out of 132,000
spawned across all eight seeds).

### D1: How many affected trips use each detour freeway?

**I-405.** Before the closure:

**16.4% ± 2.0%**

of affected trips use I-405.

After the closure:

**58.4% ± 1.7%**

use I-405.

That is a very large shift toward I-405.

**I-205.** Before the closure:

**7.5% ± 0.8%**

of affected trips use I-205.

After the closure:

**10.1% ± 0.9%**

use I-205.

That is an increase, but much smaller.

### D2: How many affected trips actually travel farther on the detour freeway?

**I-405.**

**48.9% ± 2.1%**

of affected trips increase the amount of I-405 mainline they travel.

**I-205.** Only:

**5.8% ± 0.7%**

increase the amount of I-205 they travel.

So the model predicts that roughly **half of the affected drivers add I-405
travel**, while only about **1 in 17 adds I-205 travel**.

### D3: How much extra freeway travel is added?

**I-405.** The closure adds:

**+1,187 ± 117 vehicle-kilometers per seed**

on I-405.

**I-205.** The closure adds:

**+132 ± 56 vehicle-kilometers per seed**

on I-205.

Both changes are positive in **all 8 seeds**.

The difference is also very clear.

The **smallest** I-405 increase seen in any seed is:

**+1,010 vehicle-km**

The **largest** I-205 increase seen in any seed is:

**+223 vehicle-km**

So I-405 has the larger trip-level diversion in **every single seed**.

The average affected trip also becomes:

**0.9 minutes longer**

when measured using free-flow travel time.

### Trips that could not be rerouted

The pre-registration expected zero trips to lose their route because the
southbound detour exists.

The actual result was:

**55 of 4,962 affected trips**

or:

**1.1%**

could not be routed after the closure.

All 55 have the same basic problem:

their origin or destination is effectively located on roadway that becomes
unreachable when the closure is applied.

Specifically:

* **47 trips** start or end on a node inside the closed span.
* **8 trips** end on the short southbound I-5 section immediately downstream
  from the closure.

Those 8 trips all end at the same node.

That downstream piece remains in the graph, but once the upstream freeway is
closed it has no incoming roadway connection before the next merge.

Because the pre-registration already said that impossible routes would be
**dropped and counted**, that original rule is followed.

Nothing was changed after discovering these 55 trips.

### A.3 Status of the more realistic demand version

The new non-work demand model has now been built and is currently turned
off.

It has **not yet been tested against held-out traffic counts**.

Because of that, it has **not earned a second pre-registered prediction
arm**.

If it passes that validation before September 11, it can still be added as a
separate dated appendix before the closure begins.

The original predictions above will not change.

### A.4 How the analysis is tied to the actual campaign

The trip-level analysis is performed by:

`src/rosequarter_d123.py`

The analysis does not simply assume that it recreated the same population as
the simulation campaign.

It checks that directly.

It runs against the campaign's own graph file:

**MD5:**
`6707ddf25d63f2b5b4d2948b37cdb783`

It also refuses to run unless the demand information it creates matches the
fingerprint recorded in the campaign log:

* **215,655 placeable origin-destination pairs**
* **531,245 commuters**
* **20,857 boundary entry nodes**

Reference campaign log:

`fwrq_126285_7.out`

The per-seed analysis files are:

`rqd123_s{seed}.json`

and:

`rqd123_affected_s{seed}.parquet`

Those files are stored with the campaign results rather than committed to the
repository.

---

## Plain-English bottom line

Before Portland actually closes southbound I-5 on September 11, the model
makes a very specific prediction:

**I-405 should absorb most of the freeway diversion.**

Among trips that normally use the closed part of I-5:

* I-405 use rises from **16.4% to 58.4%**
* **48.9%** of affected trips add I-405 mileage
* I-405 gains about **1,187 vehicle-km per seed**
* modeled I-405 route NOx rises **84.9%** (from a small 959-gram base)

The model predicts a much smaller shift toward I-205:

* I-205 use rises from **7.5% to 10.1%**
* only **5.8%** of affected trips add I-205 mileage
* I-205 gains about **132 vehicle-km per seed**
* modeled I-205 route NOx rises only **3.1%**, and that corridor-level result
  does not pass the frozen statistical test.

The important test comes after **September 11, 2026**:

**Does the real traffic recorded by PORTAL show the same pattern: a large
increase on I-405 and a much smaller increase on I-205?**

Because the model, measurements, stations, predictions, and pass/fail rules
were all written down beforehand, the answer can be evaluated without
changing the rules after seeing what actually happened.
