"""
Phase 23: confirms the subprocess wrapper built by run_code() actually
loads Excel/JSON/Parquet files correctly (not just CSV) before the
generated code runs -- this is the bug that would otherwise make every
non-CSV upload fail every self-correction attempt identically, since the
failure happens in the fixed wrapper preamble, before any LLM-generated
code even executes.
"""

from app.executor.code_executor import _build_load_statement, run_code

SAMPLE_XLSX = "data/samples/sample_sales.xlsx"
SAMPLE_JSON = "data/samples/sample_sales.json"
SAMPLE_PARQUET = "data/samples/sample_sales.parquet"
SAMPLE_CSV = "data/samples/sample_sales.csv"

PRINT_ROW_COUNT_CODE = "print(f'INSIGHT: row count is {len(df)}')"


def test_build_load_statement_dispatches_by_extension():
    assert "pd.read_excel" in _build_load_statement("file.xlsx")
    assert "pd.read_excel" in _build_load_statement("file.xls")
    assert "pd.read_json" in _build_load_statement("file.json")
    assert "pd.read_parquet" in _build_load_statement("file.parquet")
    assert "pd.read_csv" in _build_load_statement("file.csv")


def test_run_code_executes_against_excel_upload():
    result = run_code(PRINT_ROW_COUNT_CODE, SAMPLE_XLSX)
    assert result["success"] is True, result["stderr"]
    assert "INSIGHT: row count is 10" in result["stdout"]


def test_run_code_executes_against_json_upload():
    result = run_code(PRINT_ROW_COUNT_CODE, SAMPLE_JSON)
    assert result["success"] is True, result["stderr"]
    assert "INSIGHT: row count is 10" in result["stdout"]


def test_run_code_executes_against_parquet_upload():
    result = run_code(PRINT_ROW_COUNT_CODE, SAMPLE_PARQUET)
    assert result["success"] is True, result["stderr"]
    assert "INSIGHT: row count is 10" in result["stdout"]


def test_run_code_still_executes_against_csv_upload():
    result = run_code(PRINT_ROW_COUNT_CODE, SAMPLE_CSV)
    assert result["success"] is True, result["stderr"]
    assert "INSIGHT: row count is 10" in result["stdout"]
