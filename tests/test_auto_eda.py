"""
Phase 15 (suite) / Phase 16 (module under test): pytest tests for
app/eda/auto_eda.py -- pure pandas math, no LLM calls.
"""

import pandas as pd

from app.eda.auto_eda import compute_auto_eda


def test_numeric_summary_has_expected_stats():
    df = pd.DataFrame({"value": [10, 20, 30, 40, 50]})
    report = compute_auto_eda(df)

    stats = report["numeric_summary"]["value"]
    assert stats["mean"] == 30.0
    assert stats["min"] == 10.0
    assert stats["max"] == 50.0


def test_top_categories_reports_frequencies():
    df = pd.DataFrame({"dept": ["HR", "HR", "Sales", "Eng", "Eng", "Eng"]})
    report = compute_auto_eda(df)

    assert report["top_categories"]["dept"]["Eng"] == 3
    assert report["top_categories"]["dept"]["HR"] == 2


def test_excluded_columns_are_skipped_in_top_categories():
    df = pd.DataFrame({
        "order_id": [f"ORD-{i}" for i in range(10)],
        "dept": ["HR"] * 5 + ["Sales"] * 5,
    })
    report = compute_auto_eda(df, exclude_columns={"order_id"})

    assert "order_id" not in report["top_categories"]
    assert "dept" in report["top_categories"]


def test_high_cardinality_column_is_skipped_automatically():
    df = pd.DataFrame({"unique_notes": [f"note {i}" for i in range(30)]})
    report = compute_auto_eda(df)
    assert "unique_notes" not in report["top_categories"]


def test_top_correlations_finds_strong_relationship():
    df = pd.DataFrame({
        "a": [1, 2, 3, 4, 5],
        "b": [2, 4, 6, 8, 10],  # perfectly correlated with a
    })
    report = compute_auto_eda(df)

    assert len(report["top_correlations"]) == 1
    assert set(report["top_correlations"][0]["columns"]) == {"a", "b"}
    assert report["top_correlations"][0]["correlation"] == 1.0


def test_weak_correlation_is_not_reported():
    df = pd.DataFrame({
        "a": [1, 2, 3, 4, 5, 6],
        "b": [3, 1, 4, 1, 5, 2],  # near-zero linear relationship with a
    })
    report = compute_auto_eda(df)
    correlation = df["a"].corr(df["b"])
    assert abs(correlation) < 0.3  # sanity check the fixture itself is "weak"
    assert report["top_correlations"] == []


def test_single_numeric_column_has_no_correlations():
    df = pd.DataFrame({"a": [1, 2, 3]})
    report = compute_auto_eda(df)
    assert report["top_correlations"] == []


def test_empty_dataframe_does_not_crash():
    report = compute_auto_eda(pd.DataFrame())
    assert report == {"numeric_summary": {}, "top_categories": {}, "top_correlations": []}
