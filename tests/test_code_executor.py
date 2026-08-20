"""
Phase 15: pytest suite.

Integration tests for the self-correction loop in
app/executor/code_executor.py. The Groq client is mocked throughout --
these tests never make a real network call, so they run the same way
locally and in CI with no API key needed.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.executor.code_executor import run_with_self_correction
from app.ingestion.csv_profiler import profile_csv

SAMPLE_CSV = "data/samples/sample_sales.csv"


def _fenced(code: str) -> str:
    return f"```python\n{code}\n```"


def _mock_groq_returning(*code_strings):
    """
    Patches app.agent.llm_client.Groq so each successive call to
    generate_analysis_code() returns the next string in code_strings (the
    last one repeats if there are more calls than strings provided).
    """
    call_count = {"n": 0}

    def fake_create(*args, **kwargs):
        call_count["n"] += 1
        index = min(call_count["n"], len(code_strings)) - 1
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = code_strings[index]
        return mock_resp

    patcher = patch("app.agent.llm_client.Groq")
    mock_groq_class = patcher.start()
    mock_groq_class.return_value.chat.completions.create.side_effect = fake_create
    return patcher, call_count


@pytest.fixture
def profile():
    return profile_csv(SAMPLE_CSV)


def test_succeeds_on_first_valid_attempt(profile):
    patcher, call_count = _mock_groq_returning(
        _fenced("print('INSIGHT: works first try')")
    )
    try:
        result = run_with_self_correction(profile, SAMPLE_CSV)
    finally:
        patcher.stop()

    assert result["success"] is True
    assert len(result["attempts"]) == 1
    assert call_count["n"] == 1


def test_unsafe_code_is_blocked_and_retried(profile):
    patcher, call_count = _mock_groq_returning(
        _fenced("import os\nos.system('echo pwned')"),
        _fenced("print('INSIGHT: safe on retry')"),
    )
    try:
        result = run_with_self_correction(profile, SAMPLE_CSV)
    finally:
        patcher.stop()

    assert result["success"] is True
    assert result["attempts"][0]["blocked_by_scanner"] is True
    assert result["attempts"][1]["blocked_by_scanner"] is False
    assert call_count["n"] == 2


def test_no_insight_output_fails_validation_and_retries(profile):
    patcher, call_count = _mock_groq_returning(
        _fenced("x = df['price'].mean()"),  # runs fine, prints nothing useful
        _fenced("print('INSIGHT: now it prints something')"),
    )
    try:
        result = run_with_self_correction(profile, SAMPLE_CSV)
    finally:
        patcher.stop()

    assert result["success"] is True
    assert result["attempts"][0]["failed_validation"] is True
    assert result["attempts"][1]["failed_validation"] is False


def test_gives_up_cleanly_when_always_unsafe(profile):
    patcher, call_count = _mock_groq_returning(
        _fenced("import subprocess\nsubprocess.run(['echo', 'hi'])")
    )
    try:
        result = run_with_self_correction(profile, SAMPLE_CSV)
    finally:
        patcher.stop()

    assert result["success"] is False
    assert len(result["attempts"]) == 4  # 1 initial + 3 retries
    assert all(a["blocked_by_scanner"] for a in result["attempts"])
