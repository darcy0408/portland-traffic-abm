---
description: Wrap up a work session — log progress, commit, and push so the next session remembers everything.
---

You are closing out a work session on the Portland Traffic ABM research project.
Darcy is a student new to research, so explain what you're doing in plain language.

Do these steps in order:

1. Get today's date by running `date +%Y-%m-%d` (Bash) so the log entry is accurate.
2. Review what changed this session: run `git status --short` and `git diff --stat`,
   and recall what was discussed and decided.
3. Add a new entry to the TOP of the dated section in `PROGRESS.md` (newest first),
   using this shape:

   ```
   ## <YYYY-MM-DD> — <short title>

   **Did:**
   - <plain-language bullets of what we accomplished>

   **Decisions:**
   - <any choices made and why> (omit the section if none)

   **Next step:**
   - <the single most important thing to do next session>
   ```

4. If anything in the project changed meaningfully (current status, next build step,
   a decision that changes direction), update the relevant part of `CLAUDE.md` too —
   especially the "Where we are now" section.
5. Stage everything with `git add -A`, then show Darcy a one-paragraph summary of what
   the session accomplished and what the next step is.
6. Commit with a clear message describing the session's work, and push to `origin main`.
7. Confirm the push succeeded and remind Darcy they can pick up next time with
   `/start-session`.

Keep it brief and encouraging. The goal is that a future session can read `PROGRESS.md`
and `CLAUDE.md` and know exactly what's going on.
