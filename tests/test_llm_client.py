import json
import math
import time

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import Message
import httpx
import pytest

from app.core.config import get_settings
from app.core.errors import FailureCategory
from app.core.llm import (
    CompletionStop,
    LLMClient,
    LLMError,
    create_llm_client,
    to_completion,
    parse_retry_after,
    parse_reported_cost
)
from app.generation.extraction import parse_paper_facts
from app.services.generation_service import extraction_request
from tests.conftest import load_recording


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

# The translation tests pin what is read from the response; the duration
# only has to be present, so they all pass the same one.
ELAPSED_SECONDS = 1.0


def test_to_completion_parses_normal_response():
    message = Message.model_validate(RAW)
    result = to_completion(message, elapsed_seconds=ELAPSED_SECONDS)

    assert result.model == "anthropic/claude-haiku-4.5"
    assert result.input_tokens == 18
    assert result.output_tokens == 62
    assert result.stop == CompletionStop.COMPLETED
    assert result.text.startswith("A vector database stores")


def test_to_completion_handles_truncated_response():
    message = Message.model_validate({**RAW, "stop_reason": "max_tokens"})
    result = to_completion(message, elapsed_seconds=ELAPSED_SECONDS)

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
    result = to_completion(message, elapsed_seconds=ELAPSED_SECONDS)

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
    result = to_completion(message, elapsed_seconds=ELAPSED_SECONDS)

    assert result.text == "Actual answer."


def test_to_completion_handles_unknown_stop_reason():
    # model_construct bypasses SDK's Literal enum validation for stop_reason
    message = Message.model_construct(**{**RAW, "stop_reason": "something_unexpected"})
    result = to_completion(message, elapsed_seconds=ELAPSED_SECONDS)

    assert result.stop == CompletionStop.UNKNOWN

def test_to_completion_maps_refusal():
    # "refusal" is inside the SDK's stop_reason Literal, so model_validate
    # works and the SDK's own validation runs as part of the test.
    message = Message.model_validate({**RAW, "stop_reason": "refusal"})
    result = to_completion(message, elapsed_seconds=ELAPSED_SECONDS)

    assert result.stop == CompletionStop.REFUSED


def test_to_completion_maps_context_window_overflow():
    message = Message.model_validate(
        {**RAW, "stop_reason": "model_context_window_exceeded"}
    )
    result = to_completion(message, elapsed_seconds=ELAPSED_SECONDS)

    assert result.stop == CompletionStop.CONTEXT_OVERFLOW


async def test_aclose_releases_the_real_sdk_client():
    """The double cannot protect this: a hand-written fake would have
    whatever attribute the code asked for. Only the real type can."""
    sdk_client = AsyncAnthropic(api_key="sk-not-used", max_retries=0)
    client = LLMClient(sdk_client, "fake/test-llm")

    assert sdk_client.is_closed() is False

    await client.aclose()

    assert sdk_client.is_closed() is True


# ============================================================================
# Provider error -> LLMError. Everything below LLMClient is the real stack;
# only the socket is replaced, so the SDK builds the request and raises the
# exception exactly as it would in production.
# ============================================================================

def _responding(status_code: int, error_type: str, headers: dict[str, str] | None = None):
    """A transport handler that answers every request with one provider error."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            json={"type": "error", "error": {"type": error_type, "message": "…"}},
            headers=headers,
        )
    return handler


def _client_for(handler, *, clock=time.perf_counter) -> tuple[LLMClient, list[httpx.Request]]:
    """A real LLMClient over a real AsyncAnthropic whose socket is faked.

    max_retries is set here so that a call count of one means "complete()
    called the provider once" rather than "the SDK happened not to retry".
    It does not pin the factory's own setting; the factory_built_client tests do.

    The clock is the production one unless a test that pins a duration
    passes its own.
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
    return LLMClient(sdk_client, "fake/test-llm", clock=clock), sent


async def test_rate_limit_is_translated_and_carries_the_status():
    client, _ = _client_for(_responding(429, "rate_limit_error"))

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


async def test_retry_after_reaches_the_error():
    client, _ = _client_for(_responding(429, "rate_limit_error", headers={"retry-after": "7"}))

    try:
        with pytest.raises(LLMError) as caught:
            await client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    finally:
        await client.aclose()

    error = caught.value
    assert error.retry_after == 7.0


# ============================================================================
# The factory's transport policy. The client is built exactly as the
# application builds it, on each of the factory's two paths.
# ============================================================================

