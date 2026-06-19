---
description: Orient at the start of a work session — read the brief, the log, and git state, then propose today's focus.
---

You are starting a new work session on the Portland Traffic ABM research project.
Darcy is a student new to research, so explain things in plain language.

Do these steps, then stop and wait:

1. Read `CLAUDE.md` (project brief), `ROADMAP.md` (the schedule), and
   `PROGRESS.md` (session log) to recall the project and where we left off.
   Also skim `REU_reference.md` (distilled notes from Christof's meetings and the
   training lectures) so the drift check below measures against his actual
   directives, not just the project brief. `CLAUDE.md` stays the canonical spec; if
   the reference and `CLAUDE.md` ever conflict, flag it rather than silently
   picking one.
2. Run `git log --oneline -5` and `git status --short` to see recent commits and any
   uncommitted work.
3. If a file path to a screenshot or download was shared, read it; otherwise skip.
4. Run the three-question health check and report each answer in one line:
   - **Drift:** does the recent work still match the spec in `CLAUDE.md`,
     including its "do not drift from this" and "out of scope" sections? Name any
     drift plainly (e.g. creeping toward routing, sensor validation, or pollen).
   - **Schedule:** which `ROADMAP.md` week are we in by date, and does the actual
     current work match that week's milestone? If we have slipped to a past
     milestone, say so and note Plan B if relevant. Also call out the next hard
     deadline from the roadmap (a presentation, holiday, or the symposium) if one
     falls within roughly the next week, so it is never a surprise.
   - **Loose ends:** is anything from the last `PROGRESS.md` "Next step" or any
     open decision still unresolved or forgotten?
   Keep this honest. The job of this check is to surface problems early, not to
   reassure. If everything is fine, say so briefly.
5. Give Darcy a short, friendly orientation:
   - One or two sentences on what this project is (in case it's been a while).
   - "Last session we…" — the most recent `PROGRESS.md` entry, summarized.
   - "The next step is…" — the next step from `PROGRESS.md`, tied to the current
     week's milestone in `ROADMAP.md`.
   - A suggested concrete focus for today, framed as a question.
6. Ask what Darcy wants to work on today. Do not start coding until they answer.

Keep it encouraging and brief. Teach as you go.
