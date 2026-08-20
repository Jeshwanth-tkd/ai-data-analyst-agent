"""
Phase 5: Insight & chart generation.
Phase 6 addition: analyze_csv_file(), a single hardened entry point that
wraps the *entire* pipeline (ingestion through output) so a bad file or
an unexpected failure anywhere never crashes with a raw traceback — it
always comes back as a clean result dict. This is also the exact
function Phase 7's API endpoint will call.
Phase 12 addition: analyze_csv_file()'s result dict gains one new key,
"data_quality" — a deterministic health report (Phase 12's
assess_data_quality()) computed alongside the profile. This is an
ADDITIVE change on purpose: every key that existed before (success,
insights, charts, error, attempts) is unchanged, so main.py's FastAPI
endpoint and streamlit_app.py both keep working exactly as before even
though neither has been told about the new key yet.

Phase 16 addition: a second deterministic report (Phase 16's
compute_auto_eda()) is computed from the same DataFrame, and BOTH
reports are now passed down into the agent loop (previously
quality_report was computed but never actually given to the LLM — only
shown to the user afterward). Columns already flagged constant/ID-like
by the quality report are excluded from the EDA summary's category
breakdown, since they're already known to be meaningless.

Phase 17 addition: before code is generated, a separate planning call
(app.agent.planner.generate_analysis_plan()) decides on a goal + a
handful of concrete steps, and that plan is threaded through to the code
generator alongside quality_report/eda_summary. The result dict gains a
"plan" key (a plain dict, or None if planning itself failed) so the UI
can show what the agent intended to do.

Phase 18 addition: a second, LLM-independent chart set
(app.eda.auto_charts.generate_auto_eda_charts()) is generated directly
from the DataFrame -- distribution histograms, a correlation heatmap,
and a missingness chart, always available regardless of whether the
LLM's own run succeeds. Attached as "auto_eda_charts" (a list of file
paths, possibly empty).

Phase 20/21 additions: two more deterministic reports computed
alongside quality_report/eda_summary -- Phase 20's detect_anomalies()
(z-score outliers + Isolation Forest row-level anomalies) attached as
"anomalies", and Phase 21's run_hypothesis_tests() (automatic t-test/
ANOVA between categorical and numeric columns) attached as
"statistical_tests". Neither is threaded into the LLM's prompt (unlike
quality_report/eda_summary/plan) -- kept UI-only for now to avoid
growing the prompt further without a demonstrated need for the LLM to
react to them yet.

Phase 24 addition: a fifth deterministic report -- Phase 24's
suggest_cleaning_actions()/apply_cleaning_actions() -- computed the same
way as the others. Attached as "cleaning": {"suggestions": [...],
"log": [...], "cleaned_csv_path": str|None}. Unlike the reports above,
this one also writes a file (the cleaned CSV, if any actions were
actually applied) into OUTPUTS_DIR, since a cleaned dataset is something
a user would want to download, not just read about.

Phase 25 addition: a sixth deterministic report -- Phase 25's
forecast_time_series() -- attempts to auto-detect a date-like column and
a numeric column and forecast the next several periods forward (Holt's
linear trend method, statsmodels). Attached as "forecast":
{"ran": bool, ...} -- "ran" is False (with a "reason") for any dataset
without a usable date+numeric pair or without enough historical points,
which is expected and NOT an error -- most datasets in this project
(e.g. sample_sales.csv) aren't time series at all.

Phase 26 addition: a final "report_path" key -- app.report.report_generator's
save_html_report() bundles the entire result dict (insights, every
chart, data quality, plan, EDA, anomalies, stats, cleaning, forecast)
into one self-contained downloadable HTML file, written to
outputs/report.html. Generated last, since it only reads what's already
been computed above; wrapped in its own try/except so a report-writing
failure can never take down an otherwise-successful analysis.

This module doesn't talk to the LLM or run any code itself (aside from
calling the planner) — it takes the raw result of Phase 4's execution
loop and structures it into something a future API/frontend can
actually use: a clean list of insight strings, and a list of chart
image files that were produced.
"""

import glob
import os

