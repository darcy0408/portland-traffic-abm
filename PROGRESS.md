# Progress log

Newest entries on top. `/close-session` adds an entry here at the end of each work
session; `/start-session` reads it to remember where we left off. Each entry records
what we did, any decisions made, and the single most important next step.

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
