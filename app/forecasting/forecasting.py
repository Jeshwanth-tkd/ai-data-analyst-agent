"""
Phase 25: Forecasting.

Time-series forecasting for datasets that have a date-like column and a
numeric column worth predicting forward. Deterministic (statsmodels),
no LLM call -- forecasting a trend from historical numbers is a
statistical modeling problem, not a judgment call an LLM should make.

Design decisions:
- Model choice: Holt's linear trend method (statsmodels'
  ExponentialSmoothing with trend="add", seasonal=None). This is a
  deliberately simple, well-understood default that works reasonably on
  short, arbitrary-frequency series without needing to reliably detect
  a seasonal period first (a much harder, more fragile problem out of
  scope for this phase). This is a documented, known limitation, not a
  claim that seasonality doesn't matter -- see the README's Phase 25
  entry.
- A naive baseline (repeat the last observed value for every future
  step) is always returned alongside the model's forecast, so a viewer
  can sanity-check whether the trend model is actually adding value over
  "just guess the last number again" -- an honest comparison rather than
  presenting the model's output as unquestionably better.
- Date-column detection deliberately does NOT consult Phase 12's
  "id-like" quality flag at all -- a daily-granularity date column (one
  row per day) is very often >95% unique values, exactly what that
  heuristic flags, but that's precisely the shape of column forecasting
  needs, not junk to discard. The caller-supplied `exclude_columns` is
  ALSO deliberately not "id-like columns" by default for the numeric
  side either (see app/output/insights.py's call site) -- a genuine
  continuous metric worth forecasting (revenue, price, temperature) is
  routinely >95% unique too, so that heuristic would silently disable
  forecasting on exactly the columns most worth forecasting. This
  module only excludes what its caller explicitly passes; it applies no
  built-in numeric filtering of its own.
- Every failure path (no date column found, too few data points, model
  fit error) returns a clean {"ran": False, "reason": ...} dict rather
  than raising -- forecasting is one optional report among several, and
  should never be able to take down the rest of the pipeline.
"""

import os
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# A daily-granularity series needs a handful of points before a trend
# estimate means anything at all -- 5 is a low, deliberately permissive
# floor (not a claim that 5 points gives a reliable forecast), chosen so
# small real-world sample datasets aren't blocked outright.
MIN_POINTS_FOR_FORECAST = 5
DEFAULT_FORECAST_PERIODS = 7
# Same threshold Phase 12's type-consistency check uses for "this text
# column looks like it's actually dates" -- kept consistent rather than
# picking a new number with no justification.
DATE_PARSE_RATIO = 0.8

FORECAST_OUTPUTS_DIR = os.path.join("outputs", "forecasting")


def _find_date_like_columns(df: pd.DataFrame) -> list:
    candidates = []

    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            candidates.append(col)

    # select_dtypes(include=["object", "string"]) (the same call Phase
    # 12's data_quality.py uses) rather than comparing dtype == object
    # directly -- pandas' default text dtype isn't guaranteed to compare
    # equal to the plain `object` sentinel across pandas versions (e.g.
    # pandas 3.x's default inferred text dtype is its own StringDtype,
    # not `object`), and select_dtypes' string/object aliases already
    # handle that instead of us hand-rolling a dtype check that quietly
    # stops matching on a pandas upgrade.
    for col in df.select_dtypes(include=["object", "string"]).columns:
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        parse_rate = pd.to_datetime(non_null, errors="coerce", format="mixed").notna().mean()
        if parse_rate >= DATE_PARSE_RATIO:
            candidates.append(col)

    return candidates


def detect_forecastable_series(df: pd.DataFrame, exclude_columns: set = None) -> dict:
    """
    Picks the first date-like column and first eligible numeric column
    to forecast. Returns {"date_column": ..., "value_column": ...} or
    None if no valid (date, numeric) pair exists.
    """
    exclude_columns = exclude_columns or set()

    date_candidates = _find_date_like_columns(df)
    numeric_candidates = [
        col for col in df.select_dtypes(include="number").columns if col not in exclude_columns
    ]

    if not date_candidates or not numeric_candidates:
        return None

    return {"date_column": date_candidates[0], "value_column": numeric_candidates[0]}


def _infer_step(index: pd.DatetimeIndex):
    if len(index) < 2:
        return pd.Timedelta(days=1)
    diffs = index.to_series().diff().dropna()
    if diffs.empty:
        return pd.Timedelta(days=1)
    return diffs.median()


