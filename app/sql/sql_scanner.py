"""
Phase 22: SQL safety scanner.

Same "defense in depth" philosophy as app/security/code_scanner.py
(Phase 13), applied to SQL instead of Python: before any LLM-generated
SQL touches a real database connection, check it structurally for
anything beyond a single read-only SELECT.

Honest limitation, stated up front (same spirit as Phase 13's own
docstring): this is regex/keyword-based, not a real SQL parser. A
determined adversary crafting SQL by hand could likely find a gap. That
is NOT this module's actual job, though -- the LLM is generating the
ENTIRE query itself from a trusted system prompt, not being fed
attacker-controlled text to splice into a query (the classic SQL
injection scenario this project is explicitly NOT defending against).
This scanner exists to catch the LLM writing something destructive by
mistake, and it's paired with a second, independent, non-bypassable
layer: sql_analyst.py executes every query through a genuinely
READ-ONLY database connection, so even a query that slipped past this
scanner cannot actually mutate anything.
"""

import re

BANNED_KEYWORDS = {
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "ATTACH", "DETACH",
    "PRAGMA", "CREATE", "REPLACE", "TRUNCATE", "VACUUM", "REINDEX",
    "GRANT", "REVOKE",
}


def _strip_sql_comments(sql: str) -> str:
    """Remove -- line comments and /* */ block comments before analysis."""
    sql = re.sub(r"--.*?(\n|$)", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


def scan_sql(sql: str) -> dict:
    """
    Check that `sql` is exactly one read-only SELECT (or a SELECT built
    on a CTE via WITH) statement, with none of the banned keywords
    appearing anywhere. Returns {"safe": bool, "violations": [str, ...]}.
    """
    violations = []
    cleaned = _strip_sql_comments(sql).strip()

    if not cleaned:
        return {"safe": False, "violations": ["Empty query."]}

    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    if len(statements) != 1:
        violations.append(
            f"Expected exactly one SQL statement, found {len(statements)} "
            "(statements separated by ';')."
        )

    first_word_match = re.match(r"^\s*(\w+)", cleaned, re.IGNORECASE)
    first_word = first_word_match.group(1).upper() if first_word_match else ""
    if first_word not in ("SELECT", "WITH"):
        violations.append(f"Query must start with SELECT or WITH, not '{first_word}'.")

    found_banned = set()
    for keyword in BANNED_KEYWORDS:
        if re.search(rf"\b{keyword}\b", cleaned, re.IGNORECASE):
            found_banned.add(keyword)
    if found_banned:
        violations.append(f"Disallowed keyword(s) found: {', '.join(sorted(found_banned))}")

    return {"safe": len(violations) == 0, "violations": violations}


def format_sql_violations(violations: list) -> str:
    header = "The generated SQL was blocked by an automated safety check:"
    bullets = "\n".join(f"- {v}" for v in violations)
    footer = "Rewrite it as a single, read-only SELECT statement (WITH/CTEs are fine)."
    return f"{header}\n{bullets}\n\n{footer}"


# Demo block: python -m app.sql.sql_scanner
if __name__ == "__main__":
    samples = {
        "safe select": "SELECT category, AVG(price) FROM data GROUP BY category",
        "safe cte": "WITH top AS (SELECT * FROM data LIMIT 5) SELECT * FROM top",
        "drop table": "DROP TABLE data",
        "stacked statements": "SELECT * FROM data; DROP TABLE data;",
        "update disguised": "SELECT 1; UPDATE data SET price = 0",
        "pragma": "PRAGMA table_info(data)",
    }
    for label, sql in samples.items():
        result = scan_sql(sql)
        print(f"[{'SAFE' if result['safe'] else 'BLOCKED'}] {label}: {result['violations']}")
