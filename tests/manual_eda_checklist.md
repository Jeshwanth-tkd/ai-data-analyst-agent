# Manual EDA Checklist (Phase 9 benchmark)

This checklist exists so the manual-vs-agent comparison is fair: it
covers the same kinds of insight the agent typically produces, nothing
more and nothing less. Do it in a fresh Jupyter notebook or plain
Python script — whatever you'd normally reach for.

**Important for honesty:** do each dataset from scratch. Don't reuse or
copy-paste code between datasets — part of what we're measuring is how
long it takes on data you haven't seen before, which is the real-world
scenario the agent is competing against.

## Steps (repeat for each dataset)

1. Start the timer: `python tests/manual_eda_timer.py start`
2. Load the CSV with pandas.
3. Print its shape (rows, columns).
4. Print each column's dtype and null count.
5. Compute basic descriptive stats (mean, median) for the numeric columns.
6. Compute one meaningful group-by aggregate (e.g. a sum or average
   broken down by a categorical column).
7. Find the most frequent value in at least one categorical column.
8. Create and save at least one chart summarizing a real finding.
9. The moment you finish step 8: stop the timer:
   `python tests/manual_eda_timer.py stop`

## Datasets to run this against

- `data/samples/sample_sales.csv`
- `data/samples/employee_hr.csv`
- `data/samples/movie_ratings.csv`

## After each dataset

Write down the printed time in `tests/benchmark_results.md` before
moving to the next dataset (the timer file gets overwritten each time
you run `start`).
