"""
Phase 20: pytest tests for app/anomalies/anomaly_detection.py -- pure
pandas/scikit-learn, no LLM calls.
"""

import numpy as np
import pandas as pd

from app.anomalies.anomaly_detection import detect_anomalies

# Fixed seed so these tests are deterministic despite IsolationForest's
# internal randomness (random_state=42 is hardcoded in the module itself).
RNG = np.random.default_rng(42)


def _make_normal_dataset(n=200):
    return pd.DataFrame({
        "a": RNG.normal(loc=50, scale=5, size=n),
        "b": RNG.normal(loc=100, scale=10, size=n),
    })


def test_isolation_forest_flags_roughly_the_contamination_rate():
    # Regression test for a real bug: contamination="auto" flagged
    # 65-69% of rows on real sample data instead of a sane ~5%. This
    # pins the fixed behavior (explicit contamination=0.05) in place.
    df = _make_normal_dataset(200)
    report = detect_anomalies(df)

    iso = report["isolation_forest"]
    assert iso["ran"] is True
    # Should be in the same ballpark as the 5% contamination setting --
    # not exact (it's a real model), but nowhere near 65%+.
    assert 0 < iso["anomalous_row_pct"] < 15


def test_id_like_column_is_excluded_from_isolation_forest():
    df = pd.DataFrame({
        "record_id": range(200),  # pure noise dimension if included
        "value": RNG.normal(loc=50, scale=5, size=200),
        "value2": RNG.normal(loc=100, scale=10, size=200),
    })
    report = detect_anomalies(df, exclude_columns={"record_id"})

    top_row = report["isolation_forest"]["top_anomalous_rows"][0]
    assert "record_id" not in top_row


def test_isolation_forest_skipped_with_too_few_rows():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    report = detect_anomalies(df)
    assert report["isolation_forest"]["ran"] is False


def test_isolation_forest_skipped_with_single_numeric_column():
    df = pd.DataFrame({"a": list(range(20))})
    report = detect_anomalies(df)
    assert report["isolation_forest"]["ran"] is False


def test_z_score_flags_extreme_value():
    values = [10] * 30 + [1000]  # one wildly extreme value
    df = pd.DataFrame({"value": values})
    report = detect_anomalies(df)
    assert "value" in report["z_score_outliers"]
    assert report["z_score_outliers"]["value"]["outlier_count"] == 1


def test_z_score_excludes_specified_columns():
    values = [10] * 30 + [1000]
    df = pd.DataFrame({"value": values})
    report = detect_anomalies(df, exclude_columns={"value"})
    assert report["z_score_outliers"] == {}


def test_empty_dataframe_does_not_crash():
    report = detect_anomalies(pd.DataFrame())
    assert report["z_score_outliers"] == {}
    assert report["isolation_forest"]["ran"] is False
