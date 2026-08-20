"""
Phase 17: pytest tests for app/agent/planner.py. Groq is mocked -- no
real network calls.
"""

import json
from unittest.mock import MagicMock, patch

from app.agent.planner import AnalysisPlan, format_plan_for_prompt, generate_analysis_plan


def _mock_groq_json_response(payload: dict):
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(payload)
    return mock_resp


def test_valid_json_response_produces_matching_plan():
    payload = {"goal": "Understand sales trends.", "steps": ["Check monthly totals", "Compare categories"]}

    with patch("app.agent.planner.Groq") as mock_groq_class:
        mock_groq_class.return_value.chat.completions.create.return_value = _mock_groq_json_response(payload)
        plan = generate_analysis_plan({"shape": {"rows": 10, "columns": 3}})

    assert isinstance(plan, AnalysisPlan)
    assert plan.goal == payload["goal"]
    assert plan.steps == payload["steps"]


def test_malformed_json_falls_back_to_generic_plan():
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "not valid json at all {{"

    with patch("app.agent.planner.Groq") as mock_groq_class:
        mock_groq_class.return_value.chat.completions.create.return_value = mock_resp
        plan = generate_analysis_plan({"shape": {"rows": 10, "columns": 3}})

    assert isinstance(plan, AnalysisPlan)
    assert len(plan.steps) > 0  # fell back, but still usable


def test_missing_required_field_falls_back_to_generic_plan():
    # Valid JSON, but doesn't match the AnalysisPlan schema (no "steps").
    payload = {"goal": "Just a goal, no steps field"}

    with patch("app.agent.planner.Groq") as mock_groq_class:
        mock_groq_class.return_value.chat.completions.create.return_value = _mock_groq_json_response(payload)
        plan = generate_analysis_plan({"shape": {"rows": 10, "columns": 3}})

    assert isinstance(plan, AnalysisPlan)
    assert len(plan.steps) > 0


def test_format_plan_for_prompt_includes_goal_and_numbered_steps():
    plan = AnalysisPlan(goal="Test goal", steps=["Step one", "Step two"])
    text = format_plan_for_prompt(plan)
    assert "Test goal" in text
    assert "1. Step one" in text
    assert "2. Step two" in text
