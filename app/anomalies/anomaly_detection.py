"""
Phase 20: Anomaly detection.

Phase 12's data_quality.py already flags outliers, but only PER COLUMN
(a value outside that one column's IQR fence). It has no way to catch a
row that's perfectly normal in every individual column but is an
unusual COMBINATION -- e.g. a 22-year-old with 40 years of work
experience: neither value is extreme on its own, but together they
don't make sense. That's a multivariate anomaly, and it needs a
different technique than checking columns one at a time.

This module adds two complementary, deterministic techniques:
- Z-score outliers (per column, like IQR but using standard deviations
  from the mean instead of quartiles -- a different, useful lens: IQR is
  robust to extreme values distorting the fence, z-score is the more
  "classical statistics" definition, and the two don't always agree).
- Isolation Forest (multivariate, row-level) -- scikit-learn's algorithm
  for flagging whole rows as anomalous based on ALL numeric columns
  together, not one at a time. This is the genuinely new capability
  here.

Design note: unlike quality_report/eda_summary, this report is NOT
threaded into the LLM's prompt (analyze_csv_file() attaches it straight
to the result dict for the UI only). Keeping this phase's surface area
smaller on purpose -- the prompt already carries profile + quality +
EDA + plan, and there's a real cost (token usage, prompt complexity) to
piling on a fourth context block without a demonstrated need for the
LLM to react to it yet.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

Z_SCORE_THRESHOLD = 3.0  # values more than 3 standard deviations from the mean
MIN_ROWS_FOR_ISOLATION_FOREST = 10  # below this, "anomalous" isn't a meaningful concept
MIN_NUMERIC_COLUMNS_FOR_ISOLATION_FOREST = 2  # need at least 2 dimensions for "multivariate" to mean anything
TOP_ANOMALOUS_ROWS_TO_SHOW = 5
# A conventional prior ("assume up to ~5% of rows could be anomalous"),
# NOT a measurement of this specific dataset. This was tested explicitly
# against scikit-learn's contamination="auto" option, which sounds like
# it would be the safer/more honest choice -- it isn't: "auto" replays a
# fixed legacy threshold from the original 2008 Isolation Forest paper
# rather than calibrating to the data, and on real test data here it
# flagged 65-69% of rows as "anomalous", which is obviously wrong.
# Passing an explicit float instead makes scikit-learn calibrate the
# decision threshold so that ~this fraction of the training data is
# flagged -- verified to produce a sane ~5% on real sample data.
ANOMALY_CONTAMINATION = 0.05


def _z_score_outliers(df: pd.DataFrame, exclude_columns: set = None) -> dict:
    """Per-column outliers using the z-score method: |value - mean| / std > threshold."""
    exclude_columns = exclude_columns or set()
    result = {}
    for col in df.select_dtypes(include="number").columns:
        if col in exclude_columns:
            continue
        series = df[col].dropna()
        if len(series) < 2 or series.std() == 0:
            continue
        z_scores = (series - series.mean()) / series.std()
        outlier_count = int((z_scores.abs() > Z_SCORE_THRESHOLD).sum())
        if outlier_count > 0:
            result[col] = {
                "outlier_count": outlier_count,
                "outlier_pct": round(100 * outlier_count / len(series), 1),
            }
    return result


def _isolation_forest_anomalies(df: pd.DataFrame, exclude_columns: set = None) -> dict:
    """
    Row-level multivariate anomaly detection. Rows with any missing
    numeric value are dropped for this check specifically (Isolation
    Forest needs complete rows) -- this is a real limitation worth being
    upfront about, not silently working around: a dataset that's mostly
    missing values in its numeric columns will have very few rows left
    to actually check.

    `exclude_columns` matters more here than it might seem -- an ID-like
    column (e.g. employee_id) contributes a dimension of pure noise
    with no real relationship to the others, and empirically pollutes
    the anomaly scores for every other feature it's mixed in with.
    """
    exclude_columns = exclude_columns or set()
    numeric_df = df.select_dtypes(include="number").drop(columns=list(exclude_columns), errors="ignore").dropna()

    if numeric_df.shape[1] < MIN_NUMERIC_COLUMNS_FOR_ISOLATION_FOREST:
        return {"ran": False, "reason": "Needs at least 2 numeric columns to detect multivariate anomalies."}
    if numeric_df.shape[0] < MIN_ROWS_FOR_ISOLATION_FOREST:
        return {"ran": False, "reason": f"Needs at least {MIN_ROWS_FOR_ISOLATION_FOREST} complete numeric rows."}

    model = IsolationForest(contamination=ANOMALY_CONTAMINATION, random_state=42)
    predictions = model.fit_predict(numeric_df)  # -1 = anomaly, 1 = normal
    scores = model.score_samples(numeric_df)  # lower = more anomalous

    anomaly_mask = predictions == -1
    anomalous_indices = numeric_df.index[anomaly_mask].tolist()

    # Rank the anomalous rows by how anomalous they are, most extreme first.
    ranked = sorted(zip(anomalous_indices, scores[anomaly_mask]), key=lambda pair: pair[1])
    top_rows = [
        {"row_index": int(idx), "anomaly_score": round(float(score), 3), **numeric_df.loc[idx].to_dict()}
        for idx, score in ranked[:TOP_ANOMALOUS_ROWS_TO_SHOW]
    ]

    return {
        "ran": True,
        "rows_checked": int(numeric_df.shape[0]),
        "anomalous_row_count": int(anomaly_mask.sum()),
        "anomalous_row_pct": round(100 * anomaly_mask.sum() / numeric_df.shape[0], 1),
        "top_anomalous_rows": top_rows,
    }


def detect_anomalies(df: pd.DataFrame, exclude_columns: set = None) -> dict:
    """
    Run both anomaly detection techniques and roll them up into one
    report. Mirrors the plain-dict, JSON-serializable convention used
    by every other deterministic report in this project. `exclude_columns`
    is meant to be the same constant/ID-like column set already computed
    by Phase 12's data quality report.
    """
    return {
        "z_score_outliers": _z_score_outliers(df, exclude_columns),
        "isolation_forest": _isolation_forest_anomalies(df, exclude_columns),
    }


# Demo block: python -m app.anomalies.anomaly_detection data/samples/sample_sales.csv
if __name__ == "__main__":
    import json
    import os
    import sys

    from app.ingestion.csv_profiler import load_csv

    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "samples", "sample_sales.csv")
    dataframe = load_csv(csv_path)
    report = detect_anomalies(dataframe)
    print(json.dumps(report, indent=2, default=str))
