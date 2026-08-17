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
"""

import os
import subprocess
import sys
import tempfile

from app.agent.llm_client import generate_analysis_code

MAX_RETRIES = 3
TIMEOUT_SECONDS = 15


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
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
        tmp.write(wrapper_script)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
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


def run_with_self_correction(
    profile: dict,
    csv_path: str,
    max_retries: int = MAX_RETRIES,
) -> dict:
    """
    The full agentic loop: ask the LLM for code, run it, and if it
    fails, feed the error back to the LLM and ask it to fix its own
    code — up to `max_retries` additional attempts after the first.

    Returns a dict describing the final outcome plus a full history of
    every attempt made, so we can show/debug the whole process later.
    """
    attempts = []
    code = generate_analysis_code(profile)

    for attempt_number in range(1, max_retries + 2):  # 1 initial + N fixes
        result = run_code(code, csv_path)
        attempts.append({
            "attempt": attempt_number,
            "code": code,
            "success": result["success"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
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
        code = generate_analysis_code(
            profile,
            previous_code=code,
            error_message=result["stderr"],
        )

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