@pytest.fixture(
    params=["https://gateway.test/api/v1", ""],
    ids=["gateway", "direct"],
)
async def factory_built_client(request, monkeypatch):
    """The client as create_llm_client builds it, once per path.

    An environment variable outranks .env, and an empty LLM_BASE_URL selects
    the direct path because the factory branches on the value's truthiness.
    get_settings is cached: it is cleared on the way in so this test sees its
    own URL, and on the way out so the next test does not inherit it.
    """
    monkeypatch.setenv("LLM_BASE_URL", request.param)
    get_settings.cache_clear()
    client = create_llm_client()
    try:
        yield client
    finally:
        await client.aclose()
        get_settings.cache_clear()


async def test_factory_switches_off_the_sdk_retry(factory_built_client):
    """The retry budget lives one layer up. Left at the SDK default of 2,
    every attempt that layer makes would become up to three billed calls.

    This pins configuration rather than behaviour: the factory builds its own
    transport, so no fake socket can be slipped underneath it."""
    assert factory_built_client._client.max_retries == 0


def _raising(exc_type: type[httpx.TransportError]):
    """A transport handler that fails every request with one transport error."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type("simulated transport failure")
    return handler


@pytest.mark.parametrize(
    "handler",
    [
        _responding(429, "rate_limit_error"),
        _responding(503, "api_error"),
        _responding(529, "overloaded_error"),
        _raising(httpx.ConnectError),
        _raising(httpx.ReadTimeout),
    ],
    ids=["429-rate-limit", "503-server-error", "529-overloaded", "connect-refused", "read-timeout"],
)
async def test_complete_makes_one_call_on_every_retryable_failure(handler):
    """complete() reaches the provider exactly once on every failure the retry layer will retry. 
    That layer's attempt budget multiplies whatever happens here."""
    client, sent = _client_for(handler)

    try:
        with pytest.raises(LLMError):
            await client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    finally:
        await client.aclose()

    assert len(sent) == 1, "complete() must make exactly one provider call"


async def test_factory_uses_layered_timeouts(factory_built_client):
    """Connection setup either succeeds quickly or not at all, so the connect
    phase gets its own short bound; a request that never left is the cheapest
    one to retry, and should stay cheap in time as well.

    The other three phases keep the configured bound. It limits the silence
    between bytes within a phase, not the length of the call."""
    bound = get_settings().llm_timeout_seconds
    assert factory_built_client._client.timeout == httpx.Timeout(
        connect=5.0, read=bound, write=bound, pool=bound
    )


@pytest.mark.parametrize(
    "base_url", ["https://gateway.test/api/v1", ""], ids=["gateway", "direct"]
)
async def test_factory_sends_through_the_http_client_it_is_given(base_url, monkeypatch):
    """A client passed to the factory carries the request, on both paths.

    The response-variability measurement records what this client receives.
    A branch that dropped the argument would leave the SDK on a client of its
    own, and the measurement would see nothing.
    """
    monkeypatch.setenv("LLM_BASE_URL", base_url)
    get_settings.cache_clear()
    sent: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return _succeeding(RAW)(request)

    client = create_llm_client(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(recording))
    )
    try:
        await client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    finally:
        await client.aclose()
        get_settings.cache_clear()

    assert len(sent) == 1


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"retry-after": "7"}, 7.0),
        ({"retry-after-ms": "1500"}, 1.5),
        ({"retry-after-ms": "1500", "retry-after": "7"}, 1.5),
        ({"retry-after-ms": "soon", "retry-after": "7"}, 7.0),
        ({"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}, None),
        ({"retry-after": "-3"}, None),
        ({"retry-after": "inf"}, None),
        ({}, None),
    ],
    ids=[
        "seconds",
        "milliseconds",
        "milliseconds-win",
        "bad-milliseconds-fall-back",
        "http-date",
        "negative",
        "infinite",
        "absent",
    ],
)
def test_retry_after_is_read_as_seconds(headers, expected):
    actual = parse_retry_after(httpx.Headers(headers))
    assert actual == expected


# ============================================================================
# What complete() measures, and the cost it carries. The SDK is real here too;
# only the socket and, where a test pins a duration, the clock are fake.
# ============================================================================

class FakeClock:
    """Hands out the readings it was given, one per read.

    A read past the end of the script fails the test, so an extra reading
    cannot shift the measured interval unseen.
    """

    def __init__(self, *readings: float) -> None:
        self._readings = list(readings)

    def read(self) -> float:
        """The next scripted reading."""
        if not self._readings:
            raise AssertionError("FakeClock: a read was not in the script")
        return self._readings.pop(0)


