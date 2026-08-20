"""
Phase 4: Code execution loop — the agentic core of this project.

This module runs LLM-generated Python code safely and, if it fails,
loops back to the LLM with the error message so it can fix its own
code and try again. This is the "act -> observe -> self-correct" cycle
that makes this project an agent rather than a single API call.

Design decisions made here (confirmed with the developer before building):
- Execution happens in a separate OS subprocess (not exec() in this same
  process). A crash in generated code only kills that subprocess; a hang
  gets force-killed after a timeout. This uses only Python's standard
  library — no extra paid tools.
- The self-correction loop allows up to 3 retries (4 attempts total)
  before giving up and reporting failure honestly.

Phase 13 addition: every piece of generated code is passed through
app/security/code_scanner.py's scan_code() BEFORE it's ever handed to
run_code(). If the scanner flags it, the code is never executed at all —
instead, the violation list is fed back into the exact same
self-correction path used for real runtime errors (confirmed with the
developer: unsafe code costs a retry attempt, exactly like a crash would,
rather than immediately failing the whole analysis).

Phase 14 addition: a subprocess exit code of 0 only means "didn't crash"
— it says nothing about whether the code actually produced anything
useful. app/validation/result_validator.py's validate_result() runs
right after a successful execution and checks for at least one real
INSIGHT line and any chart files being genuine, non-corrupt PNGs. A
failed validation is fed back into the same retry path as a scanner
block or a real crash, and outputs/ is cleared before every individual
attempt (not just once per whole analysis) so validation is always
checking files this specific attempt actually produced.
"""

import glob
import os
import subprocess
import sys
import tempfile

from app.agent.llm_client import generate_analysis_code
from app.security.code_scanner import format_violations, scan_code
from app.validation.result_validator import format_issues, validate_result

MAX_RETRIES = 3
TIMEOUT_SECONDS = 15
OUTPUTS_DIR = "outputs"


def _clear_chart_files(outputs_dir: str = OUTPUTS_DIR) -> None:
    """
    Delete any chart_*.png left over from a previous attempt, so a stale
    file from an earlier (possibly failed) attempt in this same retry
    loop can't get credited to a later attempt during validation.
    """
    for path in glob.glob(os.path.join(outputs_dir, "chart_*.png")):
        os.remove(path)


def run_code(code: str, csv_path: str, timeout: int = TIMEOUT_SECONDS) -> dict:
    """
    Execute a single piece of generated analysis code in an isolated
    subprocess and report what happened.

    Important detail: a subprocess has its own separate memory — nothing
    from our main program (like an already-loaded DataFrame) is shared
    with it automatically. So we build a small wrapper script that loads
    the CSV itself, then appends the generated code underneath it. That
    wrapper is what actually gets run, not the generated code alone.

    Returns a dict: {"success": bool, "stdout": str, "stderr": str}
    """
    wrapper_script = (
        # Force matplotlib into non-interactive, file-only mode BEFORE
        # anything imports pyplot. Without this, a plt.show() call (or
        # even certain backends by default) can try to open a GUI
        # window with no display attached and hang until our timeout
        # kills it. We don't rely on the LLM remembering not to call
        # plt.show() — we make it a no-op ourselves, regardless.
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "import pandas as pd\n"
        f"df = pd.read_csv(r{csv_path!r})\n\n"
        f"{code}\n"
    )

    # delete=False because on Windows an open temp file can't be
    # re-opened by another process (our subprocess) while we're still
    # holding it open — so we close it first, then clean it up ourselves
    # in the `finally` block below.
    #
    # encoding="utf-8" is explicit on purpose: Windows' default text
    # encoding is an older, more limited encoding (often called
    # "charmap"), which errors on many valid Unicode characters the LLM
    # can legitimately produce (typographic dashes, curly quotes, etc.).
    # Linux/Mac default to UTF-8 already, which is why this bug wouldn't
    # show up in testing done there — always pin the encoding explicitly
    # rather than relying on a platform's default.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(wrapper_script)
        tmp_path = tmp.name

    # Also force the CHILD process's own stdout/stderr into UTF-8 mode.
    # Without this, the subprocess itself could crash trying to print()
    # a special character using Windows' default console encoding —
    # a separate instance of the same root problem as the temp file fix
    # above, just happening inside the child instead of in our code.
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            env=child_env,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": (
                f"Code did not finish within {timeout} seconds "
                "(likely an infinite loop or an extremely slow operation)."
            ),
        }
    finally:
        os.remove(tmp_path)


