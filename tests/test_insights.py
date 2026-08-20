"""
Phase 15: pytest suite.

Tests for the top-level entry point, app/output/insights.py:
analyze_csv_file(). Groq is mocked -- no real network calls.
"""

from unittest.mock import MagicMock, patch

from app.output.insights import analyze_csv_file

SAMPLE_CSV = "data/samples/sample_sales.csv"


def test_analyze_csv_file_success_path_has_expected_shape():
    code = "```python\nprint('INSIGHT: pytest coverage check')\n```"

    with patch("app.agent.llm_client.Groq") as mock_groq_class:
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = code
        mock_groq_class.return_value.chat.completions.create.return_value = mock_resp

        result = analyze_csv_file(SAMPLE_CSV)

    assert result["success"] is True
    assert set(result.keys()) == {"success", "insights", "charts", "error", "attempts", "data_quality"}
    assert result["data_quality"]["overall_score"] > 0
    assert "pytest coverage check" in result["insights"][0]


def test_analyze_csv_file_missing_file_returns_clean_error():
    result = analyze_csv_file("data/samples/this_file_does_not_exist.csv")

    assert result["success"] is False
    assert result["data_quality"] is None
    assert "Could not read the CSV file" in result["error"]
    assert result["insights"] == []
    assert result["charts"] == []
