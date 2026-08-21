from anthropic.types import Message

from app.core.llm import CompletionStop, to_completion

RAW = {
    "id": "gen-1787318162-WCISz7fTPyGtXjcLyjZG",
    "content": [
        {
            "type": "text",
            "text": "A vector database stores and retrieves data based on numerical vectors (arrays of numbers) that represent the semantic meaning of information, rather than traditional keyword matching. It uses mathematical distance calculations to find similar items, making it ideal for AI applications like semantic search, recommendation systems, and large language models.",
        }
    ],
    "model": "anthropic/claude-haiku-4.5",
    "role": "assistant",
    "stop_reason": "end_turn",
    "type": "message",
    "usage": {
        "input_tokens": 18,
        "output_tokens": 62,
    },
}


def test_to_completion_parses_normal_response():
    message = Message.model_validate(RAW)
    result = to_completion(message)

    assert result.model == "anthropic/claude-haiku-4.5"
    assert result.input_tokens == 18
    assert result.output_tokens == 62
    assert result.stop == CompletionStop.COMPLETED
    assert result.text.startswith("A vector database stores")


def test_to_completion_handles_truncated_response():
    message = Message.model_validate({**RAW, "stop_reason": "max_tokens"})
    result = to_completion(message)

    assert result.stop == CompletionStop.TRUNCATED


def test_to_completion_joins_multiple_text_blocks():
    payload = {
        **RAW,
        "content": [
            {"type": "text", "text": "First part. "},
            {"type": "text", "text": "Second part."},
        ],
    }
    message = Message.model_validate(payload)
    result = to_completion(message)

    assert result.text == "First part. Second part."


def test_to_completion_ignores_non_text_blocks():
    payload = {
        **RAW,
        "content": [
            {"type": "thinking", "thinking": "Internal reasoning..."},
            {"type": "text", "text": "Actual answer."},
        ],
    }
    # model_construct bypasses SDK's strict block structure validation
    message = Message.model_construct(**payload)
    result = to_completion(message)

    assert result.text == "Actual answer."


def test_to_completion_handles_unknown_stop_reason():
    # model_construct bypasses SDK's Literal enum validation for stop_reason
    message = Message.model_construct(**{**RAW, "stop_reason": "something_unexpected"})
    result = to_completion(message)

    assert result.stop == CompletionStop.UNKNOWN