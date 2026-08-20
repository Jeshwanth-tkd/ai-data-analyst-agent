"""
Phase 15: pytest suite.

Tests for app/quality/data_quality.py -- pure pandas math, no LLM calls.
"""

import pandas as pd

from app.quality.data_quality import assess_data_quality


def test_clean_dataframe_scores_high():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "category": ["a", "b", "c", "a", "b"],
        "value": [10, 20, 30, 40, 50],
    })
    report = assess_data_quality(df)

    assert report["overall_score"] >= 90
    assert report["scores"]["missing_values"] == 100
    assert report["scores"]["duplicates"] == 100


def test_missing_values_lower_the_score():
    df = pd.DataFrame({"a": [1, None, None, 4], "b": [1, 2, 3, 4]})
    report = assess_data_quality(df)

    assert report["scores"]["missing_values"] < 100
    assert report["details"]["missing_values"]["by_column"]["a"]["missing_count"] == 2


def test_duplicate_rows_lower_the_score():
    df = pd.DataFrame({"a": [1, 1, 1, 2], "b": ["x", "x", "x", "y"]})
    report = assess_data_quality(df)

    assert report["scores"]["duplicates"] < 100
    assert report["details"]["duplicates"]["duplicate_count"] == 2


def test_type_consistency_flags_numeric_stored_as_text():
    df = pd.DataFrame({"quantity": ["1", "2", "3", "4", "5"]})
    report = assess_data_quality(df)

    flagged_columns = [f["column"] for f in report["details"]["type_consistency"]["flagged_columns"]]
    assert "quantity" in flagged_columns


def test_outlier_detection_flags_extreme_value():
    df = pd.DataFrame({"value": [10, 11, 12, 13, 14, 1000]})
    report = assess_data_quality(df)

    assert "value" in report["details"]["outliers"]["by_column"]
    assert report["scores"]["outliers"] < 100


def test_constant_column_is_flagged():
    df = pd.DataFrame({"always_same": [1, 1, 1, 1], "varies": [1, 2, 3, 4]})
    report = assess_data_quality(df)

    assert "always_same" in report["structural_flags"]["constant_columns"]
    assert "varies" not in report["structural_flags"]["constant_columns"]


def test_id_like_column_is_flagged():
    df = pd.DataFrame({
        "order_id": [f"ORD-{i}" for i in range(100)],
        "status": ["done"] * 100,
    })
    report = assess_data_quality(df)

    assert "order_id" in report["structural_flags"]["id_like_columns"]


def test_inconsistent_category_spellings_are_flagged():
    df = pd.DataFrame({"dept": ["HR", "hr", " HR ", "Sales", "Sales"]})
    report = assess_data_quality(df)

    assert "dept" in report["structural_flags"]["inconsistent_categories"]


def test_empty_dataframe_does_not_crash():
    df = pd.DataFrame()
    report = assess_data_quality(df)
    assert report["overall_score"] == 100
