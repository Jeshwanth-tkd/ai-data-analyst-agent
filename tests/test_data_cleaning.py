"""
Phase 24: tests for app/cleaning/data_cleaning.py.

Covers suggestion generation (numeric vs categorical missing values,
duplicates, inconsistent categories, constant/ID-like columns staying
suggestion-only) and applying the auto_applied subset, including the
guarantee that the original DataFrame is never mutated.
"""

import pandas as pd

from app.cleaning.data_cleaning import apply_cleaning_actions, suggest_cleaning_actions
from app.quality.data_quality import assess_data_quality


def test_suggests_numeric_fill_for_numeric_missing_values():
    df = pd.DataFrame({"price": [10.0, None, 30.0, 40.0]})
    report = assess_data_quality(df)

    actions = suggest_cleaning_actions(df, report)

    numeric_fills = [a for a in actions if a["type"] == "fill_missing_numeric"]
    assert len(numeric_fills) == 1
    assert numeric_fills[0]["column"] == "price"
    assert numeric_fills[0]["auto_applied"] is True


def test_suggests_categorical_fill_for_text_missing_values():
    df = pd.DataFrame({"category": ["a", None, "b", "a"]})
    report = assess_data_quality(df)

    actions = suggest_cleaning_actions(df, report)

    categorical_fills = [a for a in actions if a["type"] == "fill_missing_categorical"]
    assert len(categorical_fills) == 1
    assert categorical_fills[0]["column"] == "category"
    assert categorical_fills[0]["auto_applied"] is True


def test_suggests_drop_duplicates_when_present():
    df = pd.DataFrame({"a": [1, 2, 1], "b": ["x", "y", "x"]})
    report = assess_data_quality(df)

    actions = suggest_cleaning_actions(df, report)

    dup_actions = [a for a in actions if a["type"] == "drop_duplicates"]
    assert len(dup_actions) == 1
    assert dup_actions[0]["auto_applied"] is True


def test_no_duplicate_suggestion_when_none_exist():
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    report = assess_data_quality(df)

    actions = suggest_cleaning_actions(df, report)

    assert not [a for a in actions if a["type"] == "drop_duplicates"]


def test_suggests_standardize_categories_for_inconsistent_spellings():
    df = pd.DataFrame({"region": ["USA", "usa", " USA", "Canada", "Canada"]})
    report = assess_data_quality(df)

    actions = suggest_cleaning_actions(df, report)

    standardize_actions = [a for a in actions if a["type"] == "standardize_categories"]
    assert len(standardize_actions) == 1
    assert standardize_actions[0]["column"] == "region"
    assert standardize_actions[0]["auto_applied"] is True


def test_constant_column_is_suggestion_only_not_auto_applied():
    df = pd.DataFrame({"flag": ["yes", "yes", "yes"], "value": [1, 2, 3]})
    report = assess_data_quality(df)

    actions = suggest_cleaning_actions(df, report)

    constant_actions = [a for a in actions if a["type"] == "drop_constant_column"]
    assert len(constant_actions) == 1
    assert constant_actions[0]["column"] == "flag"
    assert constant_actions[0]["auto_applied"] is False


def test_id_like_column_is_suggestion_only_not_auto_applied():
    # "value" repeats (not unique per row) so only "id" trips the
    # id-like-column check -- a value column that's also all-unique
    # would (correctly) get flagged too, which isn't what this test is
    # isolating.
    df = pd.DataFrame({"id": [1, 2, 3, 4, 5], "value": [10, 10, 30, 30, 50]})
    report = assess_data_quality(df)

    actions = suggest_cleaning_actions(df, report)

    id_actions = [a for a in actions if a["type"] == "drop_id_column"]
    assert len(id_actions) == 1
    assert id_actions[0]["column"] == "id"
    assert id_actions[0]["auto_applied"] is False


def test_apply_cleaning_actions_fills_numeric_missing_with_median():
    df = pd.DataFrame({"price": [10.0, None, 30.0]})
    actions = [{"type": "fill_missing_numeric", "column": "price", "auto_applied": True}]

    result = apply_cleaning_actions(df, actions)

    assert result["cleaned_df"]["price"].isnull().sum() == 0
    assert result["cleaned_df"]["price"].iloc[1] == 20.0  # median of 10, 30
    assert len(result["log"]) == 1


def test_apply_cleaning_actions_fills_categorical_missing_with_unknown():
    df = pd.DataFrame({"category": ["a", None, "b"]})
    actions = [{"type": "fill_missing_categorical", "column": "category", "auto_applied": True}]

    result = apply_cleaning_actions(df, actions)

    assert result["cleaned_df"]["category"].isnull().sum() == 0
    assert result["cleaned_df"]["category"].iloc[1] == "Unknown"


def test_apply_cleaning_actions_drops_duplicates():
    df = pd.DataFrame({"a": [1, 2, 1], "b": ["x", "y", "x"]})
    actions = [{"type": "drop_duplicates", "column": None, "auto_applied": True}]

    result = apply_cleaning_actions(df, actions)

    assert len(result["cleaned_df"]) == 2


def test_apply_cleaning_actions_standardizes_categories_to_most_common_spelling():
    df = pd.DataFrame({"region": ["USA", "USA", "usa", "Canada"]})
    actions = [{"type": "standardize_categories", "column": "region", "auto_applied": True}]

    result = apply_cleaning_actions(df, actions)

    # "USA" appears twice (most common original spelling), "usa" once --
    # both should collapse to "USA".
    assert set(result["cleaned_df"]["region"].unique()) == {"USA", "Canada"}


def test_apply_cleaning_actions_skips_actions_not_flagged_auto_applied():
    df = pd.DataFrame({"id": [1, 2, 3]})
    actions = [{"type": "drop_id_column", "column": "id", "auto_applied": False}]

    result = apply_cleaning_actions(df, actions)

    # Nothing should happen -- the column must still be present.
    assert "id" in result["cleaned_df"].columns
    assert result["log"] == []


def test_apply_cleaning_actions_never_mutates_the_original_dataframe():
    df = pd.DataFrame({"price": [10.0, None, 30.0]})
    original_null_count = df["price"].isnull().sum()

    actions = [{"type": "fill_missing_numeric", "column": "price", "auto_applied": True}]
    apply_cleaning_actions(df, actions)

    assert df["price"].isnull().sum() == original_null_count  # unchanged
