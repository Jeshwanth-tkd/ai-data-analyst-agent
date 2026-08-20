"""
Phase 14: Validation layer.

Closes the gap ARCHITECTURE_BEFORE.md flagged: "no validation layer
between 'code ran successfully' and 'the result is reported as
success.'" run_code()'s success flag only means "the subprocess exited
with code 0" -- it says nothing about whether the code actually produced
anything useful. This module adds that missing check, run after
execution already reports success but before that success is trusted.
"""

import glob
import os

OUTPUTS_DIR = "outputs"
INSIGHT_MARKER = "INSIGHT: "
PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"


def _has_at_least_one_insight(stdout: str) -> bool:
    return any(line.strip().startswith(INSIGHT_MARKER) for line in stdout.splitlines())


def _find_corrupt_chart_files(outputs_dir: str = OUTPUTS_DIR) -> list:
    """
    A chart file existing on disk isn't proof it's a real image -- a
    crash partway through plt.savefig(), or a bug that wrote garbage to
    a .png-named file, would both look like "a file is there" without
    being a usable image. Check the real PNG magic bytes instead of
    trusting the file extension.
    """
    corrupt = []
    for path in glob.glob(os.path.join(outputs_dir, "chart_*.png")):
        try:
            with open(path, "rb") as f:
                header = f.read(len(PNG_MAGIC_BYTES))
            if header != PNG_MAGIC_BYTES or os.path.getsize(path) == 0:
                corrupt.append(path)
        except OSError:
            corrupt.append(path)
    return corrupt


def validate_result(stdout: str, outputs_dir: str = OUTPUTS_DIR) -> dict:
    """
    Run after execution already reported "success". Checks whether that
    success is actually trustworthy:
      1. At least one real "INSIGHT: " line was printed.
      2. Any chart files that exist are genuine, non-empty PNGs.

    Returns {"valid": bool, "issues": [str, ...]}.
    """
    issues = []

    if not _has_at_least_one_insight(stdout):
        issues.append(
            "The code ran without crashing but printed no lines starting with "
            "'INSIGHT: ' -- an analysis that produces zero findings isn't useful "
            "to the user, even though the code itself didn't error."
        )

    for path in _find_corrupt_chart_files(outputs_dir):
        issues.append(
            f"'{path}' exists but is not a valid, complete PNG image (it may be "
            "empty or the save was interrupted)."
        )

    return {"valid": len(issues) == 0, "issues": issues}


def format_issues(issues: list) -> str:
    header = (
        "The code ran without raising an error, but the result failed a "
        "post-run validation check:"
    )
    bullets = "\n".join(f"- {i}" for i in issues)
    footer = (
        "Fix the code so it produces at least one genuine INSIGHT: line and, "
        "if it saves a chart, a complete valid image."
    )
    return f"{header}\n{bullets}\n\n{footer}"


# Demo block: python -m app.validation.result_validator
if __name__ == "__main__":
    print("No insights:", validate_result("just some debug text\n"))
    print("Has insight:", validate_result("INSIGHT: something real\n"))
