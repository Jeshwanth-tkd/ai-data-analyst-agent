"""
Phase 26: tests for app/report/report_generator.py.

Confirms the HTML report is genuinely self-contained (no external
http(s) references, chart images embedded as base64 data URIs, not
linked files), that every section only appears when its data is
actually present, that the failure path renders cleanly instead of
crashing, and that save_html_report() writes a real file to disk.
"""

import os

from app.report.report_generator import generate_html_report, save_html_report

MINIMAL_SUCCESS_RESULT = {
    "success": True,
    "insights": ["Revenue grew steadily.", "No major outliers found."],
    "charts": [],
    "error": None,
    "attempts": [],
    "data_quality": {
        "overall_score": 92,
        "scores": {"missing_values": 90, "duplicates": 100, "type_consistency": 95, "outliers": 83},
        "details": {},
        "structural_flags": {
            "constant_columns": [],
            "id_like_columns": ["order_id"],
            "high_cardinality_columns": [],
            "inconsistent_categories": {},
        },
    },
    "plan": {"goal": "Understand sales trends.", "steps": ["Check revenue by month", "Look for outliers"]},
    "auto_eda_charts": [],
    "anomalies": {
        "isolation_forest": {"ran": True, "anomalous_row_count": 3, "rows_checked": 100, "anomalous_row_pct": 3.0},
        "z_score_outliers": {"price": {"outlier_count": 2, "outlier_pct": 2.0}},
    },
    "statistical_tests": {
        "total_tests_run": 4,
        "significant_results_count": 1,
        "top_significant_results": [
            {"categorical_column": "region", "numeric_column": "price", "test": "ANOVA", "p_value": 0.01, "group_means": {}}
        ],
        "multiple_comparisons_note": "No correction applied for multiple comparisons.",
    },
    "cleaning": {
        "suggestions": [
            {"type": "fill_missing_numeric", "column": "price", "description": "Fill 2 missing value(s) in 'price' with the median.", "auto_applied": True},
        ],
        "log": ["Filled 2 missing value(s) in 'price' with the median (10.5)."],
        "cleaned_csv_path": None,
    },
    "forecast": {"ran": False, "reason": "Could not find both a date-like column and a numeric column to forecast."},
}

FAILURE_RESULT = {
    "success": False,
    "insights": [],
    "charts": [],
    "error": "Could not read the data file: bad file",
    "attempts": [],
    "data_quality": None,
    "plan": None,
    "auto_eda_charts": [],
    "anomalies": None,
    "statistical_tests": None,
    "cleaning": None,
    "forecast": None,
}


def test_report_contains_no_external_references():
    html_str = generate_html_report(MINIMAL_SUCCESS_RESULT, dataset_name="sales.csv")
    assert "http://" not in html_str
    assert "https://" not in html_str


def test_report_includes_insights_and_plan():
    html_str = generate_html_report(MINIMAL_SUCCESS_RESULT, dataset_name="sales.csv")
    assert "Revenue grew steadily." in html_str
    assert "Understand sales trends." in html_str
    assert "Check revenue by month" in html_str


def test_report_includes_data_health_and_cleaning_and_stats():
    html_str = generate_html_report(MINIMAL_SUCCESS_RESULT, dataset_name="sales.csv")
    assert "Data Health" in html_str
    assert "92/100" in html_str
    assert "Cleaning Suggestions" in html_str
    assert "Statistical Tests" in html_str
    assert "ANOVA" in html_str


def test_report_skips_forecast_section_when_not_ran():
    html_str = generate_html_report(MINIMAL_SUCCESS_RESULT, dataset_name="sales.csv")
    # forecast["ran"] is False in the fixture -- no Forecast section, and
    # definitely not the internal failure "reason" text leaking into the
    # user-facing report.
    assert "<h2>Forecast</h2>" not in html_str
    assert "Could not find both a date-like column" not in html_str


def test_report_handles_failed_analysis_without_crashing():
    html_str = generate_html_report(FAILURE_RESULT, dataset_name="broken.csv")
    assert "Analysis failed" in html_str
    assert "bad file" in html_str
    assert "<h1>" in html_str  # still a complete, valid document


def test_report_escapes_html_in_insight_text():
    malicious_result = dict(MINIMAL_SUCCESS_RESULT)
    malicious_result["insights"] = ["<script>alert(1)</script>"]
    html_str = generate_html_report(malicious_result, dataset_name="sales.csv")
    assert "<script>alert(1)</script>" not in html_str
    assert "&lt;script&gt;" in html_str


def test_save_html_report_writes_a_real_file(tmp_path):
    output_path = str(tmp_path / "report.html")
    written_path = save_html_report(MINIMAL_SUCCESS_RESULT, dataset_name="sales.csv", output_path=output_path)

    assert written_path == output_path
    assert os.path.exists(output_path)
    with open(output_path, encoding="utf-8") as f:
        content = f.read()
    assert "<h1>Data Analysis Report: sales.csv</h1>" in content


def test_report_embeds_chart_as_base64_data_uri(tmp_path):
    # Build a tiny real PNG so _embed_image() has something genuine to encode.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    chart_path = str(tmp_path / "chart_test.png")
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9])
    fig.savefig(chart_path)
    plt.close(fig)

    result_with_chart = dict(MINIMAL_SUCCESS_RESULT)
    result_with_chart["charts"] = [chart_path]

    html_str = generate_html_report(result_with_chart, dataset_name="sales.csv")
    assert "data:image/png;base64," in html_str
    assert chart_path not in html_str  # the raw file path must never leak into the report
