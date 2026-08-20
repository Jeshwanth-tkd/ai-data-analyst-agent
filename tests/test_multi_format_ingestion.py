"""
Phase 23: multi-format ingestion tests.

Covers load_data_file() dispatching to Excel/JSON/Parquet loaders, the
unsupported-extension error path, and confirms each format gets the same
size-cap / empty-check guarantees as load_csv() (rather than each format
silently skipping a safety check).
"""

import os

import pandas as pd
import pytest

from app.ingestion.csv_profiler import load_data_file, MAX_FILE_SIZE_BYTES

SAMPLE_XLSX = "data/samples/sample_sales.xlsx"
SAMPLE_JSON = "data/samples/sample_sales.json"
SAMPLE_PARQUET = "data/samples/sample_sales.parquet"
SAMPLE_CSV = "data/samples/sample_sales.csv"


def test_load_data_file_reads_excel():
    df = load_data_file(SAMPLE_XLSX)
    assert not df.empty
    assert df.shape[0] == 10


def test_load_data_file_reads_json():
    df = load_data_file(SAMPLE_JSON)
    assert not df.empty
    assert df.shape[0] == 10


def test_load_data_file_reads_parquet():
    df = load_data_file(SAMPLE_PARQUET)
    assert not df.empty
    assert df.shape[0] == 10


def test_load_data_file_still_reads_csv():
    # load_data_file() should route .csv straight to the existing,
    # already-tested load_csv() -- confirming the dispatcher doesn't
    # accidentally change CSV behavior.
    df = load_data_file(SAMPLE_CSV)
    assert not df.empty
    assert df.shape[0] == 10


def test_load_data_file_rejects_unsupported_extension(tmp_path):
    bad_file = tmp_path / "notes.txt"
    bad_file.write_text("just some text")

    with pytest.raises(ValueError, match="Unsupported file type"):
        load_data_file(str(bad_file))


def test_load_data_file_missing_file_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_data_file("data/samples/does_not_exist.xlsx")


def test_load_data_file_rejects_corrupt_excel(tmp_path):
    bad_file = tmp_path / "corrupt.xlsx"
    bad_file.write_text("not a real excel file")

    with pytest.raises(ValueError, match="Could not read"):
        load_data_file(str(bad_file))


def test_load_data_file_rejects_corrupt_json(tmp_path):
    bad_file = tmp_path / "corrupt.json"
    bad_file.write_text("not json {{{")

    with pytest.raises(ValueError, match="Could not read"):
        load_data_file(str(bad_file))


def test_load_data_file_rejects_corrupt_parquet(tmp_path):
    bad_file = tmp_path / "corrupt.parquet"
    bad_file.write_text("not a parquet file")

    with pytest.raises(ValueError, match="Could not read"):
        load_data_file(str(bad_file))


def test_load_data_file_enforces_size_cap_on_parquet(tmp_path):
    # The 5MB size cap must apply to every format, not just CSV --
    # build a parquet file bigger than the cap and confirm it's rejected
    # before pandas even tries to parse it.
    big_df = pd.DataFrame({"a": range(2_000_000)})
    big_path = tmp_path / "big.parquet"
    big_df.to_parquet(str(big_path), index=False)
    assert os.path.getsize(str(big_path)) > MAX_FILE_SIZE_BYTES

    with pytest.raises(ValueError, match="over the .* MB limit"):
        load_data_file(str(big_path))


def test_load_data_file_rejects_empty_excel(tmp_path):
    empty_df = pd.DataFrame()
    empty_path = tmp_path / "empty.xlsx"
    empty_df.to_excel(str(empty_path), index=False)

    with pytest.raises(ValueError, match="contains no rows"):
        load_data_file(str(empty_path))
