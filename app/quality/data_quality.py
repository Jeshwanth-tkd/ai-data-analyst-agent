"""
Phase 12: Data Quality Engine.

Computes a deterministic "health report" for a dataset — no LLM call
involved anywhere in this file. Every check here is plain pandas math:
the same input always produces the same output, which is the entire
point. An LLM should be reserved for genuinely ambiguous judgment calls
("what analysis is interesting here?"); "what fraction of this column
is missing" is not ambiguous, so it doesn't belong behind an API call.

This module has zero dependency on app/agent or app/executor — it only
needs a DataFrame. That's deliberate: data quality assessment is a
useful, standalone capability with or without an LLM in the loop at all.
"""

import pandas as pd

# Tunable thresholds — named constants so every "why 0.95?" question has
# a one-line, explicit answer instead of a magic number buried in logic.
ID_LIKE_UNIQUE_RATIO = 0.95      # >95% unique values -> looks like an identifier column
HIGH_CARDINALITY_UNIQUE_RATIO = 0.5   # >50% unique values in a categorical column
HIGH_CARDINALITY_MIN_UNIQUE = 50      # ...or just a lot of distinct categories outright
TYPE_MISMATCH_PARSE_RATIO = 0.8  # >=80% of values in a text column parse as numbers/dates
CATEGORY_CHECK_MAX_UNIQUE = 50   # only worth checking for near-duplicate categories below this


def _missing_values_score(df: pd.DataFrame) -> tuple:
    """
    What fraction of all cells in the whole table are missing (NaN)?
    Score is just "100 minus the missing percentage" — a table with 6%
    missing values overall scores 94/100. Simple and easy to defend.
    """
    total_cells = df.shape[0] * df.shape[1]
    if total_cells == 0:
        return 100, {"overall_missing_pct": 0.0, "by_column": {}}

    missing_by_column = df.isnull().sum()
    total_missing = int(missing_by_column.sum())
    overall_missing_pct = round(100 * total_missing / total_cells, 1)

    score = round(100 - overall_missing_pct)
    details = {
        "overall_missing_pct": overall_missing_pct,
        # Only report columns that actually have missing values — a
        # long list of "0 missing" entries would just be noise.
        "by_column": {
            col: {"missing_count": int(count), "missing_pct": round(100 * count / df.shape[0], 1)}
            for col, count in missing_by_column.items()
            if count > 0
        },
    }
    return max(0, score), details


def _duplicate_rows_score(df: pd.DataFrame) -> tuple:
    """
    What fraction of rows are exact duplicates of another row?
    df.duplicated() flags every row that's an exact repeat of an
    earlier one (the first occurrence is NOT flagged — only the repeats).
    """
    if df.shape[0] == 0:
        return 100, {"duplicate_count": 0, "duplicate_pct": 0.0}

    duplicate_count = int(df.duplicated().sum())
    duplicate_pct = round(100 * duplicate_count / df.shape[0], 1)
    score = max(0, round(100 - duplicate_pct))
    return score, {"duplicate_count": duplicate_count, "duplicate_pct": duplicate_pct}


def _type_consistency_score(df: pd.DataFrame) -> tuple:
    """
    Find text (object-dtype) columns that are secretly numbers or dates
    stored as strings — a very common real-world data problem (e.g. a
    CSV export that quoted every column). We sample the column, try
    converting it with pandas' own parsers, and see what fraction
    actually converts cleanly.

    pd.to_numeric(series, errors="coerce") turns anything it can't
    parse into NaN instead of raising — so "parse success rate" is just
    "how much of the column did NOT become NaN after conversion."
    """
    text_columns = df.select_dtypes(include=["object", "string"]).columns
    flagged = []

    for col in text_columns:
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue

        numeric_parse_rate = pd.to_numeric(non_null, errors="coerce").notna().mean()
        datetime_parse_rate = pd.to_datetime(non_null, errors="coerce", format="mixed").notna().mean()

        if numeric_parse_rate >= TYPE_MISMATCH_PARSE_RATIO:
            flagged.append({"column": col, "looks_like": "numeric", "parse_rate": round(numeric_parse_rate, 2)})
        elif datetime_parse_rate >= TYPE_MISMATCH_PARSE_RATIO:
            flagged.append({"column": col, "looks_like": "date", "parse_rate": round(datetime_parse_rate, 2)})

    total_columns = df.shape[1]
    score = 100 if total_columns == 0 else round(100 * (1 - len(flagged) / total_columns))
    return max(0, score), {"flagged_columns": flagged}


def _outlier_score(df: pd.DataFrame) -> tuple:
    """
    For every numeric column, flag values outside the classic IQR fence:
    anything below Q1 - 1.5*IQR or above Q3 + 1.5*IQR. This is the same
    rule a box-and-whisker plot uses to decide which points to draw as
    individual dots outside the whiskers — a standard, explainable
    definition of "outlier," not a judgment call.
    """
    numeric_columns = df.select_dtypes(include="number").columns
    if len(numeric_columns) == 0:
        return 100, {"by_column": {}}

    per_column_fraction = {}
    for col in numeric_columns:
        series = df[col].dropna()
        if len(series) < 4:  # not enough data for quartiles to mean anything
            continue

        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:  # every value identical (or nearly) -> no meaningful spread
            continue

        lower_fence, upper_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outlier_count = int(((series < lower_fence) | (series > upper_fence)).sum())
        if outlier_count > 0:
            per_column_fraction[col] = round(outlier_count / len(series), 3)

    if not per_column_fraction:
        return 100, {"by_column": {}}

    avg_outlier_fraction = sum(per_column_fraction.values()) / len(per_column_fraction)
    score = max(0, round(100 * (1 - avg_outlier_fraction)))
    return score, {"by_column": per_column_fraction}


