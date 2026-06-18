# Progress log

Newest entries on top. `/close-session` adds an entry here at the end of each work
session; `/start-session` reads it to remember where we left off. Each entry records
what we did, any decisions made, and the single most important next step.

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