def _save_forecast_chart(series: pd.Series, forecast_dates: list, forecast_values, value_column: str) -> str:
    os.makedirs(FORECAST_OUTPUTS_DIR, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(series.index, series.values, label="Historical", marker="o", markersize=3)
    ax.plot(forecast_dates, forecast_values, label="Forecast", marker="o", markersize=3, linestyle="--")
    ax.set_title(f"Forecast: {value_column}")
    ax.set_xlabel("Date")
    ax.set_ylabel(value_column)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()

    # Kept in its own subdirectory (not outputs/chart_*.png) so it's
    # never picked up or cleared by the LLM-chart bookkeeping in
    # app/output/insights.py (clear_outputs_dir/list_chart_files), which
    # only knows about "chart_*.png" at the top level of outputs/ --
    # same pattern app/eda/auto_charts.py already uses for its own charts.
    safe_name = "".join(c if c.isalnum() else "_" for c in value_column)
    chart_path = os.path.join(FORECAST_OUTPUTS_DIR, f"forecast_{safe_name}.png")
    fig.savefig(chart_path)
    plt.close(fig)
    return chart_path


def forecast_time_series(
    df: pd.DataFrame,
    date_column: str = None,
    value_column: str = None,
    periods: int = DEFAULT_FORECAST_PERIODS,
    exclude_columns: set = None,
) -> dict:
    """
    Forecasts `periods` steps forward for one numeric column against one
    date column. If date_column/value_column aren't given, they're
    auto-detected via detect_forecastable_series().

    Always returns a dict with a "ran" key -- True with the forecast
    data, or False with a human-readable "reason", never raises.
    """
    try:
        if date_column is None or value_column is None:
            detected = detect_forecastable_series(df, exclude_columns=exclude_columns)
            if detected is None:
                return {
                    "ran": False,
                    "reason": "Could not find both a date-like column and a numeric column to forecast.",
                }
            date_column = date_column or detected["date_column"]
            value_column = value_column or detected["value_column"]

        working = df[[date_column, value_column]].copy()
        working[date_column] = pd.to_datetime(working[date_column], errors="coerce", format="mixed")
        working = working.dropna(subset=[date_column, value_column])

        if working.empty:
            return {
                "ran": False,
                "reason": f"No valid (date, value) pairs found in '{date_column}' / '{value_column}'.",
            }

        # Multiple rows can share the same date (e.g. several orders per
        # day) -- averaging them down to one point per date is a
        # defensible default for "typical value on this date" without
        # assuming summing is meaningful for every metric a user might
        # pick (it would be for revenue, not for a rating, for instance).
        series = working.groupby(date_column)[value_column].mean().sort_index()

        if len(series) < MIN_POINTS_FOR_FORECAST:
            return {
                "ran": False,
                "reason": (
                    f"Only {len(series)} distinct date(s) found for '{date_column}' -- "
                    f"need at least {MIN_POINTS_FOR_FORECAST} to forecast meaningfully."
                ),
            }

        with warnings.catch_warnings():
            # statsmodels warns loudly about convergence on short series
            # -- expected and harmless here, not something we want
            # leaking into logs every single run.
            warnings.simplefilter("ignore")
            model = ExponentialSmoothing(
                series.values, trend="add", seasonal=None, initialization_method="estimated"
            )
            fit = model.fit()
            forecast_values = fit.forecast(periods)

        naive_forecast = [float(series.iloc[-1])] * periods

        last_date = series.index[-1]
        step = _infer_step(series.index)
        forecast_dates = [last_date + step * (i + 1) for i in range(periods)]

        chart_path = _save_forecast_chart(series, forecast_dates, forecast_values, value_column)

        return {
            "ran": True,
            "date_column": date_column,
            "value_column": value_column,
            "historical_points": len(series),
            "forecast_periods": periods,
            "forecast": [
                {
                    "date": str(d.date()),
                    "predicted_value": round(float(v), 2),
                    "naive_baseline": round(nv, 2),
                }
                for d, v, nv in zip(forecast_dates, forecast_values, naive_forecast)
            ],
            "chart_path": chart_path,
        }
    except Exception as e:
        return {"ran": False, "reason": f"Forecasting failed unexpectedly: {e}"}


# Demo block, same convention as every other module in this project:
#   python -m app.forecasting.forecasting data/samples/daily_sales_timeseries.csv
if __name__ == "__main__":
    import json
    import sys

    from app.ingestion.csv_profiler import load_csv

    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "samples", "daily_sales_timeseries.csv")
    dataframe = load_csv(csv_path)
    result = forecast_time_series(dataframe)
    print(json.dumps(result, indent=2, default=str))
