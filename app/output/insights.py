"""
Phase 5: Insight & chart generation.

This module doesn't talk to the LLM or run any code itself — it takes
the raw result of Phase 4's execution loop and structures it into
something a future API/frontend can actually use: a clean list of
insight strings, and a list of chart image files that were produced.
"""

import glob
import os

from app.executor.code_executor import run_with_self_correction

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


def analyze_and_structure(profile: dict, csv_path: str) -> dict:
    """
    The full Phase 2-5 pipeline in one call: run the self-correcting
    agent loop (Phase 4), then structure whatever it produced into
    clean insights + chart paths.
    """
    clear_outputs_dir()

    execution_result = run_with_self_correction(profile, csv_path)

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


# Demo block: runs the full Phase 2 -> 3 -> 4 -> 5 pipeline end to end.
if __name__ == "__main__":
    from app.ingestion.csv_profiler import profile_csv

    sample_path = os.path.join("data", "samples", "sample_sales.csv")
    profile = profile_csv(sample_path)

    print("Running the full agent pipeline on sample_sales.csv...\n")
    result = analyze_and_structure(profile, sample_path)

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
        print("Agent failed after all retries.")
        print("Last error:", result["error"])
