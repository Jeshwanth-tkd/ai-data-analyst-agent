"""
Phase 19: Natural language data chat.

Everything built through Phase 18 runs ONE analysis pass and shows the
result -- there's no way to ask a follow-up ("why did sales fall in
March?", "show the top 10 customers", "plot that") without re-uploading
and starting over. This module adds that: a conversational loop over the
SAME dataset, with the last few question/answer turns kept as context so
"plot that" can refer back to whatever "that" was.

Design choice worth calling out: this does NOT duplicate the scan → run
→ validate → retry engine from app/executor/code_executor.py. Phase 16's
code_generator injection point (added specifically for this) is reused
here -- a chat question just becomes a differently-prompted code
generator plugged into the exact same safety-checked execution loop the
main analysis path uses. Every chat answer goes through the Phase 13 AST
scanner and the Phase 14 validator exactly like a normal analysis run.
"""

import glob
import os
import re

from dotenv import load_dotenv
from groq import Groq

from app.executor.code_executor import run_with_self_correction

load_dotenv()

MODEL = "openai/gpt-oss-120b"
OUTPUTS_DIR = "outputs"
INSIGHT_MARKER = "INSIGHT: "
# Keep the prompt bounded -- only the last few turns are included, so a
# long chat session doesn't grow the request without limit.
MAX_HISTORY_TURNS = 5

CHAT_SYSTEM_PROMPT = """You are a data analyst answering a specific follow-up question about a dataset already loaded into a pandas DataFrame `df`.

You will be given the dataset's profile, optionally a data quality report and baseline EDA summary, the recent conversation history (previous questions and your previous answers), and the user's new question.

Your job: write a short Python script that answers the user's CURRENT question using `df`. Assume `df` already exists — do NOT load a CSV yourself.

Rules you must follow exactly:
- Only use pandas (imported as `pd`) and matplotlib.pyplot (imported as `plt`). Do not import or use any other library.
- Your code must not crash if a column contains missing (NaN) values.
- Print your answer as one or more print() statements, each starting with the literal marker "INSIGHT: ". This is your only way to communicate the answer back.
- If the question asks for or implies a chart ("plot that", "show me a graph of..."), save exactly one chart with plt.savefig("outputs/chart_1.png"). Otherwise, don't save a chart.
- If a previous question's code or answer is relevant to interpreting a vague follow-up (e.g. "plot that", "why?"), use the conversation history to figure out what "that" refers to.
- If you create a chart with more than ~6 x-axis labels, rotate them: plt.xticks(rotation=45, ha="right"). Always call plt.tight_layout() before plt.savefig(...).
- Respond with ONLY a single fenced Python code block, like this:
```python
# your code here
```
Do not include any explanation, greeting, or commentary outside that code block.
"""


def _extract_code(raw_response: str) -> str:
    match = re.search(r"```(?:python)?\s*\n(.*?)```", raw_response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_response.strip()


def _parse_insights(stdout: str) -> list:
    return [
        line.strip()[len(INSIGHT_MARKER):].strip()
        for line in stdout.splitlines()
        if line.strip().startswith(INSIGHT_MARKER)
    ]


def _clear_chat_chart(outputs_dir: str = OUTPUTS_DIR) -> None:
    for path in glob.glob(os.path.join(outputs_dir, "chart_*.png")):
        os.remove(path)


def _format_history(conversation_history: list) -> str:
    if not conversation_history:
        return "(no previous questions this session)"
    recent = conversation_history[-MAX_HISTORY_TURNS:]
    lines = []
    for turn in recent:
        lines.append(f"Q: {turn['question']}\nA: {turn['answer']}")
    return "\n\n".join(lines)


def _build_chat_generator(
    profile: dict,
    question: str,
    conversation_history: list,
    quality_report: dict = None,
    eda_summary: dict = None,
):
    """
    Builds a code_generator callable matching the (previous_code,
    error_message) -> code shape run_with_self_correction() expects --
    same injection pattern used to keep the scan/run/validate/retry
    engine shared between the main analysis path and this chat path.
    """
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    context_blocks = f"\n\nDataset profile:\n{profile}"
    if quality_report is not None:
        context_blocks += f"\n\nData quality report:\n{quality_report}"
    if eda_summary is not None:
        context_blocks += f"\n\nBaseline EDA summary:\n{eda_summary}"
    context_blocks += f"\n\nRecent conversation history:\n{_format_history(conversation_history)}"

    def generate(previous_code: str = None, error_message: str = None) -> str:
        if previous_code and error_message:
            user_message = (
                "The code below was written to answer the question shown further down, "
                "but it failed when run. Fix it, following all your original rules.\n\n"
                f"Code that failed:\n```python\n{previous_code}\n```\n\n"
                f"Error it produced:\n{error_message}"
                f"{context_blocks}\n\n"
                f"Question to answer: {question}\n\n"
                "Respond with ONLY the corrected, fenced Python code block."
            )
        else:
            user_message = f"{context_blocks}\n\nQuestion to answer: {question}"

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        return _extract_code(response.choices[0].message.content)

    return generate


def answer_data_question(
    profile: dict,
    csv_path: str,
    question: str,
    conversation_history: list = None,
    quality_report: dict = None,
    eda_summary: dict = None,
) -> dict:
    """
    Answer one natural-language question about the dataset, reusing the
    exact same scan → run → validate → retry loop the main analysis path
    uses (via code_executor's code_generator injection point). Returns
    {"success": bool, "answer": str, "chart": str or None, "error": str or None}.

    Never raises -- follows the same "never crash the caller" convention
    as analyze_csv_file().
    """
    conversation_history = conversation_history or []

    try:
        _clear_chat_chart()
        code_generator = _build_chat_generator(
            profile, question, conversation_history, quality_report, eda_summary
        )
        execution_result = run_with_self_correction(profile, csv_path, code_generator=code_generator)
    except Exception as e:
        return {"success": False, "answer": None, "chart": None, "error": f"Unexpected error: {e}"}

    if not execution_result["success"]:
        return {
            "success": False,
            "answer": None,
            "chart": None,
            "error": execution_result["attempts"][-1]["stderr"],
        }

    insights = _parse_insights(execution_result["output"])
    charts = sorted(glob.glob(os.path.join(OUTPUTS_DIR, "chart_*.png")))

    return {
        "success": True,
        "answer": " ".join(insights) if insights else "(the code ran but printed no answer)",
        "chart": charts[0] if charts else None,
        "error": None,
    }


# Demo block: python -m app.agent.chat_agent "What's the average price?"
if __name__ == "__main__":
    import sys

    from app.ingestion.csv_profiler import profile_csv

    csv_path = os.path.join("data", "samples", "sample_sales.csv")
    profile = profile_csv(csv_path)
    question = sys.argv[1] if len(sys.argv) > 1 else "What is the average price?"

    print(f"Q: {question}")
    result = answer_data_question(profile, csv_path, question)
    if result["success"]:
        print(f"A: {result['answer']}")
        if result["chart"]:
            print(f"Chart saved: {result['chart']}")
    else:
        print(f"Failed: {result['error']}")
