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
from app.eda.auto_charts import generate_auto_eda_charts
from app.eda.auto_eda import compute_auto_eda
from app.stats.statistical_tests import run_hypothesis_tests
from app.executor.code_executor import run_with_self_correction
from app.ingestion.csv_profiler import load_csv, profile_dataframe
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
        df = load_csv(csv_path)
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
    except Exception as e:
        return {
            "success": False,
            "insights": [],
            "charts": [],
            "error": f"Could not read the CSV file: {e}",
            "attempts": [],
            "data_quality": None,
            "plan": None,
            "auto_eda_charts": [],
            "anomalies": None,
            "statistical_tests": None,
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
