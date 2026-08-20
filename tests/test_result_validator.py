"""
Phase 15: pytest suite.

Tests for app/validation/result_validator.py -- reads stdout text and
files on disk, no LLM calls.
"""

from app.validation.result_validator import PNG_MAGIC_BYTES, validate_result


def test_stdout_with_insight_is_valid(tmp_path):
    result = validate_result("INSIGHT: something real\n", outputs_dir=str(tmp_path))
    assert result["valid"] is True
    assert result["issues"] == []


def test_stdout_without_insight_is_invalid(tmp_path):
    result = validate_result("just some debug text, no marker\n", outputs_dir=str(tmp_path))
    assert result["valid"] is False
    assert len(result["issues"]) == 1


def test_valid_png_file_passes(tmp_path):
    chart = tmp_path / "chart_1.png"
    chart.write_bytes(PNG_MAGIC_BYTES + b"fake but correctly-headed png bytes")

    result = validate_result("INSIGHT: ok\n", outputs_dir=str(tmp_path))
    assert result["valid"] is True


def test_corrupt_png_file_is_flagged(tmp_path):
    chart = tmp_path / "chart_1.png"
    chart.write_bytes(b"not a real png at all")

    result = validate_result("INSIGHT: ok\n", outputs_dir=str(tmp_path))
    assert result["valid"] is False
    assert "chart_1.png" in result["issues"][0]


def test_empty_png_file_is_flagged(tmp_path):
    chart = tmp_path / "chart_1.png"
    chart.write_bytes(b"")

    result = validate_result("INSIGHT: ok\n", outputs_dir=str(tmp_path))
    assert result["valid"] is False
