# CLAUDE.md — project brief for Claude Code

This file is read automatically at the start of every session. It exists so any
session (or a returning human) is instantly oriented. Keep it current.

## Who this is for

Darcy — an NSF REU student at Portland State (Teuscher Lab), new to research and
to large coding projects. Default to **plain-language explanations**: say what
each step does and why, not just that it's done. When a task says "STOP" or
"wait for confirmation," genuinely pause. Teach as you go — this is a learning
project as much as a research one.

## What the project is

An **agent-based model (ABM)** of vehicles driving on Portland's street network
(downloaded with OSMnx). Vehicles interact — car-following, queueing at signals,
congestion — and each one adds a noise and NO2 contribution to the street segment
it's on. The simulation produces **per-segment noise and NO2 surfaces** for the city.

**The research question:** do these *interacting agents* preserve sharp,
block-to-block (near-road) pollution gradients better than standard statistical
methods that predict pollution from static variables?

**What we compare against (baselines):**
- NO2: a **Rao-style land-use random forest**. We feed our agent-generated
  predictors into the *same* random-forest method — so any improvement isolates
  what the ABM adds, not a different algorithm.
- Noise: the **FHWA reference** model.

**Mechanistic models used inside the sim:** CNOSSOS (noise), HBEFA (NO2 emissions).

**Honest limitation:** this compares models to models (Rao's surface and FHWA are
themselves estimates; Portland lacks dense ground-truth sensors). It shows method
*agreement*, not absolute accuracy.

**Main risk:** city-scale simulation may be too slow for 8 weeks. **Plan B:** focus
on the Powell Boulevard corridor (also a real planning case — noise walls are being
added there).

## How the code is organized (and the one rule)

Generation and visualization are **separate stages**, on purpose:
- `src/generate.py` — STAGE 1. Runs the ABM, checkpoints, saves result tables. **No plotting.**
- `src/visualize.py` — STAGE 2. Reads saved tables, writes figures. **No simulation.**
- `src/checkpoint.py` — save/restore simulation state (mandatory on Colab, where disk wipes on disconnect).
- `config.py` — every parameter, path, and the random seed, in one place. Auto-detects Colab.

Why: the sim is expensive; figures get remade often (papers, the Aug 14 symposium).
Keeping them separate means you re-draw a map without re-running days of simulation.

Layout: `data/` (network/raw/processed) and `outputs/figures/` are created on first
run and are git-ignored.

## Where we are now

Scaffold committed and pushed. **No simulation code written yet.** The next build
step is **car-following vehicle movement** (Week 2 milestone), which goes inside the
marked stub in `src/generate.py` `run_simulation()` (the `YOUR ABM STEP GOES HERE`
block), feeding `segment_totals[edge] += contribution`.

See `PROGRESS.md` for the running session-by-session log.

## Timeline checkpoints (the "exams")

- **W2:** vehicles move correctly through the network (sensible classes, speeds, time-of-day patterns).
- **W4:** noise + NO2 surfaces generated; a random forest and a first comparison vs. Rao/FHWA (RMSE, MAE, correlation).
- **W7:** agent-fed vs. Rao-style forests evaluated at held-out locations, including near-road gradients.
- **Final (Aug 14, 2026):** pipeline, final maps, proceedings chapter, code+data archive, symposium presentation.

## Working agreements

- Put things on GitHub now, comment as you write (not in a cleanup pass that never comes).
- Same config + same seed must reproduce the same numbers.
- Commit at the end of a work session (`/close-session` does this); start with `/start-session`.
