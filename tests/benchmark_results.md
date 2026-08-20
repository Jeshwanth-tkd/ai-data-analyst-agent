# Phase 9 Benchmark Results

Agent times from `python tests/benchmark_agent.py`. Manual time
personally measured with `manual_eda_timer.py`, following
`manual_eda_checklist.md`, on one dataset (see honest notes below).

| Dataset | Rows | Agent time (s) | Manual time (min) | Manual time (s) | Time saved |
|---|---|---|---|---|---|
| sample_sales.csv | 10 | 12.0 | — (not measured) | — | — |
| employee_hr.csv | 200 | 6.5 | 3.7 | 224 | 97.1% (Phase 9 loop only) |
| movie_ratings.csv | 200 | 6.2 | — (not measured) | — | — |

**Measured time saved (employee_hr.csv, single trial, Phase 9 agent loop only): 97.1%**

*(Time saved = (manual_seconds - agent_seconds) / manual_seconds × 100 = (224 - 6.5) / 224 × 100)*

**More conservative figure, recalculated in Phase 27 (see the section below
for methodology): 96.6%** — the Phase 9 agent time (6.5s) plus a freshly
re-measured 1.12s of deterministic-report overhead (Phases 12-26's data
quality, EDA, anomalies, stats, cleaning, and forecast reports, all now
part of every real run) on the same `employee_hr.csv` dataset:
(224 − 7.62) / 224 × 100 = **96.6%**. This is the more representative
number for "how long does the CURRENT full pipeline take end to end"
(still excluding the LLM step itself, which needs a real API key to
time honestly) — it moves only half a point from the original figure
because 224 seconds of manual time so heavily dominates the comparison
that even real added overhead barely shifts the percentage.

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
- **Accurate phrasing:** "In a timed personal test, an AI agent I built
  completed first-pass exploratory data analysis on a 200-row dataset in
  6.5 seconds versus 3.7 minutes doing the same analysis manually — a
  97% reduction in my own analysis time on that dataset (96.6% including
  the deterministic reports added in later phases)." This is accurate to
  what was actually measured; avoid phrasing that implies this was
  tested across many datasets/analysts, since it wasn't.

## Phase 27 addition: deterministic reports (Phases 12-26), timed separately

The table above measures the **original Phase 4 agent loop only** (ingest →
LLM writes code → execute → self-correct). Everything added in Phases
12-26 — data quality, automatic EDA, anomaly detection, statistical
testing, the cleaning agent, forecasting, and HTML report generation —
runs with **zero LLM/network calls**, so it's benchmarked separately here
via `python tests/benchmark_deterministic_reports.py`, on a different
dataset (`movie_ratings.csv`, 200 rows) than the table above, so this is a
genuinely separate measurement rather than a relabeled version of the same
number.

| Metric | Result |
|---|---|
| Total time (all 6 deterministic reports + HTML report generation) | **0.85s** |
| Data quality score | 100/100 |
| Automatic EDA charts generated | 6 |
| Anomaly detection | ran (Isolation Forest + z-score) |
| Statistical tests run | 0 |
| Cleaning suggestions generated | 5 |
| Forecast | not run (no date-like column in this dataset) |

**Honest notes on this measurement:**
- This is a single run on one machine (this project's cloud dev
  sandbox), not averaged across multiple runs — sub-second timings like
  this can vary run to run more, proportionally, than the 6.5s Phase 9
  number did.
- **Statistical tests ran 0 times on this dataset, and that's expected,
  not a bug:** `movie_ratings.csv`'s only categorical column (`genre`)
  has 7 distinct values, one more than Phase 21's 2-6-category cap (see
  that module's docstring for why the cap exists — a 30-category column
  tested against a numeric column produces a result nobody can act on).
  This is included rather than swapped for a more flattering dataset,
  because a benchmark that only ever shows the best case isn't an honest
  one.
- **Forecasting didn't run on this dataset** because it has no date-like
  column at all — expected, not a failure (see Phase 25's entry: most
  datasets in this project aren't time series).
- This number does NOT include the LLM code-generation/execution loop
  (Phase 3/4) or the planner (Phase 17) — both require a real
  `GROQ_API_KEY`, which isn't available in every environment this
  benchmark might be re-run in. It measures exactly the deterministic
  portion of `analyze_csv_file()` that runs with no network access at all.
- **A real bug this benchmark caught while being built:** the first
  version of this measurement showed 0 statistical tests running on a
  *different* sample dataset for the wrong reason — `statistical_tests`
  was reusing the same "exclude id-like columns" filter as the EDA
  summary and anomaly detection, which silently dropped a legitimate
  numeric column (a continuous metric that's >95% unique, exactly what
  the id-like heuristic flags — the same root cause as a Phase 25
  forecasting bug found earlier). Fixed at the call site in
  `app/output/insights.py` (`statistical_tests.py` itself needed no
  change) to only exclude genuinely constant columns from the numeric
  side, pinned with a regression test in `tests/test_insights.py`.
- **A separate, smaller recalculation** (not this table, the one in the
  "More conservative figure" note above): the same six deterministic
  reports were re-run specifically on `employee_hr.csv` — the exact
  dataset the original 97.1% figure used — to get a real, directly
  comparable "current full pipeline overhead" number (1.12s across 3
  warm runs) to add on top of the original 6.5s, producing the 96.6%
  conservative figure. `movie_ratings.csv` was used for the table above
  instead specifically so this document has two independent
  measurements on two different datasets, not the same one reused twice.
