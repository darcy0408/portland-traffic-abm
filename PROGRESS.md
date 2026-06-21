# Progress log

Newest entries on top. `/close-session` adds an entry here at the end of each work
session; `/start-session` reads it to remember where we left off. Each entry records
what we did, any decisions made, and the single most important next step.

---

## 2026-06-20 — Car-following kernel, project planning, and Rao talk prep

**Did:**
- Built the IDM (Intelligent Driver Model) car-following function in
  `src/generate.py` and sanity-checked it: a lone car accelerates to the speed
  limit and flattens; a car approaching a stopped car brakes smoothly to a clean
  stop at the minimum gap. Put the IDM parameters in `config.py`.
- Added a sim-free network map (`python src/visualize.py network`) and confirmed
  the study area by eye (Ladd's Addition starburst is the giveaway landmark).
- Created `ROADMAP.md`: a real week-by-week schedule (weeks 3-10, Jun 22 to the
  Aug 14 symposium) with hard deadlines and recurring program obligations.
- Upgraded `/start-session` to run a drift + schedule + loose-ends health check
  each session, measured against the spec and the (gitignored) class reference.
- Saved class reference material privately (REU_reference.md and two lecture PDFs
  in reference/, both gitignored). Added `REFERENCES.md` (public bibliography) for
  the four papers Christof sent.
- Replied to Christof's email (sound-wall fact sheet, references, Powell data).
- Did a full first pass on the Rao baseline paper and wrote a complete 12-slide
  talk with speaker notes for the Jun 23 key-paper presentation (saved in
  Downloads, outside the repo).

**Decisions:**
- Use IDM for car-following (not a cell-based model) because per-vehicle NO2
  emissions depend on acceleration, which IDM gives at every step.
- Open question to raise with Christof: build the ABM directly on NetworkX (as we
  are) vs the Mesa framework the training suggested. Hand-rolled is defensible
  since we need continuous acceleration and are not doing reservoir computing.

**Next step:**
- Finish prepping the Jun 23 Rao paper talk (build the actual slides from the
  speaker notes), since that deadline is fixed and closest. Then start the week-3
  build: vehicles moving on the real network with routes, driven by the IDM
  kernel.

---

## 2026-06-17 — Environment + network download working

**Did:**
- Installed the Python stack: added osmnx and pyarrow (networkx, numpy, pandas, matplotlib were already present).
- Replaced the canonical `CLAUDE.md` with Darcy's authoritative spec; added private `CLAUDE.local.md` and gitignored it.
- Downloaded and cached the Powell street network: 978 intersections, 2,838 segments, ~4 seconds. Verified the disk cache reloads in 0.1 s.

**Decisions:**
- Define the study area by an explicit center point and radius, not a place-name string. The name "SE Powell Blvd" geocoded to a tiny wrong fragment and the download failed. Center is on Powell by Cleveland High School, radius 1.5 km. This is reproducible and tunable for the runtime benchmark.
- First runtime data point: 1.5 km radius is effectively instant, so the area has room to grow later.

**Next step:**
- Build car-following vehicle movement inside the marked stub in `src/generate.py` `run_simulation()`. Optional quick win first: draw a map of the downloaded network in `visualize.py` to confirm the study area by eye.

---

## 2026-06-17 — Project setup

**Did:**
- Cloned the repo and added the scaffold (config, requirements, `src/` modules, `.gitignore`).
- Added `CLAUDE.md` (project brief, auto-read each session) and this `PROGRESS.md`.
- Added `/start-session` and `/close-session` slash commands.
- Granted Claude read access to Downloads and Screenshots folders (on-demand only).

**Decisions:**
- Keep generation and visualization in separate scripts (re-plot without re-running the sim).
- Baselines fixed: Rao-style land-use random forest (NO2) and FHWA reference (noise).
- If full-city sim is too slow, fall back to the Powell Boulevard corridor (Plan B).

**Next step:**
- Build **car-following vehicle movement** (Week 2 milestone) inside the marked stub
  in `src/generate.py` `run_simulation()`. No simulation code exists yet.
