# Phase 9 Benchmark Results

Agent times from `python tests/benchmark_agent.py`. Manual time
personally measured with `manual_eda_timer.py`, following
`manual_eda_checklist.md`, on one dataset (see honest notes below).

| Dataset | Rows | Agent time (s) | Manual time (min) | Manual time (s) | Time saved |
|---|---|---|---|---|---|
| sample_sales.csv | 10 | 12.0 | — (not measured) | — | — |
| employee_hr.csv | 200 | 6.5 | 3.7 | 224 | **97.1%** |
| movie_ratings.csv | 200 | 6.2 | — (not measured) | — | — |

**Measured time saved (employee_hr.csv, single trial): 97.1%**

*(Time saved = (manual_seconds - agent_seconds) / manual_seconds × 100 = (224 - 6.5) / 224 × 100)*

## Honest notes / caveats

- This is a **single measured data point**, not an average across
  multiple datasets or multiple trials — manual EDA was only actually
  timed once, on `employee_hr.csv` (200 rows, 7 columns), following the
  fixed 8-step checklist so the comparison covers a comparable scope of
  analysis on both sides.
- This measures *my* personal speed at manual EDA on *this* dataset —
  not a claim about analysts in general, and not something that's been
  validated across dataset sizes, domains, or multiple runs.
- The agent produced considerably more individual insight lines (41)
  than the fixed manual checklist covered (which asked for one
  representative example of each category: one stat block, one
  group-by, one most-frequent-value, one chart) — the two aren't a
  perfectly like-for-like comparison in depth, only in the *categories*
  of analysis covered. Worth being upfront about in an interview if
  asked to unpack the number.
- Agent times for `sample_sales.csv` and `movie_ratings.csv` are
  recorded above for reference, but have no manual-time counterpart to
  compare against (manual EDA wasn't repeated for those datasets).
- **Honest resume-safe phrasing:** "In a timed personal test, an AI
  agent I built completed first-pass exploratory data analysis on a
  200-row dataset in 6.5 seconds versus 3.7 minutes doing the same
  analysis manually — a 97% reduction in my own analysis time on that
  dataset." This is accurate to what was actually measured; avoid
  phrasing that implies this was tested across many datasets/analysts,
  since it wasn't.
