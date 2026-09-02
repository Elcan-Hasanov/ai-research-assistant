import pytest

from app.generation.extraction import (
    ExtractionErrorCause,
    ExtractionValidationError,
    parse_paper_facts,
)


def test_parse_paper_facts_valid_json():
    mock_llm_output = (
        '{"problem": "High computational overhead of self-attention.", '
        '"contributions": ["Proposed sparse attention", "Achieved O(N) complexity"], '
        '"evaluated": true}'
    )

    result = parse_paper_facts(mock_llm_output)

    assert result.problem == "High computational overhead of self-attention."
    assert result.contributions == [
        "Proposed sparse attention",
        "Achieved O(N) complexity",
    ]
    assert result.evaluated is True


def test_parse_paper_facts_invalid_json():
    mock_llm_output = (
        "Sure! Here is the output:\n"
        '{"problem": "Truncated json'
    )

    with pytest.raises(ExtractionValidationError) as exc_info:
        parse_paper_facts(mock_llm_output)

    assert exc_info.value.cause == ExtractionErrorCause.UNPARSEABLE


def test_parse_paper_facts_schema_violation_and_no_leakage():
    mock_llm_output = (
        '{"problem": "Valid problem statement", '
        '"contributions": "CONFIDENTIAL_RESEARCH_PAYLOAD_12345", '
        '"evaluated": true}'
    )

    with pytest.raises(ExtractionValidationError) as exc_info:
        parse_paper_facts(mock_llm_output)

    assert exc_info.value.cause == ExtractionErrorCause.SCHEMA_VIOLATION

    error_message_str = str(exc_info.value)
    error_details_str = str(exc_info.value.details)

    assert "CONFIDENTIAL_RESEARCH_PAYLOAD_12345" not in error_message_str
    assert "CONFIDENTIAL_RESEARCH_PAYLOAD_12345" not in error_details_str