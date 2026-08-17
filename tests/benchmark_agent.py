"""
Phase 9: times the agent's actual elapsed time on each test dataset.

This is one half of the honest time-saved comparison -- the half that's
just code. The other half (how long the SAME analysis takes a human by
hand) has to be measured by you, since faking that number would make
the whole comparison dishonest. See manual_eda_checklist.md and
manual_eda_timer.py for that side.

Run from the project root:
    python tests/benchmark_agent.py
"""

import os
import sys
import time

# Allows this script to import from app/ even though it lives in tests/,
# by adding the project root to Python's module search path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.output.insights import analyze_csv_file

DATASETS = [
    "data/samples/sample_sales.csv",
    "data/samples/employee_hr.csv",
    "data/samples/movie_ratings.csv",
]

print(f"{'Dataset':<24}{'Time (s)':<12}{'Success':<10}{'Insights':<10}{'Charts':<8}")
print("-" * 64)

for path in DATASETS:
    start = time.time()
    result = analyze_csv_file(path)
    elapsed = time.time() - start

    name = os.path.basename(path)
    success = "yes" if result["success"] else "no"
    n_insights = len(result["insights"])
    n_charts = len(result["charts"])
    print(f"{name:<24}{elapsed:<12.1f}{success:<10}{n_insights:<10}{n_charts:<8}")

print("\nRecord these times in tests/benchmark_results.md alongside your")
print("manually-timed results, once you've completed the manual checklist.")
