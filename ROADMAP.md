# Roadmap

This is the schedule the project is measured against. `/start-session` reads it
to answer one question out loud: are we on pace, or have we slipped?

It is a **draft plan**, not a contract. Confirm the milestone order with Christof.
Update it when reality changes, but when you move a milestone, write down *why* in
`PROGRESS.md`. A schedule you quietly rewrite to match what happened is not a
schedule. A schedule you change on purpose, with a reason, is good project
management.

The milestones come straight from the build order Christof gave (see
`REU_reference.md` section 1): get cars moving on the network, add car-following
interaction, add lights/queueing and congestion, then the NO2 path, the noise
path, and the writeup.

## Calendar

Program is 10 weeks. Weeks 1-2 were training (done). **8 project weeks remain.**
Week 3 starts **Monday June 22, 2026**. Symposium talk is **Friday August 14,
2026** (fixed). Week 10 is presentation week.

| Week | Dates           | Milestone                                                        | Hard deadline this week        | Status   |
|------|-----------------|-----------------------------------------------------------------|--------------------------------|----------|
| 1-2  | thru Jun 19     | Training + setup: repo, environment, network download + cache,  | Jun 19 Juneteenth (holiday)    | done     |
|      |                 | and the IDM car-following decision rule (built + sanity-checked) |                                |          |
| 3    | Jun 22 - Jun 26 | Vehicles move on the real network with routes (car-following on) | **Jun 23: present a key paper**| current  |
| 4    | Jun 29 - Jul 3  | Traffic lights + queueing; congestion emerges (the ABM's whole  | Jul 3 Independence Day (hol.)  | planned  |
|      |                 | point). Runtime benchmark: decide full-city vs Powell Plan B     |                                |          |
| 5    | Jul 6  - Jul 10 | Per-vehicle NO2 (HBEFA factors) -> segment NO2 surface           | **Jul 9: progress update 1**   | planned  |
| 6    | Jul 13 - Jul 17 | Predictors + random forest (tune with Optuna); reproduce Rao     | Jul 15: GPU/HPC session        | planned  |
|      |                 | baseline; run the NO2 model-to-model comparison                  |                                |          |
| 7    | Jul 20 - Jul 24 | **DEFCON week (partially away) — keep light.** Buffer + catch-up;| **Jul 24: progress update 2**  | planned  |
|      |                 | set calibration gates with Christof; write up NO2 results        | (conflicts with trip — plan!)  |          |
| 8    | Jul 27 - Jul 31 | Noise path: CNOSSOS -> noise surface, compare to FHWA TNM        | -                              | planned  |
| 9    | Aug 3  - Aug 7  | Figures, results, draft the proceedings chapter                  | -                              | planned  |
| 10   | Aug 10 - Aug 14 | Finalize chapter; build and rehearse the symposium talk          | **Aug 14: symposium talk**     | planned  |

## The DEFCON rule (week 7)

You are away part of week 7. So the target is: **finish the NO2 comparison
(week 6 milestone) before week 7 starts.** That makes week 7 a genuine buffer,
not a scramble. If by the end of week 6 the NO2 path is not done, that is the
signal to pull Plan B (Powell corridor only) so you do not enter your trip
behind. Front-load weeks 3 to 6.

## Week 3-4 additions from the Jun 22 check-in

From Christof's Jun 22 cohort check-in. These apply to this project. (The separate
synthetic-data-module advice in that same meeting was directed at Fatima, not here,
so it is intentionally not on this list.)

- **Parameterize the prototype.** Network size and vehicle count are config
  variables, not hard-coded, so the model scales up without a rewrite. Christof
  marked this "valid for both of you."
- **Early computational-complexity read, this week.** Time small runs and watch how
  runtime grows with vehicle count and network size. This front-loads part of the
  Week 4 runtime benchmark so we learn early whether the approach is viable. Keep
  scenarios small enough to run in seconds.
- **Dataset hunt, ~30% of time.** Alongside coding, locate the critical public
  datasets the project will need: traffic counts/AADT, emission factors, land cover,
  signal locations. Research started Jun 22; findings collected in `DATASETS.md`.
- **Framework decision (resolved).** Hand-roll the prototype on NetworkX now; switch
  to RePast / Mesa / NetLogo later only if a real need appears. Christof endorsed
  this directly.

## Program obligations (don't forget these)

These are program duties on top of the build work. Source: the daily check-in
reminder deck (in `reference/`). They are easy to forget and they shape how much
build time each week really has.

**Your presentations (hard deadlines):**
- **Jun 23** — present a key paper (10-15 min, teach the cohort something). Pick a
  paper in your area: a strong candidate is the Rao et al. paper you are using as
  the baseline, or a traffic-ABM / car-following paper.
- **Jul 9** — progress update 1 (10-15 min: what you did, challenges, open
  questions; include visualizations).
- **Jul 24** — progress update 2. **This is during your DEFCON trip.** Either get
  ahead and pre-build the talk, or ask Christof early to swap your slot.

**Summer Proceedings chapter (mandatory NSF REU deliverable):**
- **Sun Jul 12** — sign up: add your name and a tentative title to the signup sheet.
  (Done early; tentative title can change anytime.)
- Three chapter-writing lectures, Wednesdays 12-1pm (the research/career slots),
  Zoom https://pdx.zoom.us/j/87039235793:
  - **Jul 1** — finding sources, literature review, annotated bibliography, background
  - **Jul 8** — writing a title, abstract, and introduction
  - **Jul 22** — methodology, results, discussion, and conclusion
- Editors-in-chief: Fatima Asghar and Muhammad Cheema. Draft target is week 9
  (Aug 3-7); finalize week 10. The chapter is sole-author.

**Recurring meetings:**
- Daily check-in, 1:30-2:00pm PT (Christof or Nik).
- Nik's office hours, Mondays 11am-12pm.
- Research/career meeting, Wednesdays 12-1pm. Topics: Jul 1 literature review +
  annotated bibliography; Jul 8 writing title/abstract/intro; **Jul 15 GPU/HPC
  session** (bring your runtime-benchmark questions); Jul 22 writing
  methodology/results/discussion/conclusion; Jul 29 NSF GRFP career meeting.
  (Jul 1, Jul 8, and Jul 22 are the Summer Proceedings chapter-writing lectures
  above, not optional.)

**Daily:** end-of-day REUnite report (what you did, what's next). `/close-session`
produces the raw material for this.

**After every mentor meeting:** send a summary email (what we discussed, what we
decided, what I'll do next).

## How to read "on pace"

- If today's work matches the **current** week's milestone, you are on pace.
- If you are still finishing a past week's milestone, you have slipped. That is
  normal; the point is to *see* it early, tell Christof, and decide what to cut or
  defer rather than discovering it in August.
- Plan B (Powell corridor instead of full city) is the main pressure-release
  valve. The Week 4 runtime benchmark is when you decide whether to pull it.

## What "presenting honestly" means here, concretely

The research is already framed honestly: it is a model-to-model comparison, not
validation against sensor measurements, and the research question is falsifiable
(the agent-fed forest may not beat Rao's, and that is still a valid result). See
`REU_reference.md` section 1.

The day-to-day habit that backs this up: every session, `PROGRESS.md` records what
you did, every real decision, and why, including dead ends. Christof explicitly
wants the struggles and setbacks in your progress updates, not a polished
positive story. That honest record is what makes the chapter and the talk
trustworthy. You never claim the model is "right"; you show what you built, what
you compared, and what the comparison said.
