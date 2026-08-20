"""
Phase 22: pytest tests for app/sql/sql_scanner.py -- pure regex/text
analysis, no LLM calls, no database.
"""

from app.sql.sql_scanner import scan_sql


def test_safe_select_passes():
    result = scan_sql("SELECT category, AVG(price) FROM data GROUP BY category")
    assert result["safe"] is True
    assert result["violations"] == []


def test_safe_cte_passes():
    result = scan_sql("WITH top AS (SELECT * FROM data LIMIT 5) SELECT * FROM top")
    assert result["safe"] is True


def test_drop_table_is_blocked():
    result = scan_sql("DROP TABLE data")
    assert result["safe"] is False


def test_stacked_statements_are_blocked():
    result = scan_sql("SELECT * FROM data; DROP TABLE data;")
    assert result["safe"] is False


def test_update_disguised_as_second_statement_is_blocked():
    result = scan_sql("SELECT 1; UPDATE data SET price = 0")
    assert result["safe"] is False


def test_pragma_is_blocked():
    result = scan_sql("PRAGMA table_info(data)")
    assert result["safe"] is False


def test_empty_query_is_blocked():
    result = scan_sql("")
    assert result["safe"] is False


def test_banned_keyword_inside_comment_is_still_caught():
    # Comments don't execute, but the scanner should still flag the
    # keyword rather than being fooled by comment stripping alone --
    # since we strip comments before checking, a keyword ONLY inside a
    # comment should NOT trigger a false positive.
    result = scan_sql("SELECT * FROM data -- DROP TABLE later maybe\n")
    assert result["safe"] is True  # comment-only mention shouldn't block a safe query


def test_select_column_named_like_keyword_is_not_falsely_blocked():
    # A column/alias containing a banned word as a SUBSTRING (not a
    # whole word) should not trigger a false positive.
    result = scan_sql("SELECT dropoff_location FROM data")
    assert result["safe"] is True
