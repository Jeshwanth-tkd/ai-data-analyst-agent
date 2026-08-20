"""
Phase 21: Statistical analysis / hypothesis testing engine.

Phase 16's auto_eda.py reports correlations and category frequencies,
but it never answers the actual analyst question those numbers raise:
"is this difference REAL, or could it just be noise?" This module adds
that -- automatic hypothesis tests between categorical and numeric
columns, so a claim like "Category X has a higher average price" comes
with an actual p-value instead of just two numbers that happen to
differ.

Method selection is deterministic, not an LLM judgment call:
- Exactly 2 groups -> independent two-sample t-test (scipy.stats.ttest_ind)
- 3-6 groups -> one-way ANOVA (scipy.stats.f_oneway)
- Outside that range, the pair is skipped -- 1 group can't be compared
  to anything, and testing a column with 30 categories against a numeric
  column produces a result nobody can act on.

Honesty about multiple comparisons: testing every categorical/numeric
pair and reporting "significant" results (p < 0.05) without correction
is a well-known statistics trap -- run enough tests and ~5% will look
significant by pure chance. This module does NOT apply a formal
correction (e.g. Bonferroni), but DOES report how many total tests were
run alongside the significant ones specifically so that context isn't
hidden from whoever reads the output.
"""

import pandas as pd
from scipy import stats

MIN_GROUPS_FOR_TEST = 2
MAX_GROUPS_FOR_TEST = 6
MIN_GROUP_SIZE = 2  # a group with fewer than 2 values can't contribute to a t-test/ANOVA
SIGNIFICANCE_THRESHOLD = 0.05
TOP_RESULTS_TO_SHOW = 5


def _groups_for_column(df: pd.DataFrame, categorical_col: str, numeric_col: str) -> dict:
    """Numeric values split by category, dropping groups too small to test."""
    groups = {}
    for category, sub_df in df.groupby(categorical_col, observed=True):
        values = sub_df[numeric_col].dropna()
        if len(values) >= MIN_GROUP_SIZE:
            groups[str(category)] = values
    return groups


def _run_test_for_pair(df: pd.DataFrame, categorical_col: str, numeric_col: str) -> dict:
    groups = _groups_for_column(df, categorical_col, numeric_col)
    if len(groups) < MIN_GROUPS_FOR_TEST or len(groups) > MAX_GROUPS_FOR_TEST:
        return None

    group_values = list(groups.values())
    group_means = {name: round(float(values.mean()), 2) for name, values in groups.items()}

    if len(groups) == 2:
        stat, p_value = stats.ttest_ind(*group_values, equal_var=False, nan_policy="omit")
        test_name = "two-sample t-test"
    else:
        stat, p_value = stats.f_oneway(*group_values)
        test_name = "one-way ANOVA"

    if pd.isna(p_value):
        return None

    return {
        "categorical_column": categorical_col,
        "numeric_column": numeric_col,
        "test": test_name,
        "groups_compared": len(groups),
        "group_means": group_means,
        "statistic": round(float(stat), 3),
        "p_value": round(float(p_value), 4),
        "likely_significant": bool(p_value < SIGNIFICANCE_THRESHOLD),
    }


def run_hypothesis_tests(df: pd.DataFrame, exclude_columns: set = None, max_unique_for_grouping: int = MAX_GROUPS_FOR_TEST) -> dict:
    """
    Test every (categorical column, numeric column) pair where the
    categorical column has between 2 and 6 distinct values, and roll up
    the results. Returns a plain, JSON-serializable dict.
    """
    exclude_columns = exclude_columns or set()
    categorical_cols = [
        col for col in df.select_dtypes(include=["object", "string"]).columns
        if col not in exclude_columns and MIN_GROUPS_FOR_TEST <= df[col].nunique(dropna=True) <= max_unique_for_grouping
    ]
    numeric_cols = [col for col in df.select_dtypes(include="number").columns if col not in exclude_columns]

    all_results = []
    for cat_col in categorical_cols:
        for num_col in numeric_cols:
            result = _run_test_for_pair(df, cat_col, num_col)
            if result is not None:
                all_results.append(result)

    significant = [r for r in all_results if r["likely_significant"]]
    significant.sort(key=lambda r: r["p_value"])

    return {
        "total_tests_run": len(all_results),
        "significant_results_count": len(significant),
        "top_significant_results": significant[:TOP_RESULTS_TO_SHOW],
        "multiple_comparisons_note": (
            f"{len(all_results)} tests were run without a multiple-comparisons "
            "correction -- with enough tests, some 'significant' results are "
            "expected by chance alone. Treat these as leads worth a closer "
            "look, not proven conclusions."
        ) if len(all_results) > 0 else None,
    }


# Demo block: python -m app.stats.statistical_tests data/samples/sample_sales.csv
if __name__ == "__main__":
    import json
    import os
    import sys

    from app.ingestion.csv_profiler import load_csv

    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "samples", "sample_sales.csv")
    dataframe = load_csv(csv_path)
    report = run_hypothesis_tests(dataframe)
    print(json.dumps(report, indent=2, default=str))
