"""
Phase 22: pytest tests for app/sql/sql_analyst.py. Groq is mocked -- no
real network calls. The read-only database enforcement itself IS real
(no mocking) -- these tests exercise actual SQLite connections.
"""

import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pandas as pd

from app.sql.sql_analyst import _run_readonly_query, answer_sql_question
from app.ingestion.csv_profiler import load_csv

SAMPLE_CSV = "data/samples/sample_sales.csv"


def _mock_sql(sql: str):
    r = MagicMock()
    r.choices[0].message.content = f"```sql\n{sql}\n```"
    return r


def test_safe_query_returns_expected_rows():
    df = load_csv(SAMPLE_CSV)
    with patch("app.sql.sql_analyst.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = _mock_sql(
            "SELECT COUNT(*) as n FROM data"
        )
        result = answer_sql_question(df, "how many rows?")

    assert result["success"] is True
    assert result["columns"] == ["n"]
    assert result["rows"][0][0] == len(df)


def test_unsafe_query_is_blocked_and_retried():
    df = load_csv(SAMPLE_CSV)
    call_count = {"n": 0}

    def fake_create(*args, **kwargs):
        call_count["n"] += 1
        sql = "DROP TABLE data" if call_count["n"] == 1 else "SELECT 1"
        return _mock_sql(sql)

    with patch("app.sql.sql_analyst.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = fake_create
        result = answer_sql_question(df, "delete everything")

    assert result["success"] is True
    assert result["attempts"][0]["blocked_by_scanner"] is True
    assert call_count["n"] == 2


def test_sql_syntax_error_triggers_retry():
    df = load_csv(SAMPLE_CSV)
    call_count = {"n": 0}

    def fake_create(*args, **kwargs):
        call_count["n"] += 1
        sql = "SELECT FORM data" if call_count["n"] == 1 else "SELECT * FROM data LIMIT 1"
        return _mock_sql(sql)

    with patch("app.sql.sql_analyst.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.side_effect = fake_create
        result = answer_sql_question(df, "show me one row")

    assert result["success"] is True
    assert call_count["n"] == 2


def test_gives_up_cleanly_when_always_unsafe():
    df = load_csv(SAMPLE_CSV)
    with patch("app.sql.sql_analyst.Groq") as MockGroq:
        MockGroq.return_value.chat.completions.create.return_value = _mock_sql("DROP TABLE data")
        result = answer_sql_question(df, "delete everything", max_retries=2)

    assert result["success"] is False
    assert len(result["attempts"]) == 3  # 1 initial + 2 retries
    assert all(a["blocked_by_scanner"] for a in result["attempts"])


def test_readonly_connection_physically_rejects_writes():
    # No Groq/scanner involved at all -- proves the DB-level guarantee
    # independent of anything upstream.
    df = pd.DataFrame({"a": [1, 2, 3]})
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    conn = sqlite3.connect(db_path)
    df.to_sql("data", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()

    result = _run_readonly_query(db_path, "UPDATE data SET a = 0")
    assert result["success"] is False
    assert "readonly" in result["error"].lower()

    # And confirm the data genuinely wasn't touched, via a fresh
    # read-write connection.
    verify_conn = sqlite3.connect(db_path)
    remaining = verify_conn.execute("SELECT a FROM data").fetchall()
    verify_conn.close()
    assert remaining == [(1,), (2,), (3,)]

    import os
    os.remove(db_path)