def _succeeding(body: dict):
    """A transport handler that answers every request with one successful response."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)
    return handler


async def test_complete_reports_how_long_the_call_took():
    """The duration is the time between the two clock readings around the provider call."""
    client, _ = _client_for(_succeeding(RAW), clock=FakeClock(1.0, 3.5).read)

    try:
        completion = await client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    finally:
        await client.aclose()

    assert completion.elapsed_seconds == 2.5


@pytest.mark.parametrize(
    "handler",
    [
        _responding(529, "overloaded_error"),
        _raising(httpx.ReadTimeout),
    ],
    ids=["status-error", "read-timeout"],
)
async def test_a_failed_call_reports_how_long_it_took(handler):
    """A failed attempt is timed as well: a timed-out attempt never gets a
    response, and its duration is what the timeout rules are judged on."""
    client, _ = _client_for(handler, clock=FakeClock(1.0, 3.5).read)

    try:
        with pytest.raises(LLMError) as caught:
            await client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    finally:
        await client.aclose()

    assert caught.value.elapsed_seconds == 2.5


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({**RAW, "usage": {**RAW["usage"], "cost": 0.00153}}, 0.00153),
        (RAW, None),
        ({**RAW, "usage": {**RAW["usage"], "cost": -0.5}}, None),
    ],
    ids=["reported", "absent", "negative"],
)
async def test_complete_keeps_the_reported_cost_only_when_usable(body, expected):
    """A response's cost reaches the completion only when it is usable.

    The gateway's cost is a field the SDK does not declare; it arrives only
    because the SDK keeps such fields. A response without one must still
    complete, and an unusable one must not be stored as if the gateway had
    charged it.
    """
    client, _ = _client_for(_succeeding(body))

    try:
        completion = await client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    finally:
        await client.aclose()

    assert completion.reported_cost_usd == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (7.43, 7.43),
        (0, 0.0),
        (None, None),
        (True, None),
        ("abc", None),
        (-42, None),
        (math.inf, None),
        (10**400, None),
    ],
    ids=["dollars", "free", "absent", "boolean", "string", "negative", "infinite", "too-large"],
)
def test_a_raw_cost_is_read_as_dollars_or_none(value, expected):
    actual = parse_reported_cost(value)

    assert actual == expected


# ============================================================================
# What complete() sends. An optional argument reaches the request body only
# when the caller gave one: an explicit null is not the same as an absent key,
# and a provider may reject it.
# ============================================================================

OPTIONAL_KEYS = ("system", "temperature", "output_config")

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}


async def test_complete_sends_optional_arguments_when_given():
    client, sent = _client_for(_succeeding(RAW))

    try:
        await client.complete(
            [{"role": "user", "content": "hi"}],
            max_tokens=10,
            system="Answer in one word.",
            temperature=0.3,
            response_schema=ANSWER_SCHEMA,
        )
    finally:
        await client.aclose()

    body = json.loads(sent[0].content)
    assert {key: body.get(key) for key in OPTIONAL_KEYS} == {
        "system": "Answer in one word.",
        "temperature": 0.3,
        "output_config": {"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
    }


async def test_complete_omits_optional_arguments_that_are_not_given():
    client, sent = _client_for(_succeeding(RAW))

    try:
        await client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    finally:
        await client.aclose()

    body = json.loads(sent[0].content)
    assert [key for key in OPTIONAL_KEYS if key in body] == []


# ============================================================================
# A recorded response. scripts/measure_response_variability.py captured it on
# the wire from a real call; it is replaced by recording again, never edited.
# ============================================================================

async def test_complete_reads_every_field_of_a_recorded_response():
    """Every field this project reads is taken from where the gateway puts it.

    The recording ended normally: the script records no other kind of
    response. The expected values come from the recording itself, so a new
    recording needs no change here.
    """
    recording = load_recording("extract_paper_facts.v1")
    body = recording["response"]
    client, _ = _client_for(_succeeding(body))
    request = extraction_request(recording["article"])

    try:
        completion = await client.complete(**request.to_completion_kwargs())
    finally:
        await client.aclose()

    assert completion.model_dump(exclude={"elapsed_seconds"}) == {
        "text": body["content"][0]["text"],
        "stop": CompletionStop.COMPLETED,
        "input_tokens": body["usage"]["input_tokens"],
        "output_tokens": body["usage"]["output_tokens"],
        "model": body["model"],
        "reported_cost_usd": body["usage"]["cost"],
    }


def test_a_recorded_response_parses_into_paper_facts():
    """The extraction parser accepts what the model actually returned.

    Hand-written JSON shows what we expect the model to say; this is what it
    said. It also notices a recording gone stale on this side: a change to
    PaperFacts that the recorded answer no longer fits fails here, and the fix
    is a new recording.
    """
    text = load_recording("extract_paper_facts.v1")["response"]["content"][0]["text"]

    facts = parse_paper_facts(text)

    assert facts.model_dump() == json.loads(text)