from app.agent.planner import generate_analysis_plan
from app.anomalies.anomaly_detection import detect_anomalies
from app.cleaning.data_cleaning import apply_cleaning_actions, suggest_cleaning_actions
from app.eda.auto_charts import generate_auto_eda_charts
from app.eda.auto_eda import compute_auto_eda
from app.forecasting.forecasting import forecast_time_series
from app.report.report_generator import save_html_report
from app.stats.statistical_tests import run_hypothesis_tests
from app.executor.code_executor import run_with_self_correction
from app.ingestion.csv_profiler import load_data_file, profile_dataframe
from app.quality.data_quality import assess_data_quality

OUTPUTS_DIR = "outputs"
INSIGHT_MARKER = "INSIGHT: "


def clear_outputs_dir(outputs_dir: str = OUTPUTS_DIR) -> None:
    """
    Delete any chart images left over from a previous run, so that after
    this run finishes, everything sitting in outputs/ genuinely belongs
    to *this* run. We only remove chart_*.png files — .gitkeep is left
    alone so the folder itself stays tracked by git.
    """
    for path in glob.glob(os.path.join(outputs_dir, "chart_*.png")):
        os.remove(path)


def parse_insights(stdout: str) -> list:
    """
    Pull out just the lines the LLM's code printed with the "INSIGHT: "
    marker, stripped of that marker. Any other printed text (debug
    prints, stray output) is simply ignored rather than causing errors.
    """
    insights = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith(INSIGHT_MARKER):
            insights.append(line[len(INSIGHT_MARKER):].strip())
    return insights


def list_chart_files(outputs_dir: str = OUTPUTS_DIR) -> list:
    """Return the paths of any chart images the code saved, in order."""
    paths = glob.glob(os.path.join(outputs_dir, "chart_*.png"))
    return sorted(paths)


def analyze_and_structure(
    profile: dict,
    csv_path: str,
    quality_report: dict = None,
    eda_summary: dict = None,
    plan=None,
) -> dict:
    """
    The full Phase 2-5 pipeline in one call: run the self-correcting
    agent loop (Phase 4), then structure whatever it produced into
    clean insights + chart paths. Phase 16: quality_report/eda_summary
    are optional and, when given, are threaded straight through to the
    agent loop so the LLM actually sees them. Phase 17 adds `plan`
    (an app.agent.planner.AnalysisPlan) the same way.
    """
    clear_outputs_dir()

    execution_result = run_with_self_correction(
        profile, csv_path, quality_report=quality_report, eda_summary=eda_summary, plan=plan
    )

    if not execution_result["success"]:
        return {
            "success": False,
            "insights": [],
            "charts": [],
            "error": execution_result["attempts"][-1]["stderr"],
            "attempts": execution_result["attempts"],
        }

    return {
        "success": True,
        "insights": parse_insights(execution_result["output"]),
        "charts": list_chart_files(),
        "error": None,
        "attempts": execution_result["attempts"],
    }