def _default_code_generator(profile, quality_report, eda_summary, plan):
    """
    Builds the code_generator callable used when the caller doesn't
    supply their own -- captures profile/quality_report/eda_summary/plan
    once, and returns a function matching the (previous_code,
    error_message) -> code shape every code_generator must have.
    """
    def generate(previous_code: str = None, error_message: str = None) -> str:
        return generate_analysis_code(
            profile,
            previous_code=previous_code,
            error_message=error_message,
            quality_report=quality_report,
            eda_summary=eda_summary,
            plan=plan,
        )
    return generate


def run_with_self_correction(
    profile: dict,
    csv_path: str,
    max_retries: int = MAX_RETRIES,
    quality_report: dict = None,
    eda_summary: dict = None,
    plan=None,
    code_generator=None,
) -> dict:
    """
    The full agentic loop: ask for code, run it, and if it fails, feed
    the error back and ask for a fix — up to `max_retries` additional
    attempts after the first.

    Phase 16: `quality_report` and `eda_summary` (both optional) are
    passed straight through to every code-generation call — the first
    attempt and every retry — so the LLM has that context for the whole
    loop, not just the initial attempt. Phase 17 adds `plan` alongside
    them the same way.

    Phase 19: `code_generator` is an optional injection point. By
    default this loop builds one from generate_analysis_code() (the
    "explore this dataset" agent) using profile/quality_report/
    eda_summary/plan above -- but a caller can pass its own callable
    with signature (previous_code, error_message) -> code instead, to
    reuse this exact same scan → run → validate → retry engine for a
    DIFFERENT code-writing task (e.g. the Phase 19 data-chat agent
    answering one specific question) without duplicating any of the
    safety/retry logic below.

    Returns a dict describing the final outcome plus a full history of
    every attempt made, so we can show/debug the whole process later.
    """
    if code_generator is None:
        code_generator = _default_code_generator(profile, quality_report, eda_summary, plan)

    attempts = []
    code = code_generator()

    for attempt_number in range(1, max_retries + 2):  # 1 initial + N fixes
        # Phase 13: check BEFORE running, not instead of running. A
        # scanner flag skips run_code() entirely -- the code never
        # touches a subprocess -- but is otherwise treated exactly like
        # a runtime failure below, so the rest of the loop doesn't need
        # to know or care which kind of failure this was.
        scan_result = scan_code(code)
        blocked_by_scanner = not scan_result["safe"]

        failed_validation = False

        if blocked_by_scanner:
            result = {
                "success": False,
                "stdout": "",
                "stderr": format_violations(scan_result["violations"]),
            }
        else:
            _clear_chart_files()
            result = run_code(code, csv_path)

            # Phase 14: a clean exit code isn't proof the result is
            # actually usable -- check that before trusting "success".
            if result["success"]:
                validation_result = validate_result(result["stdout"])
                if not validation_result["valid"]:
                    failed_validation = True
                    result = {
                        "success": False,
                        "stdout": result["stdout"],
                        "stderr": format_issues(validation_result["issues"]),
                    }

        attempts.append({
            "attempt": attempt_number,
            "code": code,
            "success": result["success"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "blocked_by_scanner": blocked_by_scanner,
            "failed_validation": failed_validation,
        })

        if result["success"]:
            return {
                "success": True,
                "final_code": code,
                "output": result["stdout"],
                "attempts": attempts,
            }

        was_last_attempt = attempt_number == max_retries + 1
        if was_last_attempt:
            break

        print(f"Attempt {attempt_number} failed — asking the LLM to fix it...")
        code = code_generator(previous_code=code, error_message=result["stderr"])

    return {
        "success": False,
        "final_code": code,
        "output": None,
        "attempts": attempts,
    }


# Demo block: chains Phases 2, 3, and 4 together end to end — profile a
# CSV, generate code for it, run that code, and self-correct if needed.
if __name__ == "__main__":
    from app.ingestion.csv_profiler import profile_csv

    sample_path = os.path.join("data", "samples", "sample_sales.csv")
    profile = profile_csv(sample_path)

    print("Running the full agent loop on sample_sales.csv...\n")
    result = run_with_self_correction(profile, sample_path)

    print(f"Total attempts: {len(result['attempts'])}")
    for a in result["attempts"]:
        status = "SUCCESS" if a["success"] else "FAILED"
        print(f"  Attempt {a['attempt']}: {status}")

    if result["success"]:
        print("\n----- Final output -----")
        print(result["output"])
    else:
        print("\nAgent gave up after all retries. Last error:")
        print(result["attempts"][-1]["stderr"])
