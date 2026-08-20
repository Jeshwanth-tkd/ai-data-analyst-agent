"""
Phase 15: pytest suite. Extended in Phase 17/18 for the new plan /
auto_eda_charts result keys.

Tests for the top-level entry point, app/output/insights.py:
analyze_csv_file(). Groq is mocked -- no real network calls (both the
main code-writing client in app.agent.llm_client and the separate
planning client in app.agent.planner).
"""

import json
from unittest.mock import MagicMock, patch

from app.output.insights import analyze_csv_file

SAMPLE_CSV = "data/samples/sample_sales.csv"
TIMESERIES_CSV = "data/samples/daily_sales_timeseries.csv"

EXPECTED_KEYS = {
    "success", "insights", "charts", "error", "attempts",
    "data_quality", "plan", "auto_eda_charts", "anomalies", "statistical_tests",
    "cleaning", "forecast", "report_path",
}


def _mock_plan_response():
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps({
        "goal": "Understand pricing and category patterns.",
        "steps": ["Summarize price by category", "Check for outliers"],
    })
    return mock_resp


def test_analyze_csv_file_success_path_has_expected_shape():
    code = "```python\nprint('INSIGHT: pytest coverage check')\n```"

    with patch("app.agent.llm_client.Groq") as mock_llm_groq, \
         patch("app.agent.planner.Groq") as mock_planner_groq:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = code
        mock_llm_groq.return_value.chat.completions.create.return_value = mock_resp
        mock_planner_groq.return_value.chat.completions.create.return_value = _mock_plan_response()

        result = analyze_csv_file(SAMPLE_CSV)

    assert result["success"] is True
    assert set(result.keys()) == EXPECTED_KEYS
    assert result["data_quality"]["overall_score"] > 0
    assert "pytest coverage check" in result["insights"][0]
    assert result["plan"]["goal"] == "Understand pricing and category patterns."
    assert isinstance(result["auto_eda_charts"], list)
    assert len(result["auto_eda_charts"]) > 0  # sample_sales.csv has numeric + missing data
    assert result["cleaning"] is not None
    assert isinstance(result["cleaning"]["suggestions"], list)
    assert isinstance(result["cleaning"]["log"], list)
    assert result["forecast"] is not None
    assert "ran" in result["forecast"]
    assert result["report_path"] is not None
    import os
    assert os.path.exists(result["report_path"])


def test_statistical_tests_are_not_blocked_by_id_like_numeric_column():
    # Phase 27 regression test: daily_sales_timeseries.csv's only
    # numeric column ("daily_sales") is flagged id-like by Phase 12's
    # quality report (continuous values are routinely >95% unique) --
    # before the Phase 27 fix, statistical_tests reused the full
    # constant+id-like exclusion and silently ran ZERO tests on this
    # dataset even though a real (region, daily_sales) pair exists to
    # test. This pins the fix: at least one test must actually run.
    code = "```python\nprint('INSIGHT: pytest coverage check')\n```"

    with patch("app.agent.llm_client.Groq") as mock_llm_groq, \
         patch("app.agent.planner.Groq") as mock_planner_groq:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = code
        mock_llm_groq.return_value.chat.completions.create.return_value = mock_resp
        mock_planner_groq.return_value.chat.completions.create.return_value = _mock_plan_response()

        result = analyze_csv_file(TIMESERIES_CSV)

    assert result["statistical_tests"]["total_tests_run"] > 0


def test_analyze_csv_file_missing_file_returns_clean_error():
    result = analyze_csv_file("data/samples/this_file_does_not_exist.csv")

    assert result["success"] is False
    assert result["data_quality"] is None
    assert result["plan"] is None
    assert result["auto_eda_charts"] == []
    assert result["anomalies"] is None
    assert result["statistical_tests"] is None
    assert result["cleaning"] is None
    assert result["forecast"] is None
    assert result["report_path"] is None
    assert "Could not read the data file" in result["error"]
    assert result["insights"] == []
    assert result["charts"] == []


def test_planner_failure_does_not_break_the_whole_pipeline():
    # The planner's Groq client isn't mocked at all here -- it has no
    # API key in this environment, so generate_analysis_plan() will hit
    # a real (failing) network/auth path internally. The pipeline must
    # still complete successfully with plan=None, not crash.
    code = "```python\nprint('INSIGHT: still works without a plan')\n```"

    with patch("app.agent.llm_client.Groq") as mock_llm_groq:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = code
        mock_llm_groq.return_value.chat.completions.create.return_value = mock_resp

        result = analyze_csv_file(SAMPLE_CSV)

    assert result["success"] is True
    assert result["plan"] is None