def _find_constant_columns(df: pd.DataFrame) -> list:
    """Columns with only one distinct value are useless for analysis — grouping or comparing by them tells you nothing."""
    return [col for col in df.columns if df[col].nunique(dropna=True) <= 1]


def _find_id_like_columns(df: pd.DataFrame) -> list:
    """Columns where almost every value is unique look like an identifier (order ID, row number) rather than something worth aggregating."""
    if df.shape[0] == 0:
        return []
    return [col for col in df.columns if df[col].nunique(dropna=True) / df.shape[0] > ID_LIKE_UNIQUE_RATIO]


def _find_high_cardinality_columns(df: pd.DataFrame, exclude: set) -> list:
    """
    Text columns with a huge number of distinct categories (but NOT
    already flagged as ID-like) — grouping or charting by these tends
    to produce unreadable results (a bar chart with 300 bars).
    """
    flagged = []
    for col in df.select_dtypes(include=["object", "string"]).columns:
        if col in exclude or df.shape[0] == 0:
            continue
        unique_count = df[col].nunique(dropna=True)
        if unique_count >= HIGH_CARDINALITY_MIN_UNIQUE or unique_count / df.shape[0] > HIGH_CARDINALITY_UNIQUE_RATIO:
            flagged.append(col)
    return flagged


def _find_inconsistent_categories(df: pd.DataFrame) -> dict:
    """
    Catches the classic "HR" vs "hr" vs " HR " problem: values that are
    clearly meant to be the same category but differ in case or
    whitespace, which silently splits what should be one group into
    several during a groupby.
    """
    findings = {}
    for col in df.select_dtypes(include=["object", "string"]).columns:
        non_null = df[col].dropna()
        unique_count = non_null.nunique()
        if unique_count == 0 or unique_count > CATEGORY_CHECK_MAX_UNIQUE:
            continue  # too many distinct values for this check to be meaningful/cheap

        # Group raw values by a normalized (lowercase, trimmed) form.
        normalized_groups = {}
        for raw_value in non_null.unique():
            key = str(raw_value).strip().lower()
            normalized_groups.setdefault(key, []).append(raw_value)

        # Only worth reporting where one normalized form has MORE THAN
        # one distinct raw spelling -- that's the actual inconsistency.
        inconsistent = {k: v for k, v in normalized_groups.items() if len(v) > 1}
        if inconsistent:
            findings[col] = inconsistent
    return findings


def assess_data_quality(df: pd.DataFrame) -> dict:
    """
    Run every deterministic quality check and roll them up into one
    report. Mirrors profile_dataframe()'s convention: takes a DataFrame,
    returns a plain dict (JSON-serializable, no custom classes).
    """
    missing_score, missing_details = _missing_values_score(df)
    duplicate_score, duplicate_details = _duplicate_rows_score(df)
    type_score, type_details = _type_consistency_score(df)
    outlier_score, outlier_details = _outlier_score(df)

    # The headline number: an unweighted average of the four scores
    # above. Unweighted on purpose -- a weighted formula would need its
    # own justification we don't have evidence for yet (e.g. "missing
    # values matter 2x more than outliers"), and an honest simple
    # formula beats a falsely-precise complicated one.
    overall_score = round((missing_score + duplicate_score + type_score + outlier_score) / 4)

    constant_columns = _find_constant_columns(df)
    id_like_columns = _find_id_like_columns(df)
    high_cardinality_columns = _find_high_cardinality_columns(
        df, exclude=set(constant_columns) | set(id_like_columns)
    )
    inconsistent_categories = _find_inconsistent_categories(df)

    return {
        "overall_score": overall_score,
        "scores": {
            "missing_values": missing_score,
            "duplicates": duplicate_score,
            "type_consistency": type_score,
            "outliers": outlier_score,
        },
        "details": {
            "missing_values": missing_details,
            "duplicates": duplicate_details,
            "type_consistency": type_details,
            "outliers": outlier_details,
        },
        "structural_flags": {
            "constant_columns": constant_columns,
            "id_like_columns": id_like_columns,
            "high_cardinality_columns": high_cardinality_columns,
            "inconsistent_categories": inconsistent_categories,
        },
    }


# Demo block, same convention as every other module in this project:
#   python -m app.quality.data_quality data/samples/messy_mixed_types.csv
if __name__ == "__main__":
    import json
    import os
    import sys

    from app.ingestion.csv_profiler import load_csv

    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "samples", "sample_sales.csv")
    dataframe = load_csv(csv_path)
    report = assess_data_quality(dataframe)
    print(json.dumps(report, indent=2, default=str))
