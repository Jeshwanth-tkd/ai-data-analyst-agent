"""
Phase 25: tests for app/forecasting/forecasting.py.

Covers auto-detection of a date+numeric column pair, the too-few-points
and no-date-column failure paths (both must return a clean {"ran":
False, "reason": ...} rather than raising), the exclude_columns
behavior for the numeric candidate, and that a real forecast produces a
plausible shape (right number of periods, a valid chart file).
"""

import os

import pandas as pd
import pytest

from app.forecasting.forecasting import (
    MIN_POINTS_FOR_FORECAST,
    detect_forecastable_series,
    forecast_time_series,
)


def _make_daily_series(n=30, start="2024-01-01"):
    dates = pd.date_range(start, periods=n, freq="D")
    values = [100 + i * 0.5 for i in range(n)]
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "value": values})


def test_detects_date_and_numeric_columns():
    df = _make_daily_series()
    detected = detect_forecastable_series(df)
    assert detected == {"date_column": "date", "value_column": "value"}


def test_detect_returns_none_when_no_date_column():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    assert detect_forecastable_series(df) is None


def test_detect_returns_none_when_no_numeric_column():
    df = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=5), "label": ["a", "b", "c", "d", "e"]})
    assert detect_forecastable_series(df) is None


def test_exclude_columns_skips_excluded_numeric_candidate():
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=10),
        "id": range(10),
        "value": range(10, 20),
    })
    detected = detect_forecastable_series(df, exclude_columns={"id"})
    assert detected["value_column"] == "value"


def test_forecast_fails_cleanly_with_too_few_distinct_dates():
    df = pd.DataFrame({
        "date": ["2024-01-01", "2024-01-01", "2024-01-02"],
        "value": [1, 2, 3],
    })
    result = forecast_time_series(df)
    assert result["ran"] is False
    assert "need at least" in result["reason"]


def test_forecast_fails_cleanly_with_no_date_column():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    result = forecast_time_series(df)
    assert result["ran"] is False
    assert "Could not find" in result["reason"]


def test_forecast_produces_expected_shape(tmp_path, monkeypatch):
    # Run from a temp cwd so the chart file this test writes doesn't
    # collide with / get cleaned up alongside a real analysis run's
    # outputs/ directory.
    monkeypatch.chdir(tmp_path)

    df = _make_daily_series(n=MIN_POINTS_FOR_FORECAST + 10)
    result = forecast_time_series(df, periods=5)

    assert result["ran"] is True
    assert result["date_column"] == "date"
    assert result["value_column"] == "value"
    assert result["forecast_periods"] == 5
    assert len(result["forecast"]) == 5
    for point in result["forecast"]:
        assert "date" in point
        assert isinstance(point["predicted_value"], float)
        assert isinstance(point["naive_baseline"], float)
    assert os.path.exists(result["chart_path"])
    assert os.path.getsize(result["chart_path"]) > 0


def test_forecast_averages_multiple_rows_on_the_same_date(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # Two rows per date, MIN_POINTS_FOR_FORECAST distinct dates.
    dates = []
    values = []
    for i in range(MIN_POINTS_FOR_FORECAST + 2):
        d = pd.Timestamp("2024-01-01") + pd.Timedelta(days=i)
        dates += [d, d]
        values += [10.0, 20.0]  # mean should be 15.0 for every date

    df = pd.DataFrame({"date": dates, "value": values})
    result = forecast_time_series(df)

    assert result["ran"] is True
    assert result["historical_points"] == MIN_POINTS_FOR_FORECAST + 2


def test_forecast_never_raises_on_garbage_input():
    # A DataFrame that superficially has the right columns but garbage
    # content shouldn't crash the caller -- it should come back as a
    # clean ran=False result.
    df = pd.DataFrame({"date": [None, None, None], "value": [None, None, None]})
    result = forecast_time_series(df)
    assert result["ran"] is False
