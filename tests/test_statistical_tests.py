"""
Phase 21: pytest tests for app/stats/statistical_tests.py -- pure
scipy/pandas, no LLM calls.
"""

import numpy as np
import pandas as pd

from app.stats.statistical_tests import run_hypothesis_tests

RNG = np.random.default_rng(42)


def test_two_group_real_difference_is_detected():
    # Two genuinely different distributions -- should come back significant.
    group_a = RNG.normal(loc=50, scale=5, size=100)
    group_b = RNG.normal(loc=70, scale=5, size=100)
    df = pd.DataFrame({
        "group": ["A"] * 100 + ["B"] * 100,
        "value": list(group_a) + list(group_b),
    })

    report = run_hypothesis_tests(df)

    assert report["total_tests_run"] == 1
    assert report["significant_results_count"] == 1
    result = report["top_significant_results"][0]
    assert result["test"] == "two-sample t-test"
    assert result["p_value"] < 0.05


def test_no_real_difference_is_not_flagged_as_significant():
    same_distribution = RNG.normal(loc=50, scale=5, size=200)
    df = pd.DataFrame({
        "group": ["A"] * 100 + ["B"] * 100,
        "value": list(same_distribution),
    })

    report = run_hypothesis_tests(df)
    assert report["significant_results_count"] == 0


def test_three_to_six_groups_uses_anova():
    df = pd.DataFrame({
        "group": ["A"] * 40 + ["B"] * 40 + ["C"] * 40,
        "value": list(RNG.normal(50, 5, 40)) + list(RNG.normal(50, 5, 40)) + list(RNG.normal(90, 5, 40)),
    })

    report = run_hypothesis_tests(df)
    assert report["top_significant_results"][0]["test"] == "one-way ANOVA"
    assert report["top_significant_results"][0]["groups_compared"] == 3


def test_categorical_column_outside_group_range_is_skipped():
    # A single-category column (1 group) and a high-cardinality column
    # (>6 groups) should both be skipped -- neither can be meaningfully tested.
    df = pd.DataFrame({
        "single_group": ["only_one"] * 50,
        "too_many_groups": [f"g{i}" for i in range(50)],
        "value": list(RNG.normal(50, 5, 50)),
    })

    report = run_hypothesis_tests(df)
    assert report["total_tests_run"] == 0


def test_excluded_columns_are_skipped():
    df = pd.DataFrame({
        "group": ["A"] * 50 + ["B"] * 50,
        "value": list(RNG.normal(50, 5, 100)),
    })
    report = run_hypothesis_tests(df, exclude_columns={"group"})
    assert report["total_tests_run"] == 0


def test_multiple_comparisons_note_present_when_tests_run():
    df = pd.DataFrame({
        "group": ["A"] * 50 + ["B"] * 50,
        "value": list(RNG.normal(50, 5, 100)),
    })
    report = run_hypothesis_tests(df)
    assert report["multiple_comparisons_note"] is not None
    assert "1 tests" in report["multiple_comparisons_note"]


def test_empty_dataframe_does_not_crash():
    report = run_hypothesis_tests(pd.DataFrame())
    assert report["total_tests_run"] == 0
    assert report["multiple_comparisons_note"] is None
