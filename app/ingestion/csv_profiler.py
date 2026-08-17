"""
Phase 2: Core CSV ingestion.

This module has one job: turn a raw CSV file into a compact "profile"
dictionary that describes its shape, columns, data types, missing values,
and a few sample rows. This profile is what we'll hand to the LLM in
Phase 3 instead of the raw file — cheaper, faster, and more reliable
than making the LLM guess at the data's structure.
"""

import os
import pandas as pd

# A deliberately conservative cap for a free-tier hobby/portfolio project —
# not a claim about what's "too big" in general, just a predictable limit
# that keeps load time and LLM prompt size fast and free-tier-friendly.
# Checked as a file-size (bytes on disk) rather than a row count, because
# that lets us reject an oversized file BEFORE spending time reading the
# whole thing into memory.
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def load_csv(file_path: str) -> pd.DataFrame:
    """
    Safely load a CSV file into a pandas DataFrame.

    We don't just call pd.read_csv() directly and hope for the best —
    we catch the specific ways this can fail and raise a clear,
    human-readable error instead of letting pandas' raw traceback
    surface.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No file found at: {file_path}")

    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE_BYTES:
        size_mb = file_size / (1024 * 1024)
        raise ValueError(
            f"File is {size_mb:.1f} MB, which is over the {MAX_FILE_SIZE_MB} MB "
            f"limit this project currently supports. Try a smaller file, or a "
            f"sample of the full dataset."
        )

    try:
        # Try standard UTF-8 first (the overwhelming majority of real CSVs).
        # Fall back to latin-1 for files exported from tools (e.g. older
        # Excel versions) that use a different encoding — latin-1 can
        # decode any byte sequence without erroring, so it's a safe
        # last-resort rather than crashing on an encoding mismatch.
        try:
            df = pd.read_csv(file_path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(file_path, encoding="latin-1")
    except pd.errors.EmptyDataError:
        raise ValueError(f"The file at {file_path} is empty — no data to read.")
    except pd.errors.ParserError as e:
        raise ValueError(f"Could not parse {file_path} as a CSV: {e}")

    if df.empty:
        raise ValueError(f"The file at {file_path} loaded, but contains no rows.")

    return df


def profile_dataframe(df: pd.DataFrame, sample_size: int = 5) -> dict:
    """
    Build a profile dictionary describing a DataFrame.

    This is deliberately a plain dict (not a class) — Phase 3 will
    need to convert this into text for an LLM prompt, and a dict
    converts to JSON with zero extra work.
    """
    columns_info = []
    for col in df.columns:
        columns_info.append({
            "name": col,
            "dtype": str(df[col].dtype),          # e.g. "int64", "object", "float64"
            "null_count": int(df[col].isnull().sum()),
            "unique_count": int(df[col].nunique()),
        })

    profile = {
        "shape": {
            "rows": df.shape[0],
            "columns": df.shape[1],
        },
        "columns": columns_info,
        "duplicate_rows": int(df.duplicated().sum()),
        # .head() gives real example rows so the LLM sees actual values,
        # not just abstract column names and types.
        "sample_rows": df.head(sample_size).to_dict(orient="records"),
    }
    return profile


def profile_csv(file_path: str, sample_size: int = 5) -> dict:
    """Convenience function: load a CSV and profile it in one call."""
    df = load_csv(file_path)
    return profile_dataframe(df, sample_size=sample_size)


# This block only runs when you execute this file directly
# (e.g. `python -m app.ingestion.csv_profiler`), not when another
# file imports functions from it. It's a quick way to demo the module
# without needing a separate test script yet.
if __name__ == "__main__":
    import json

    sample_path = os.path.join("data", "samples", "sample_sales.csv")
    result = profile_csv(sample_path)
    print(json.dumps(result, indent=2, default=str))
