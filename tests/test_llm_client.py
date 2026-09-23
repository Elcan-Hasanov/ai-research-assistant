from anthropic.types import Message
from anthropic import AsyncAnthropic

from app.core.llm import CompletionStop, to_completion, LLMClient

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

def test_to_completion_maps_refusal():
    # "refusal" is inside the SDK's stop_reason Literal, so model_validate
    # works and the SDK's own validation runs as part of the test.
    message = Message.model_validate({**RAW, "stop_reason": "refusal"})
    result = to_completion(message)

    assert result.stop == CompletionStop.REFUSED


def test_to_completion_maps_context_window_overflow():
    message = Message.model_validate(
        {**RAW, "stop_reason": "model_context_window_exceeded"}
    )
    result = to_completion(message)

    assert result.stop == CompletionStop.CONTEXT_OVERFLOW


async def test_aclose_releases_the_real_sdk_client():
    """The double cannot protect this: a hand-written fake would have
    whatever attribute the code asked for. Only the real type can."""
    sdk_client = AsyncAnthropic(api_key="sk-not-used", max_retries=0)
    client = LLMClient(sdk_client, "fake/test-llm")

    assert sdk_client.is_closed() is False

    await client.aclose()

    assert sdk_client.is_closed() is True


import anthropic
import httpx
import pytest

from app.core.errors import FailureCategory
from app.core.llm import LLMClient, LLMError


# ============================================================================
# Provider error -> LLMError. Everything below LLMClient is the real stack;
# only the socket is replaced, so the SDK builds the request and raises the
# exception exactly as it would in production.
# ============================================================================

def _responding(status_code: int, error_type: str):
    """A transport handler that answers every request with one provider error."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"type": "error", "error": {"type": error_type, "message": "…"}},
        )
    return handler


def _client_for(handler) -> tuple[LLMClient, list[httpx.Request]]:
    """A real LLMClient over a real AsyncAnthropic whose socket is faked.

    max_retries is set here so that a call count of one means "complete()
    called the provider once" rather than "the SDK happened not to retry".
    It does not pin the factory's own setting — nothing does.
    """
    sent: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return handler(request)

    sdk_client = anthropic.AsyncAnthropic(
        api_key="sk-not-used",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(recording)),
    )
    return LLMClient(sdk_client, "fake/test-llm"), sent


async def test_rate_limit_is_translated_and_carries_the_status():
    client, sent = _client_for(_responding(429, "rate_limit_error"))

    try:
        with pytest.raises(LLMError) as caught:
            await client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    finally:
        await client.aclose()

    error = caught.value
    assert error.status_code == 429
    assert error.provider_error == "RateLimitError"
    assert error.category is FailureCategory.UPSTREAM_UNAVAILABLE
    assert str(error) == "LLM request failed"
    assert len(sent) == 1, "complete() must make exactly one provider call"


async def test_authentication_failure_is_translated_to_internal():
    client, _ = _client_for(_responding(401, "authentication_error"))

    try:
        with pytest.raises(LLMError) as caught:
            await client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    finally:
        await client.aclose()

    assert caught.value.status_code == 401
    assert caught.value.provider_error == "AuthenticationError"
    assert caught.value.category is FailureCategory.INTERNAL


async def test_connection_failure_arrives_without_a_status_code():
    """Nothing reached HTTP, so status_code is absent rather than unknown."""
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client, _ = _client_for(refuse)

    try:
        with pytest.raises(LLMError) as caught:
            await client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    finally:
        await client.aclose()

    assert caught.value.status_code is None
    assert caught.value.provider_error == "APIConnectionError"
    assert caught.value.category is FailureCategory.UPSTREAM_UNAVAILABLE