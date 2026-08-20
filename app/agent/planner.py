"""
Phase 17: Multi-step planning agent.

Up through Phase 16, the agent went straight from "here's a dataset
profile" to "write me Python code that analyzes it" — a single LLM call
deciding both WHAT to look at and HOW to code it at the same time. This
module splits that into two explicit steps: first decide on a short plan
(a goal + a handful of concrete analysis steps), THEN write code that
follows it. This is the same "plan → act" split real agentic systems use
instead of a single opaque generate-and-hope call, and it also gives the
UI something honest to show the user about what the agent intends to do
before it does it.

Structured output: the plan is requested as JSON (Groq's response_format
json_object mode) and validated into a Pydantic model, so a malformed
response is caught immediately rather than silently producing garbage
that only breaks something three steps later.
"""

import json
import os

from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel, ValidationError

load_dotenv()

MODEL = "openai/gpt-oss-120b"

PLANNER_SYSTEM_PROMPT = """You are a planning agent for an automated data analysis pipeline.

You will be given a JSON profile of a dataset (and, when available, a data quality report and a baseline EDA summary). Your job is NOT to write code or perform the analysis yourself -- it is to decide what a good analyst would look at.

Respond with ONLY a JSON object of this exact shape:
{"goal": "<one sentence describing the overall analysis goal for this dataset>", "steps": ["<short step 1>", "<short step 2>", "<short step 3>"]}

Rules:
- 3 to 5 steps, each a short, concrete action (e.g. "Compare average price across categories", "Check whether order volume trends up or down over time", "Investigate the outliers already flagged in the price column").
- Prefer steps that touch on real signal already visible in the profile/quality/EDA context you're given (a flagged correlation, a category with high variance, a known outlier) over generic boilerplate steps.
- Do not suggest analyzing any column already flagged as constant or ID-like.
- Respond with ONLY the JSON object. No commentary, no markdown fences, no explanation.
"""

# A safe, generic fallback used only if the LLM's response can't be
# parsed/validated as an AnalysisPlan -- keeps the pipeline moving
# (code generation still works fine with a generic plan) instead of
# letting a malformed planning response take down the whole run.
FALLBACK_PLAN_STEPS = [
    "Summarize the overall shape and structure of the dataset.",
    "Report basic descriptive statistics for the numeric columns.",
    "Identify the most notable category breakdown or relationship in the data.",
]


class AnalysisPlan(BaseModel):
    """A validated, structured plan: one goal sentence plus concrete steps."""
    goal: str
    steps: list[str]


def _build_planner_message(profile: dict, quality_report: dict = None, eda_summary: dict = None) -> str:
    message = f"Dataset profile:\n{json.dumps(profile, indent=2, default=str)}"
    if quality_report is not None:
        message += f"\n\nData quality report:\n{json.dumps(quality_report, indent=2, default=str)}"
    if eda_summary is not None:
        message += f"\n\nBaseline EDA summary:\n{json.dumps(eda_summary, indent=2, default=str)}"
    return message


def generate_analysis_plan(profile: dict, quality_report: dict = None, eda_summary: dict = None) -> AnalysisPlan:
    """
    Ask the LLM to produce a short analysis plan for this dataset, and
    validate its response into an AnalysisPlan. Falls back to a generic
    but still-usable plan if the LLM's response is missing, isn't valid
    JSON, or doesn't match the expected shape -- this function is
    designed to never raise, matching the "never crash the pipeline"
    convention established in Phase 6's analyze_csv_file().
    """
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    user_message = _build_planner_message(profile, quality_report, eda_summary)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
        )
        raw_reply = response.choices[0].message.content
        data = json.loads(raw_reply)
        return AnalysisPlan(**data)
    except (json.JSONDecodeError, ValidationError, KeyError, IndexError, TypeError):
        return AnalysisPlan(goal="Explore the dataset's key structure and relationships.", steps=FALLBACK_PLAN_STEPS)


def format_plan_for_prompt(plan: AnalysisPlan) -> str:
    """Render a plan as plain text suitable for including in the code-gen prompt."""
    steps_text = "\n".join(f"{i}. {step}" for i, step in enumerate(plan.steps, start=1))
    return f"Goal: {plan.goal}\nPlanned steps:\n{steps_text}"


# Demo block: python -m app.agent.planner
if __name__ == "__main__":
    from app.ingestion.csv_profiler import profile_csv

    profile = profile_csv(os.path.join("data", "samples", "sample_sales.csv"))
    plan = generate_analysis_plan(profile)
    print(format_plan_for_prompt(plan))
