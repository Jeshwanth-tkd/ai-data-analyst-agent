"""
Phase 22: SQL analyst.

An alternate "front door" onto the same uploaded dataset, alongside the
pandas-code-writing agent (Phase 4) and the NL chat agent (Phase 19).
Some questions are just more natural to answer in SQL than in pandas,
and -- more interestingly -- SQL gives us a COMPLETELY DIFFERENT, and
arguably stronger, safety model than Python code execution does.

The Python path (Phase 4/13/14) has to defend against a Turing-complete
language: an AST scanner blocklists dangerous patterns, but "can this
code do something bad" is fundamentally open-ended. SQL SELECT
statements are much more constrained by nature, and -- critically --
SQLite lets us open a genuinely READ-ONLY connection. That means safety
here doesn't rely SOLELY on the sql_scanner.py blocklist (Phase 13-style
defense in depth): even a query that somehow slipped past the scanner
physically cannot mutate the database, because the connection used to
run it doesn't have write permission at the OS/SQLite level. That's a
strictly stronger guarantee than anything blocklist-based code scanning
alone can offer, and worth being able to explain in an interview as a
real security tradeoff between the two designs.
"""

import os
import re
import sqlite3
import tempfile

import pandas as pd
from dotenv import load_dotenv
from groq import Groq

from app.sql.sql_scanner import format_sql_violations, scan_sql

load_dotenv()

MODEL = "openai/gpt-oss-120b"
TABLE_NAME = "data"
MAX_RETRIES = 3

SQL_SYSTEM_PROMPT = """You are a SQL analyst. You will be given the schema of a single SQLite table called `data`, and a natural language question. Write ONE SQLite SELECT query that answers it.

Rules you must follow exactly:
- Only a single SELECT statement (a WITH/CTE followed by a SELECT is fine). No other statement type, and no multiple statements separated by semicolons.
- Only query the `data` table -- it's the only table that exists.
- Use standard SQLite syntax and functions.
- Respond with ONLY a single fenced sql code block, like this:
```sql
SELECT ...
```
Do not include any explanation, greeting, or commentary outside that code block.
"""


def _extract_sql(raw_response: str) -> str:
    match = re.search(r"```(?:sql)?\s*\n(.*?)```", raw_response, re.DOTALL)
    return match.group(1).strip() if match else raw_response.strip()


def _schema_description(df: pd.DataFrame) -> str:
    columns = [f"{col} ({df[col].dtype})" for col in df.columns]
    return f"Table `{TABLE_NAME}` columns: " + ", ".join(columns)


def _generate_sql(
    client: Groq,
    schema: str,
    question: str,
    previous_sql: str = None,
    error_message: str = None,
) -> str:
    if previous_sql and error_message:
        user_message = (
            "The SQL query below was written to answer the question shown further "
            "down, but it failed. Fix it, following all your original rules.\n\n"
            f"Query that failed:\n```sql\n{previous_sql}\n```\n\n"
            f"Error:\n{error_message}\n\n"
            f"{schema}\n\nQuestion: {question}\n\n"
            "Respond with ONLY the corrected, fenced SQL code block."
        )
    else:
        user_message = f"{schema}\n\nQuestion: {question}"

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SQL_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    return _extract_sql(response.choices[0].message.content)


def _run_readonly_query(db_path: str, sql: str) -> dict:
    """
    Execute `sql` against `db_path` using a connection opened in SQLite's
    own read-only URI mode -- a real OS-level guarantee, not just a
    convention. Any attempted write raises sqlite3.OperationalError
    ("attempt to write a readonly database"), which is caught and
    reported like any other query error.
    """
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        cursor = conn.execute(sql)
        columns = [description[0] for description in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return {"success": True, "columns": columns, "rows": rows, "error": None}
    except sqlite3.Error as e:
        return {"success": False, "columns": [], "rows": [], "error": str(e)}
    finally:
        conn.close()


def answer_sql_question(df: pd.DataFrame, question: str, max_retries: int = MAX_RETRIES) -> dict:
    """
    Build a temporary read-only-queryable SQLite database from `df`,
    ask the LLM for a SELECT query answering `question`, scan it (Phase
    13-style AST scanning, but for SQL), execute it through a genuinely
    read-only connection, and self-correct on failure (bad SQL syntax,
    unsafe query, or a real SQLite error) up to `max_retries` times --
    same "generate, check, run, retry" shape as the Python agent loop,
    with a lighter-weight scan/execute pair suited to SQL instead of
    reusing code_executor.py's subprocess machinery, which doesn't apply
    here (there's no Python process to sandbox).

    Never raises -- returns a clean result dict no matter what happens,
    same convention as analyze_csv_file() and answer_data_question().
    """
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    schema = _schema_description(df)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        # Build the table using a normal read-write connection, then
        # never touch this connection again -- all actual query
        # execution below goes through a SEPARATE read-only connection.
        build_conn = sqlite3.connect(db_path)
        df.to_sql(TABLE_NAME, build_conn, if_exists="replace", index=False)
        build_conn.commit()
        build_conn.close()

        sql = None
        error_message = None
        attempts = []

        for attempt_number in range(1, max_retries + 2):
            sql = _generate_sql(client, schema, question, previous_sql=sql, error_message=error_message)

            scan_result = scan_sql(sql)
            if not scan_result["safe"]:
                error_message = format_sql_violations(scan_result["violations"])
                attempts.append({"attempt": attempt_number, "sql": sql, "success": False, "blocked_by_scanner": True})
                continue

            query_result = _run_readonly_query(db_path, sql)
            attempts.append({"attempt": attempt_number, "sql": sql, "success": query_result["success"], "blocked_by_scanner": False})

            if query_result["success"]:
                return {
                    "success": True,
                    "sql": sql,
                    "columns": query_result["columns"],
                    "rows": query_result["rows"],
                    "error": None,
                    "attempts": attempts,
                }
            error_message = query_result["error"]

        return {"success": False, "sql": sql, "columns": [], "rows": [], "error": error_message, "attempts": attempts}
    except Exception as e:
        return {"success": False, "sql": None, "columns": [], "rows": [], "error": f"Unexpected error: {e}", "attempts": []}
    finally:
        os.remove(db_path)


# Demo block: python -m app.sql.sql_analyst "What is the average price by category?"
if __name__ == "__main__":
    import sys

    from app.ingestion.csv_profiler import load_csv

    csv_path = os.path.join("data", "samples", "sample_sales.csv")
    question = sys.argv[1] if len(sys.argv) > 1 else "What is the average price by category?"

    dataframe = load_csv(csv_path)
    print(f"Q: {question}")
    result = answer_sql_question(dataframe, question)
    if result["success"]:
        print(f"SQL: {result['sql']}")
        print(f"Columns: {result['columns']}")
        for row in result["rows"]:
            print(f"  {row}")
    else:
        print(f"Failed: {result['error']}")
