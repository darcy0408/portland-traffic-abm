# Logger null floor, measured Sept 4 2026 (Appendix Q addendum 2)

Read-only run of the registered instrument on the public travel-time
logger, the first time it touched real logger data (Appendix Q, M.3 rule 5).

- Command: `python src/rosequarter_logger_floor.py --floor --log-dir C:\dev\portland-traveltime-log`
- Instrument: main fe2c893 (see scorer_commit.txt; working copy identical
  to HEAD at run time), `--selftest` PASS immediately before (selftest.log).
- Data: clone of github.com/darcy0408/portland-traveltime-log at commit
  601b319, 2026-09-04 17:33 UTC; CSV md5s in logger_repo_commit.txt.
- floor_run.log is the instrument's verbatim output.

Reading the log against the registered rules (Appendix Q addendum, Aug 28,
decision tree case 1): the governing floor is the SINGLE draw
2026-08-18..20 vs 2026-09-01..03 (week-1 pool = Aug 19-20 after Aug 18
drops at 10 of 14), T = 6.86% (mlk_sb). The two draws involving
2026-08-25..27 (Aug 25 the only usable day) and the summary "FLOOR 14.43%"
line are DIAGNOSTIC under the registered rule and never govern wording.

Amended by Appendix Q addendum 3 (same day): Aug 19's 06:00 hour is
duplicated in the CSV (two ticks, pre-hardening), disclosed with a
keep-first sensitivity, and the computational thresholds are the exact
values (--floor-pct 6.864666476624853); the T = 6.86% above is display.
