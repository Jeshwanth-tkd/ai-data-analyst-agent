"""
Phase 18: pytest tests for app/eda/auto_charts.py -- deterministic
matplotlib chart generation, no LLM calls.
"""

import os

import pandas as pd

from app.eda.auto_charts import generate_auto_eda_charts


def _is_valid_png(path: str) -> bool:
    with open(path, "rb") as f:
        header = f.read(8)
    return header == b"\x89PNG\r\n\x1a\n" and os.path.getsize(path) > 0


def test_generates_distribution_and_correlation_and_missingness_charts(tmp_path):
    df = pd.DataFrame({
        "a": [1, 2, 3, 4, None, 6, 7, 8],
        "b": [10, 20, 30, 40, 50, 60, 70, 80],
    })
    outputs_dir = str(tmp_path)
    paths = generate_auto_eda_charts(df, outputs_dir=outputs_dir)

    assert len(paths) > 0
    for path in paths:
        assert _is_valid_png(path)

    labels = " ".join(paths)
    assert "auto_dist_" in labels
    assert "auto_correlation_heatmap" in labels  # 2 numeric columns
    assert "auto_missingness" in labels  # column "a" has a missing value


def test_no_correlation_heatmap_with_single_numeric_column(tmp_path):
    # NOTE: check basenames, not full paths -- pytest names the tmp_path
    # directory after this very test function, and "correlation_heatmap"
    # is a substring of this test's own name, so checking the full path
    # would give a false positive from the directory name itself.
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5]})
    paths = generate_auto_eda_charts(df, outputs_dir=str(tmp_path))
    basenames = [os.path.basename(p) for p in paths]
    assert not any("correlation_heatmap" in b for b in basenames)


def test_no_missingness_chart_when_nothing_missing(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    paths = generate_auto_eda_charts(df, outputs_dir=str(tmp_path))
    basenames = [os.path.basename(p) for p in paths]
    assert not any("missingness" in b for b in basenames)


def test_distribution_charts_are_capped(tmp_path):
    # 10 numeric columns -- should still only produce at most
    # MAX_DISTRIBUTION_CHARTS distribution charts.
    data = {f"col_{i}": list(range(i, i + 20)) for i in range(10)}
    df = pd.DataFrame(data)
    paths = generate_auto_eda_charts(df, outputs_dir=str(tmp_path))

    dist_charts = [p for p in paths if "auto_dist_" in p]
    assert len(dist_charts) <= 4


def test_previous_run_charts_are_cleared(tmp_path):
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    outputs_dir = str(tmp_path)

    first_run = generate_auto_eda_charts(df, outputs_dir=outputs_dir)
    # Second run with a dataset that produces FEWER charts -- confirm
    # nothing from the first run lingers.
    second_run = generate_auto_eda_charts(pd.DataFrame({"a": [1, 2, 3]}), outputs_dir=outputs_dir)

    remaining_files = set(os.listdir(outputs_dir))
    assert remaining_files == {os.path.basename(p) for p in second_run}
