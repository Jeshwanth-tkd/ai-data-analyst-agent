"""
Phase 15: pytest suite.

Tests for app/ingestion/csv_profiler.py -- pure, deterministic, no LLM
calls, so these need no mocking at all.
"""

import pandas as pd
import pytest

from app.ingestion import csv_profiler


def test_load_csv_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        csv_profiler.load_csv("data/samples/this_file_does_not_exist.csv")


def test_load_csv_raises_on_empty_file(tmp_path):
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("")

    with pytest.raises(ValueError, match="empty"):
        csv_profiler.load_csv(str(empty_file))


def test_load_csv_raises_on_header_only_file(tmp_path):
    header_only = tmp_path / "header_only.csv"
    header_only.write_text("col_a,col_b,col_c\n")

    with pytest.raises(ValueError, match="no rows"):
        csv_profiler.load_csv(str(header_only))


def test_load_csv_rejects_oversized_file(tmp_path, monkeypatch):
    # Monkeypatch the size cap down to a few bytes instead of writing a
    # real multi-MB file -- same code path, much faster test.
    monkeypatch.setattr(csv_profiler, "MAX_FILE_SIZE_BYTES", 10)

    big_file = tmp_path / "big.csv"
    big_file.write_text("a,b,c\n1,2,3\n4,5,6\n")

    with pytest.raises(ValueError, match="MB"):
        csv_profiler.load_csv(str(big_file))


def test_load_csv_reads_valid_file():
    df = csv_profiler.load_csv("data/samples/sample_sales.csv")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


def test_profile_dataframe_reports_correct_shape():
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    profile = csv_profiler.profile_dataframe(df)

    assert profile["shape"] == {"rows": 3, "columns": 2}
    assert len(profile["columns"]) == 2
    assert profile["duplicate_rows"] == 0


def test_profile_dataframe_counts_nulls_and_duplicates():
    df = pd.DataFrame({
        "a": [1, 1, None],
        "b": ["x", "x", "y"],
    })
    profile = csv_profiler.profile_dataframe(df)

    col_a = next(c for c in profile["columns"] if c["name"] == "a")
    assert col_a["null_count"] == 1

    # Rows 0 and 1 are exact duplicates of each other.
    assert profile["duplicate_rows"] == 1


def test_profile_csv_end_to_end():
    profile = csv_profiler.profile_csv("data/samples/sample_sales.csv")
    assert profile["shape"]["rows"] > 0
    assert profile["shape"]["columns"] > 0
    assert isinstance(profile["sample_rows"], list)
