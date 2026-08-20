"""
Phase 15: pytest suite.

Tests for app/security/code_scanner.py -- pure AST parsing, no LLM calls.
"""

from app.security.code_scanner import scan_code


def test_safe_pandas_matplotlib_code_passes():
    code = (
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n"
        "print('INSIGHT: mean is', df['price'].mean())\n"
        "plt.figure()\n"
        "plt.savefig('outputs/chart_1.png')\n"
    )
    result = scan_code(code)
    assert result["safe"] is True
    assert result["violations"] == []


def test_banned_import_is_blocked():
    result = scan_code("import os\nos.system('echo hi')\n")
    assert result["safe"] is False
    assert any("os" in v for v in result["violations"])


def test_banned_import_from_is_blocked():
    result = scan_code("from subprocess import run\nrun(['echo', 'hi'])\n")
    assert result["safe"] is False


def test_bare_eval_is_blocked():
    result = scan_code("eval('1 + 1')\n")
    assert result["safe"] is False


def test_dataframe_eval_method_is_not_blocked():
    # df.eval(...) is a legitimate pandas method that happens to share a
    # name with the dangerous builtin -- it must NOT be flagged.
    result = scan_code("df.eval('a + b')\n")
    assert result["safe"] is True


def test_sandbox_escape_gadget_is_blocked():
    result = scan_code("().__class__.__bases__[0].__subclasses__()\n")
    assert result["safe"] is False
    assert len(result["violations"]) >= 1


def test_open_builtin_is_blocked():
    result = scan_code("f = open('/etc/passwd')\n")
    assert result["safe"] is False


def test_syntax_error_is_reported_as_unsafe():
    result = scan_code("def broken(:\n")
    assert result["safe"] is False
    assert "parse" in result["violations"][0].lower()
