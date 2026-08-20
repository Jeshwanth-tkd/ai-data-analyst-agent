"""
Phase 3: LLM connection.

This module turns a CSV profile (from Phase 2) into a request to Groq's
LLM API, and gets back Python analysis code as a string. It does NOT run
that code — that's Phase 4's job. Keeping "ask the LLM for code" and
"run the code" in separate modules is the safety boundary described in
the README.

Phase 16 addition: generate_analysis_code() can now also be given a
Phase 12 data-quality report and a Phase 16 baseline EDA report. Both
are optional (default None) so every existing call site keeps working
unchanged -- when present, they're folded into the prompt so the LLM
can skip known-junk columns (constant/ID-like), stay aware of type
mismatches and outliers already found, and build on top of baseline
stats/correlations instead of re-deriving them from scratch.
"""

import os
import re
import json

from dotenv import load_dotenv
from groq import Groq

# Reads your local .env file and loads its values (like GROQ_API_KEY)
# into the environment, so os.environ.get() below can find them.
# This only reads from your own machine's .env file — nothing here
# sends your key anywhere by itself.
load_dotenv()

# llama-3.3-70b-versatile was deprecated by Groq on 2026-08-16 — this is
# a live example of why depending on a third-party API means models can
# be retired without warning. openai/gpt-oss-120b is Groq's current
# recommended replacement (also noted for strong coding performance).
MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are an expert data analyst who writes Python code to explore datasets.

You will be given a JSON profile describing a pandas DataFrame that has already been loaded into a variable called `df`. The profile includes the DataFrame's shape, column names and data types, null counts, unique-value counts, and a few real sample rows.

Your job: write a short Python script that performs useful exploratory analysis on `df`, prints its findings, and optionally saves 1-3 charts as image files. Assume `df` already exists in the environment your code will run in — do NOT write code to load a CSV yourself.

Rules you must follow exactly:
- Only use pandas (imported as `pd`) and matplotlib.pyplot (imported as `plt`). Do not import or use any other library.
- Your code must not crash if a column contains missing (NaN) values.
- Every insight you want reported MUST be printed as its own print() statement, and the text MUST start with the literal marker "INSIGHT: ", for example:
  print("INSIGHT: Electronics has the highest average price at $34.20")
  Do not print anything else that starts with "INSIGHT: " — only genuine findings.
- If you create a chart, save it with plt.savefig("outputs/chart_1.png") for the first chart, "outputs/chart_2.png" for the second, and so on. Do not call plt.show().
- If a chart's x-axis has more than ~6 labels (e.g. many dates, or many category names), rotate them so they don't overlap: plt.xticks(rotation=45, ha="right").
- Always call plt.tight_layout() right before plt.savefig(...) so axis labels and titles never get cut off or run into each other.
- Respond with ONLY a single fenced Python code block, like this:
```python
# your code here
```
Do not include any explanation, greeting, or commentary outside that code block.

You may also be given a data quality report and a baseline EDA summary alongside the profile. When present:
- Do NOT waste an insight restating a number that's already in the baseline summary verbatim -- build on it (e.g. explain why a correlation matters, compare a category's mean against the overall mean) instead of repeating it.
- Avoid grouping or charting by any column listed as constant or ID-like in the quality report's structural_flags -- those columns carry no useful signal.
- If a column is flagged with likely type issues or a high outlier fraction, account for that (e.g. don't just average a column that's mostly text-as-numbers without acknowledging it, or consider whether outliers are skewing a mean you report).
"""


def _extract_code(raw_response: str) -> str:
    """
    Pull the Python code out of a fenced ```python ... ``` block in the
    model's raw text reply. If the model didn't follow instructions and
    skipped the fences, we fall back to returning the whole reply as-is —
    Phase 6 will make this extraction much more defensive.
    """
    match = re.search(r"```(?:python)?\s*\n(.*?)```", raw_response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_response.strip()


def _build_context_blocks(quality_report: dict = None, eda_summary: dict = None) -> str:
    """
    Shared helper: render the optional Phase 12 / Phase 16 reports as
    extra JSON blocks. Returns "" (nothing appended) when both are
    None, so a caller that doesn't pass them gets the exact same
    message shape as before Phase 16 -- fully backward compatible.
    """
    blocks = ""
    if quality_report is not None:
        blocks += (
            "\n\nData quality report for this dataset:\n"
            f"{json.dumps(quality_report, indent=2, default=str)}"
        )
    if eda_summary is not None:
        blocks += (
            "\n\nBaseline EDA summary already computed for this dataset "
            "(build on this, don't just repeat it):\n"
            f"{json.dumps(eda_summary, indent=2, default=str)}"
        )
    return blocks


def _build_initial_message(profile: dict, quality_report: dict = None, eda_summary: dict = None) -> str:
    return (
        "Here is the profile of the dataset (already loaded as `df`):\n\n"
        f"{json.dumps(profile, indent=2, default=str)}"
        f"{_build_context_blocks(quality_report, eda_summary)}"
    )


def _build_fix_message(
    profile: dict,
    previous_code: str,
    error_message: str,
    quality_report: dict = None,
    eda_summary: dict = None,
) -> str:
    return (
        "The Python code below was written to analyze the dataset profile shown "
        "further down, but it failed when it was actually run. Fix the code so it "
        "runs successfully, while still following all of your original rules.\n\n"
        f"Code that failed:\n```python\n{previous_code}\n```\n\n"
        f"Error message it produced:\n{error_message}\n\n"
        f"Dataset profile (already loaded as `df`):\n"
        f"{json.dumps(profile, indent=2, default=str)}"
        f"{_build_context_blocks(quality_report, eda_summary)}\n\n"
        "Respond with ONLY the corrected, fenced Python code block."
    )


def generate_analysis_code(
    profile: dict,
    previous_code: str = None,
    error_message: str = None,
    quality_report: dict = None,
    eda_summary: dict = None,
) -> str:
    """
    Send a dataset profile to the LLM and return the Python analysis
    code it writes back, as a plain string (not yet executed).

    Normally called with just `profile` for a fresh attempt. When called
    with `previous_code` and `error_message` set (by the self-correction
    loop in Phase 4's executor), it instead asks the model to fix code
    that already failed — this is the same function doing double duty
    for both "write code" and "fix code", since the API call itself is
    identical; only the message we send differs.

    `quality_report` (Phase 12) and `eda_summary` (Phase 16) are both
    optional and, when given, are included on EVERY call — initial
    attempt and every fix attempt alike — so the model stays aware of
    known data issues and baseline stats throughout the whole retry loop,
    not just on the first try.
    """
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    if previous_code and error_message:
        user_message = _build_fix_message(
            profile, previous_code, error_message, quality_report, eda_summary
        )
    else:
        user_message = _build_initial_message(profile, quality_report, eda_summary)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw_reply = response.choices[0].message.content
    return _extract_code(raw_reply)


# Demo block: chains Phase 2's profiler straight into Phase 3's LLM call,
# so you can see the two phases connect end to end.
if __name__ == "__main__":
    from app.ingestion.csv_profiler import profile_csv

    sample_path = os.path.join("data", "samples", "sample_sales.csv")
    profile = profile_csv(sample_path)

    print("Asking the LLM to write analysis code for sample_sales.csv...\n")
    code = generate_analysis_code(profile)

    print("----- Generated code -----")
    print(code)
    print("---------------------------")