def analyze_csv_file(csv_path: str) -> dict:
    """
    Phase 6's hardened entry point. Runs the whole pipeline — profile,
    generate code, execute, self-correct, structure results — and
    GUARANTEES a clean result dict comes back no matter what goes wrong,
    at any stage. Nothing here should ever raise an exception outward.

    There are two layers of error handling on purpose:
    1. Specific, expected failures (bad file, empty file, oversized
       file) are already caught with clear messages inside load_csv().
    2. This function's `except Exception` is a broad, final backstop —
       it catches anything unexpected we didn't specifically plan for
       (a Groq API/network error, a rate limit, a bug we haven't found
       yet) so the caller (soon: a FastAPI endpoint) never has to deal
       with a raw crash, only ever this one consistent dict shape.

    Phase 12 note: the CSV is loaded into memory exactly ONCE here
    (`load_csv`), and that same in-memory DataFrame feeds both
    `profile_dataframe()` and `assess_data_quality()`. Before this
    change, `profile_csv()` re-read the file from disk on its own — for
    a single call that's harmless, but reading a file twice for two
    different reasons is the kind of small inefficiency worth removing
    once you notice it, and it also guarantees the profile and the
    quality report are describing the literal same snapshot of data.
    """
    try:
        # Phase 23: load_data_file() dispatches by extension (csv, xlsx,
        # xls, json, parquet) instead of assuming CSV -- the csv_path
        # parameter name is unchanged (see csv_profiler.py's Phase 23
        # docstring note on why), but it may now hold any supported format.
        df = load_data_file(csv_path)
        profile = profile_dataframe(df)
        quality_report = assess_data_quality(df)
        # Phase 16: don't waste EDA-summary space on columns already
        # known to be meaningless (constant / ID-like), per Phase 12's
        # own structural_flags for this exact dataset.
        junk_columns = set(quality_report["structural_flags"]["constant_columns"]) | set(
            quality_report["structural_flags"]["id_like_columns"]
        )
        eda_summary = compute_auto_eda(df, exclude_columns=junk_columns)
        # Phase 18: deterministic charts, independent of the LLM loop
        # below -- computed here so they exist even if the LLM run fails.
        auto_eda_charts = generate_auto_eda_charts(df)
        # Phase 20/21: two more deterministic reports, same junk_columns
        # exclusion as the EDA summary above.
        anomalies = detect_anomalies(df, exclude_columns=junk_columns)
        statistical_tests = run_hypothesis_tests(df, exclude_columns=junk_columns)
        # Phase 24: deterministic cleaning suggestions + a conservative
        # auto-applied subset (missing-value fills, duplicate removal,
        # category standardization -- never column drops, see that
        # module's docstring). The cleaned data is written out as its
        # own CSV (not embedded in this dict) so it can be offered as a
        # download, the same pattern as chart file paths below.
        cleaning_suggestions = suggest_cleaning_actions(df, quality_report)
        cleaning_apply_result = apply_cleaning_actions(df, cleaning_suggestions)
        cleaned_csv_path = None
        if cleaning_apply_result["log"]:
            os.makedirs(OUTPUTS_DIR, exist_ok=True)
            cleaned_csv_path = os.path.join(OUTPUTS_DIR, "cleaned_data.csv")
            cleaning_apply_result["cleaned_df"].to_csv(cleaned_csv_path, index=False)
        cleaning = {
            "suggestions": cleaning_suggestions,
            "log": cleaning_apply_result["log"],
            "cleaned_csv_path": cleaned_csv_path,
        }
        # Phase 25: forecast_time_series() never raises (see its own
        # docstring). Deliberately NOT reusing junk_columns here (unlike
        # eda_summary/anomalies/statistical_tests above) -- caught by
        # testing against a real time-series sample: Phase 12's
        # id-like-column heuristic (>95% unique values) is tuned for
        # "is this safe to group/aggregate by", and a genuine continuous
        # metric worth forecasting (revenue, temperature, price) is
        # ROUTINELY >95% unique too -- excluding it would silently
        # disable forecasting on exactly the columns most worth
        # forecasting. Only constant columns (zero variance -- nothing
        # to forecast, definitionally) are excluded from the numeric
        # candidate pool; date-column detection was already independent
        # of any exclusion (see forecasting.py's own docstring).
        forecast_exclude_columns = set(quality_report["structural_flags"]["constant_columns"])
        forecast = forecast_time_series(df, exclude_columns=forecast_exclude_columns)
    except Exception as e:
        return {
            "success": False,
            "insights": [],
            "charts": [],
            "error": f"Could not read the data file: {e}",
            "attempts": [],
            "data_quality": None,
            "plan": None,
            "auto_eda_charts": [],
            "anomalies": None,
            "statistical_tests": None,
            "cleaning": None,
            "forecast": None,
            "report_path": None,
        }

    # Phase 17: decide on a plan before writing any code. generate_analysis_plan()
    # already never raises (it falls back to a generic plan internally), but this
    # is wrapped anyway -- planning is a nice-to-have, not something that should
    # ever be allowed to take down the whole analysis if something unexpected happens.
    try:
        plan = generate_analysis_plan(profile, quality_report=quality_report, eda_summary=eda_summary)
    except Exception:
        plan = None

    try:
        result = analyze_and_structure(
            profile, csv_path, quality_report=quality_report, eda_summary=eda_summary, plan=plan
        )
    except Exception as e:
        result = {
            "success": False,
            "insights": [],
            "charts": [],
            "error": f"Unexpected error while analyzing the file: {e}",
            "attempts": [],
        }

    # Attach every deterministic report regardless of whether the
    # LLM/execution side succeeded or failed -- all of them are
    # independent of the agent loop's outcome, and are still genuinely
    # useful to show a user even on a failed run.
    result["data_quality"] = quality_report
    result["plan"] = plan.model_dump() if plan is not None else None
    result["auto_eda_charts"] = auto_eda_charts
    result["anomalies"] = anomalies
    result["statistical_tests"] = statistical_tests
    result["cleaning"] = cleaning
    result["forecast"] = forecast

    # Phase 26: bundle everything above into one self-contained HTML
    # report, generated LAST since it just reads what's already in
    # `result` -- wrapped defensively like the planner call above, since
    # a report-writing failure (e.g. a full disk) shouldn't be able to
    # take down an otherwise-successful analysis.
    try:
        result["report_path"] = save_html_report(result, dataset_name=os.path.basename(csv_path))
    except Exception:
        result["report_path"] = None

    return result


