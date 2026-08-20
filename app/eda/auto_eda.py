"""
Phase 16: richer automatic EDA.

Everything the agent has known about a dataset so far (Phases 2-14) was
either structural (shape/dtypes/nulls from the profiler) or about data
*quality* (Phase 12). Nothing computed actual descriptive statistics or
relationships between columns ahead of time -- the LLM had to work all
of that out itself, from scratch, on every single call.

This module closes that gap with a second deterministic report (same
"plain pandas math, no LLM judgment" pattern as app/quality/
data_quality.py): baseline numeric stats, top categories for low-
cardinality text columns, and the strongest numeric-to-numeric
correlations. Feeding this to the LLM (via llm_client.py) means it
spends its "creativity budget" on genuinely interesting angles and
chart choices instead of re-deriving a mean and a value_counts() call --
and, combined with Phase 12's structural_flags, it can also be told to
skip constant/ID-like columns instead of wasting an attempt analyzing
something meaningless.
"""

import pandas as pd

# Skip a categorical column for the "top categories" check once it has
# more distinct values than this -- past this point, "top categories"
# stops being a meaningful summary (nothing dominates) and just becomes
# noise in the prompt.
MAX_UNIQUE_FOR_TOP_CATEGORIES = 20
TOP_CATEGORIES_TO_SHOW = 5
TOP_CORRELATIONS_TO_SHOW = 5
# Below this, a correlation is closer to "no relationship" than anything
# worth surfacing -- filtering it out keeps the report focused.
MIN_CORRELATION_TO_REPORT = 0.3


def _numeric_summary(df: pd.DataFrame) -> dict:
    """Mean/median/std/min/max for every numeric column, rounded for readability."""
    summary = {}
    for col in df.select_dtypes(include="number").columns:
        series = df[col].dropna()
        if len(series) == 0:
            continue
        summary[col] = {
            "mean": round(float(series.mean()), 2),
            "median": round(float(series.median()), 2),
            "std": round(float(series.std()), 2) if len(series) > 1 else 0.0,
            "min": round(float(series.min()), 2),
            "max": round(float(series.max()), 2),
        }
    return summary


def _top_categories(df: pd.DataFrame, exclude: set) -> dict:
    """
    For each text column with a manageable number of distinct values
    (and not already flagged as constant/ID-like by the quality report),
    the top few values by frequency and their counts.
    """
    result = {}
    for col in df.select_dtypes(include=["object", "string"]).columns:
        if col in exclude:
            continue
        non_null = df[col].dropna()
        unique_count = non_null.nunique()
        if unique_count == 0 or unique_count > MAX_UNIQUE_FOR_TOP_CATEGORIES:
            continue
        counts = non_null.value_counts().head(TOP_CATEGORIES_TO_SHOW)
        result[col] = {str(k): int(v) for k, v in counts.items()}
    return result


def _top_correlations(df: pd.DataFrame) -> list:
    """
    The strongest pairwise correlations among numeric columns, above
    MIN_CORRELATION_TO_REPORT, sorted by absolute strength, deduplicated
    (A-B and B-A are the same relationship, only reported once), and
    with a column's correlation with itself (always 1.0) excluded.
    """
    numeric_df = df.select_dtypes(include="number")
    if numeric_df.shape[1] < 2:
        return []

    corr_matrix = numeric_df.corr()
    seen_pairs = set()
    pairs = []

    for col_a in corr_matrix.columns:
        for col_b in corr_matrix.columns:
            if col_a == col_b:
                continue
            pair_key = frozenset({col_a, col_b})
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            value = corr_matrix.loc[col_a, col_b]
            if pd.isna(value) or abs(value) < MIN_CORRELATION_TO_REPORT:
                continue
            pairs.append({"columns": [col_a, col_b], "correlation": round(float(value), 2)})

    pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)
    return pairs[:TOP_CORRELATIONS_TO_SHOW]


def compute_auto_eda(df: pd.DataFrame, exclude_columns: set = None) -> dict:
    """
    Run every baseline EDA check and roll them up into one report.
    `exclude_columns` is meant to be the union of a Phase 12 quality
    report's constant_columns + id_like_columns, so this report doesn't
    waste space summarizing columns that are already known to be
    meaningless for analysis. Optional -- pass nothing to include every
    column.
    """
    exclude_columns = exclude_columns or set()

    return {
        "numeric_summary": _numeric_summary(df),
        "top_categories": _top_categories(df, exclude=exclude_columns),
        "top_correlations": _top_correlations(df),
    }


# Demo block, same convention as every other module in this project:
#   python -m app.eda.auto_eda data/samples/sample_sales.csv
if __name__ == "__main__":
    import json
    import os
    import sys

    from app.ingestion.csv_profiler import load_csv

    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "samples", "sample_sales.csv")
    dataframe = load_csv(csv_path)
    report = compute_auto_eda(dataframe)
    print(json.dumps(report, indent=2, default=str))
