"""
Phase 27 benchmark: times the deterministic (non-LLM) reports added in
Phases 12-26, run on a DIFFERENT dataset than the original Phase 9
agent-loop benchmark (data/samples/movie_ratings.csv, 200 rows, rather
than employee_hr.csv) so this is a genuinely separate measurement, not a
rehash of the same number under a new label. movie_ratings.csv was
specifically chosen over the smaller daily_sales_timeseries.csv sample
because it has multiple numeric columns and a real categorical column
(genre) -- enough for anomaly detection and statistical testing to
actually have something to run on, not just report "skipped."

This intentionally does NOT include the LLM code-generation/execution
loop (Phase 3/4) or the planner (Phase 17) -- both require a real
GROQ_API_KEY to run, which isn't available in every environment this
project gets evaluated in. What's timed here is exactly the part of
analyze_csv_file() that runs with zero network calls: ingestion,
data quality, automatic EDA (summary + charts), anomaly detection,
statistical tests, the cleaning agent, forecasting, and the final HTML
report generation -- everything added since the original Phase 9
benchmark that doesn't depend on an LLM being reachable.

Run from the project root:
    python tests/benchmark_deterministic_reports.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.anomalies.anomaly_detection import detect_anomalies
from app.cleaning.data_cleaning import apply_cleaning_actions, suggest_cleaning_actions
from app.eda.auto_charts import generate_auto_eda_charts
from app.eda.auto_eda import compute_auto_eda
from app.forecasting.forecasting import forecast_time_series
from app.ingestion.csv_profiler import load_data_file, profile_dataframe
from app.quality.data_quality import assess_data_quality
from app.report.report_generator import save_html_report
from app.stats.statistical_tests import run_hypothesis_tests

DATASET = "data/samples/movie_ratings.csv"

start = time.time()

df = load_data_file(DATASET)
profile = profile_dataframe(df)
quality_report = assess_data_quality(df)
junk_columns = set(quality_report["structural_flags"]["constant_columns"]) | set(
    quality_report["structural_flags"]["id_like_columns"]
)
eda_summary = compute_auto_eda(df, exclude_columns=junk_columns)
auto_eda_charts = generate_auto_eda_charts(df)
anomalies = detect_anomalies(df, exclude_columns=junk_columns)
# Phase 27 fix: statistical_tests only excludes constant columns, not
# id-like ones -- see app/output/insights.py's matching comment for why.
stats_exclude_columns = set(quality_report["structural_flags"]["constant_columns"])
statistical_tests = run_hypothesis_tests(df, exclude_columns=stats_exclude_columns)
cleaning_suggestions = suggest_cleaning_actions(df, quality_report)
cleaning_apply_result = apply_cleaning_actions(df, cleaning_suggestions)
forecast = forecast_time_series(df, exclude_columns=set(quality_report["structural_flags"]["constant_columns"]))

# Build the same "partial result" shape save_html_report() expects, so
# the report-generation step timed here matches what analyze_csv_file()
# actually produces (minus the LLM-dependent success/insights/charts,
# which are reported as "not run" rather than faked).
partial_result = {
    "success": False,
    "insights": [],
    "charts": [],
    "error": "LLM step skipped in this deterministic-only benchmark.",
    "attempts": [],
    "data_quality": quality_report,
    "plan": None,
    "auto_eda_charts": auto_eda_charts,
    "anomalies": anomalies,
    "statistical_tests": statistical_tests,
    "cleaning": {
        "suggestions": cleaning_suggestions,
        "log": cleaning_apply_result["log"],
        "cleaned_csv_path": None,
    },
    "forecast": forecast,
}
report_path = save_html_report(partial_result, dataset_name=os.path.basename(DATASET))

elapsed = time.time() - start

print(f"Dataset: {DATASET} ({df.shape[0]} rows, {df.shape[1]} columns)")
print(f"Deterministic reports total time: {elapsed:.2f}s")
print()
print(f"  Data quality score:      {quality_report['overall_score']}/100")
print(f"  Automatic EDA charts:    {len(auto_eda_charts)}")
print(f"  Anomaly detection ran:   {anomalies['isolation_forest'].get('ran')}")
print(f"  Statistical tests run:   {statistical_tests['total_tests_run']}")
print(f"  Cleaning suggestions:    {len(cleaning_suggestions)}")
print(f"  Forecast ran:            {forecast.get('ran')}")
print(f"  HTML report saved to:    {report_path}")
