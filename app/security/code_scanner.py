"""
Phase 13: AST-based Code Safety Scanner.

Before any LLM-generated code reaches the subprocess in
app/executor/code_executor.py, this module parses it into an AST
(Abstract Syntax Tree) and inspects that tree *structurally* for
known-dangerous patterns -- disallowed imports, disallowed builtin calls,
and the classic Python sandbox-escape gadget attributes -- instead of just
searching the raw code text for banned words.

This is a defense-in-depth layer, not a replacement for the subprocess
isolation Phase 4 already provides (see ARCHITECTURE_BEFORE.md /
PROJECT_AUDIT.md for the full reasoning on why that gap mattered). Nothing
in this file ever executes the code it's given -- it only ever reads it.
"""

import ast

# Modules with zero legitimate use in "analyze a DataFrame, save a chart"
# code. llm_client.py's system prompt already *asks* the LLM to only use
# pandas and matplotlib.pyplot -- this list is what actually *enforces*
# that, instead of just requesting it and hoping.
BANNED_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "requests",
    "urllib", "urllib2", "urllib3", "http", "ftplib", "smtplib",
    "telnetlib", "pickle", "marshal", "ctypes", "importlib",
    "multiprocessing", "threading", "signal", "resource", "pty", "code",
}

# Builtins that either run arbitrary code (eval/exec/compile/__import__),
# touch the filesystem directly (open), or reach outside the intended
# scope (globals/locals/vars, dynamic attribute access via
# getattr/setattr/delattr). Note this only ever matches a BARE call to
# these names -- df.eval(...) and df.query(...) are legitimate pandas
# methods that happen to share a name with the dangerous builtin, and are
# NOT flagged, because they show up in the AST as attribute calls
# (df.eval), not name calls (eval) -- see the isinstance check below.
BANNED_CALL_NAMES = {
    "eval", "exec", "compile", "__import__", "open", "input",
    "globals", "locals", "vars", "breakpoint", "exit", "quit",
    "getattr", "setattr", "delattr",
}

# Attribute names used by the classic Python "sandbox escape" gadget
# chain -- e.g. ().__class__.__bases__[0].__subclasses__() -- which can
# reach os/subprocess-equivalent functionality WITHOUT ever writing the
# literal text "import os" anywhere, so the import check above wouldn't
# catch it on its own. Flagging these attribute names directly, wherever
# they appear, closes that specific well-known bypass.
DANGEROUS_ATTRIBUTES = {
    "__globals__", "__builtins__", "__subclasses__", "__bases__",
    "__base__", "__mro__", "__import__", "__loader__", "__code__",
}


def scan_code(code: str) -> dict:
    """
    Parse `code` and check it for disallowed imports, disallowed builtin
    calls, and sandbox-escape gadget attributes.

    Returns {"safe": bool, "violations": [str, ...]} -- an empty
    violations list means the code passed every check. A SyntaxError
    while parsing is also reported as unsafe (we can't verify code we
    can't even parse), which has a nice side effect: it catches broken
    code before wasting time spinning up a subprocess for it.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"safe": False, "violations": [f"Code failed to parse as valid Python: {e}"]}

    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level_module = alias.name.split(".")[0]
                if top_level_module in BANNED_MODULES:
                    violations.append(f"Disallowed import: '{alias.name}' (line {node.lineno})")

        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                # A relative import (e.g. "from . import something") --
                # meaningless in a standalone script anyway, and not
                # something legitimate analysis code has any reason to do.
                violations.append(f"Disallowed relative import (line {node.lineno})")
            else:
                top_level_module = node.module.split(".")[0]
                if top_level_module in BANNED_MODULES:
                    violations.append(
                        f"Disallowed import: 'from {node.module} import ...' (line {node.lineno})"
                    )

        elif isinstance(node, ast.Call):
            # Only matches a bare call like eval(...) -- NOT an attribute
            # call like df.eval(...), which is a different AST node shape
            # (ast.Attribute, not ast.Name) and is legitimate pandas usage.
            if isinstance(node.func, ast.Name) and node.func.id in BANNED_CALL_NAMES:
                violations.append(f"Disallowed function call: '{node.func.id}(...)' (line {node.lineno})")

        elif isinstance(node, ast.Attribute):
            if node.attr in DANGEROUS_ATTRIBUTES:
                violations.append(f"Disallowed attribute access: '.{node.attr}' (line {node.lineno})")

    return {"safe": len(violations) == 0, "violations": violations}


def format_violations(violations: list) -> str:
    """
    Turn a list of violation strings into one readable block of text,
    shaped so it can be fed straight back to the LLM as an "error
    message" through the exact same self-correction path
    code_executor.py already uses for real runtime errors.
    """
    header = (
        "The generated code was blocked by an automated safety check "
        "before it was run, for using disallowed operations:"
    )
    bullets = "\n".join(f"- {v}" for v in violations)
    footer = (
        "Rewrite the code using ONLY pandas (as `pd`) and matplotlib.pyplot "
        "(as `plt`) on the existing `df` variable, without any of the "
        "operations listed above."
    )
    return f"{header}\n{bullets}\n\n{footer}"


# Demo block, same convention as every other module in this project:
#   python -m app.security.code_scanner
if __name__ == "__main__":
    samples = {
        "safe pandas/matplotlib code": (
            "import pandas as pd\n"
            "print('INSIGHT:', df.describe())\n"
        ),
        "banned import": (
            "import os\n"
            "os.system('echo hi')\n"
        ),
        "banned bare eval": "eval('1 + 1')\n",
        "legit df.eval (should NOT be flagged)": "df.eval('a + b')\n",
        "classic sandbox-escape gadget": "().__class__.__bases__[0].__subclasses__()\n",
        "syntax error": "def broken(:\n",
    }

    for label, code in samples.items():
        result = scan_code(code)
        status = "SAFE" if result["safe"] else "BLOCKED"
        print(f"[{status}] {label}")
        for v in result["violations"]:
            print(f"    {v}")