# Demo block: runs the full Phase 2 -> 3 -> 4 -> 5 -> 6 pipeline end to end.
# Accepts an optional CSV path as a command-line argument, so we can
# easily stress-test different messy files without editing this file:
#   python -m app.output.insights data/samples/messy_no_header.csv
if __name__ == "__main__":
    import sys

    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "samples", "sample_sales.csv")

    print(f"Running the full agent pipeline on {csv_path}...\n")
    result = analyze_csv_file(csv_path)

    if result.get("data_quality"):
        print(f"Data health score: {result['data_quality']['overall_score']}/100")
        print(f"  {result['data_quality']['scores']}\n")

    if result.get("plan"):
        print(f"Agent's plan -- goal: {result['plan']['goal']}")
        for i, step in enumerate(result["plan"]["steps"], start=1):
            print(f"  {i}. {step}")
        print()

    if result.get("auto_eda_charts"):
        print(f"Automatic EDA charts (no LLM): {len(result['auto_eda_charts'])}")
        for chart in result["auto_eda_charts"]:
            print(f"  - {chart}")
        print()

    anomalies = result.get("anomalies")
    if anomalies and anomalies["isolation_forest"].get("ran"):
        iso = anomalies["isolation_forest"]
        print(f"Anomalies: {iso['anomalous_row_count']}/{iso['rows_checked']} rows ({iso['anomalous_row_pct']}%)")

    stats_report = result.get("statistical_tests")
    if stats_report and stats_report["significant_results_count"]:
        print(f"Statistical tests: {stats_report['significant_results_count']} significant result(s) "
              f"out of {stats_report['total_tests_run']} tested")
        for r in stats_report["top_significant_results"]:
            print(f"  - {r['categorical_column']} vs {r['numeric_column']}: p={r['p_value']}")
        print()

    cleaning = result.get("cleaning")
    if cleaning and cleaning["suggestions"]:
        print(f"Cleaning suggestions: {len(cleaning['suggestions'])}")
        for a in cleaning["suggestions"]:
            marker = "auto-applied" if a["auto_applied"] else "manual review"
            print(f"  [{marker}] {a['description']}")
        if cleaning["cleaned_csv_path"]:
            print(f"Cleaned data saved to: {cleaning['cleaned_csv_path']}")
        print()

    forecast = result.get("forecast")
    if forecast and forecast.get("ran"):
        print(f"Forecast ({forecast['value_column']} over {forecast['date_column']}):")
        for point in forecast["forecast"]:
            print(f"  {point['date']}: predicted={point['predicted_value']}, naive_baseline={point['naive_baseline']}")
        print(f"Forecast chart saved to: {forecast['chart_path']}\n")

    if result.get("report_path"):
        print(f"Full HTML report saved to: {result['report_path']}")

    if result["success"]:
        print(f"Insights found: {len(result['insights'])}")
        for insight in result["insights"]:
            print(f"  - {insight}")

        print(f"\nCharts saved: {len(result['charts'])}")
        for chart in result["charts"]:
            print(f"  - {chart}")

        # Showing the code that actually ran makes it possible to debug
        # cases where charts/insights look wrong or empty — you can see
        # exactly what the LLM wrote, not just guess at it.
        print("\n----- Code that produced this result -----")
        print(result["attempts"][-1]["code"])
        print("--------------------------------------------")
    else:
        print("Analysis failed.")
        print("Reason:", result["error"])
