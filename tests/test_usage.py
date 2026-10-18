"""Attempt records and the recorder that collects them. No database, no network."""

import pytest

from app.core.llm import CompletionStop, LLMCompletion, LLMError
from app.core.retry import Retrier
from app.core.usage import AttemptOutcome, AttemptRecorder
from tests.conftest import FakeLLMClient


# Billed but unusable: the recorder does not filter on the stop reason.
RESPONSE = LLMCompletion(
    text="ok",
    stop=CompletionStop.TRUNCATED,
    input_tokens=247,
    output_tokens=500,
    model="fake/test-llm",
    elapsed_seconds=1.76,
    reported_cost_usd=0.0137,
)

LLM_ERROR = LLMError(
    "LLM request failed",
    status_code=529,
    provider_error="SimulatedError",
    retry_after=10.0,
    elapsed_seconds=1.76,
)


def _unavailable() -> LLMError:
    """A new upstream failure for every attempt that should fail.

    An exception object raised again keeps the traceback of its earlier raise,
    so one shared between tests shows both raises in a failure report.
    """
    return LLMError("LLM request failed", status_code=529)


async def _no_wait(seconds: float) -> None:
    """Stands in for asyncio.sleep: the retrier's waits take no time."""


async def test_a_response_is_recorded_with_its_usage() -> None:
    """A response is recorded with everything it reports, whether or not it
    was usable; the failure fields stay empty."""
    client = FakeLLMClient(response=RESPONSE)
    recorder = AttemptRecorder()

    completion = await recorder.observe(
        client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
    )

    assert completion is RESPONSE
    assert len(recorder.attempts) == 1
    assert recorder.attempts[0].model_dump() == {
        "attempt": 1,
        "outcome": AttemptOutcome.RESPONSE,
        "stop": CompletionStop.TRUNCATED,
        "input_tokens": 247,
        "output_tokens": 500,
        "model": "fake/test-llm",
        "elapsed_seconds": 1.76,
        "reported_cost_usd": 0.0137,
        "status_code": None,
        "provider_error": None,
        "retry_after_seconds": None,
    }


@pytest.mark.parametrize(
    ("error", "expected_record"),
    [
        (
            LLM_ERROR,
            {
                "attempt": 1,
                "outcome": AttemptOutcome.LLM_ERROR,
                "stop": None,
                "input_tokens": None,
                "output_tokens": None,
                "model": None,
                "reported_cost_usd": None,
                "elapsed_seconds": 1.76,
                "status_code": 529,
                "provider_error": "SimulatedError",
                "retry_after_seconds": 10.0,
            },
        ),
        (
            TypeError("malformed response"),
            {
                "attempt": 1,
                "outcome": AttemptOutcome.UNCLASSIFIED,
                "stop": None,
                "input_tokens": None,
                "output_tokens": None,
                "model": None,
                "reported_cost_usd": None,
                "elapsed_seconds": None,
                "status_code": None,
                "provider_error": None,
                "retry_after_seconds": None,
            },
        ),
    ],
    ids=["translated", "untranslated"],
)
async def test_a_failure_is_recorded_with_only_what_its_exception_reveals(
    error: Exception, expected_record: dict
) -> None:
    """A failed attempt is recorded with only what its exception reveals, and
    the exception goes on unchanged.

    A translated failure carries its status, provider error, requested wait
    and duration, but no usage: a timed-out attempt may still have been
    billed, so its tokens are unknown, not zero. An exception the client did
    not translate reveals nothing reliable, so only its position and outcome
    are recorded.
    """
    client = FakeLLMClient(outcomes=[error])
    recorder = AttemptRecorder()

    with pytest.raises(type(error)) as caught:
        await recorder.observe(
            client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
        )

    assert caught.value is error
    assert len(recorder.attempts) == 1
    assert recorder.attempts[0].model_dump() == expected_record


async def test_attempts_are_numbered_in_the_order_the_retrier_made_them() -> None:
    """Through the real retrier, each attempt is observed once and numbered in
    the order it was made."""
    client = FakeLLMClient(outcomes=[_unavailable(), _unavailable(), RESPONSE])
    recorder = AttemptRecorder()
    retrier = Retrier(sleep=_no_wait)

    await retrier.run(
        lambda: recorder.observe(
            client.complete([{"role": "user", "content": "hi"}], max_tokens=10)
        )
    )

    assert [
        (record.attempt, record.outcome) for record in recorder.attempts
    ] == [
        (1, AttemptOutcome.LLM_ERROR),
        (2, AttemptOutcome.LLM_ERROR),
        (3, AttemptOutcome.RESPONSE),
    ]