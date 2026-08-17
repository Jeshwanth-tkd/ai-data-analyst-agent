"""
Phase 3: LLM connection.

This module turns a CSV profile (from Phase 2) into a request to Groq's
LLM API, and gets back Python analysis code as a string. It does NOT run
that code — that's Phase 4's job. Keeping "ask the LLM for code" and
"run the code" in separate modules is the safety boundary described in
the README.
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

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """You are an expert data analyst who writes Python code to explore datasets.

You will be given a JSON profile describing a pandas DataFrame that has already been loaded into a variable called `df`. The profile includes the DataFrame's shape, column names and data types, null counts, unique-value counts, and a few real sample rows.

Your job: write a short Python script that performs useful exploratory analysis on `df` and prints the results. Assume `df` already exists in the environment your code will run in — do NOT write code to load a CSV yourself.

Rules you must follow exactly:
- Only use pandas, which is already imported as `pd`. Do not import or use any other library.
- Your code must not crash if a column contains missing (NaN) values.
- Print your findings using print(...) statements with clear, human-readable labels.
- Respond with ONLY a single fenced Python code block, like this:
```python
# your code here
```
Do not include any explanation, greeting, or commentary outside that code block.
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


def _build_initial_message(profile: dict) -> str:
    return (
        "Here is the profile of the dataset (already loaded as `df`):\n\n"
        f"{json.dumps(profile, indent=2, default=str)}"
    )


def _build_fix_message(profile: dict, previous_code: str, error_message: str) -> str:
    return (
        "The Python code below was written to analyze the dataset profile shown "
        "further down, but it failed when it was actually run. Fix the code so it "
        "runs successfully, while still following all of your original rules.\n\n"
        f"Code that failed:\n```python\n{previous_code}\n```\n\n"
        f"Error message it produced:\n{error_message}\n\n"
        f"Dataset profile (already loaded as `df`):\n"
        f"{json.dumps(profile, indent=2, default=str)}\n\n"
        "Respond with ONLY the corrected, fenced Python code block."
    )


def generate_analysis_code(
    profile: dict,
    previous_code: str = None,
    error_message: str = None,
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
    """
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    if previous_code and error_message:
        user_message = _build_fix_message(profile, previous_code, error_message)
    else:
        user_message = _build_initial_message(profile)

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
