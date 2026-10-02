"""The retry policy and the loop that applies it.

Nothing here waits. The loop's sleep is a recorder and its random draw is a
constant, so every wait the loop asks for can be asserted exactly.
"""

import logging

import pytest

from app.core.llm import CompletionStop, LLMCompletion, LLMError
from app.core.retry import MAX_ATTEMPTS, Retrier, plan_retry
from tests.conftest import FakeLLMClient

MESSAGES = [{"role": "user", "content": "hi"}]

DONE = LLMCompletion(
    text="ok",
    stop=CompletionStop.COMPLETED,
    input_tokens=1,
    output_tokens=1,
    model="fake/test-llm",
)


class FakeSleep:
    """Records every wait it is asked for and returns at once."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)


def _error(status_code: int | None, retry_after: float | None = None) -> LLMError:
    """An LLMError as complete() raises it; the status decides the category."""
    return LLMError(
        "LLM request failed",
        status_code=status_code,
        provider_error="SimulatedError",
        retry_after=retry_after,
    )


async def test_a_retryable_failure_is_retried_after_the_backoff():
    """One overloaded attempt, then a success: the loop waits the first
    backoff and returns what the second attempt produced."""
    client = FakeLLMClient(outcomes=[_error(529), DONE])
    clock = FakeSleep()
    retrier = Retrier(sleep=clock.sleep, fraction=lambda: 0.0)

    result = await retrier.run(lambda: client.complete(MESSAGES, max_tokens=10))

    assert result is DONE
    assert len(client.calls) == 2
    assert clock.waits == [0.5]


async def test_each_retry_leaves_a_warning(caplog):
    """A retry that ends in success leaves no error behind, so this warning is
    the only trace that the upstream faltered."""
    client = FakeLLMClient(outcomes=[_error(529), DONE])
    retrier = Retrier(sleep=FakeSleep().sleep, fraction=lambda: 0.0)

    with caplog.at_level(logging.WARNING, logger="app.core.retry"):
        await retrier.run(lambda: client.complete(MESSAGES, max_tokens=10))

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert f"attempt 1 of {MAX_ATTEMPTS}" in record.getMessage()


@pytest.mark.parametrize(
    ("failed_attempt", "fraction", "expected"),
    [
        (1, 0.0, 0.5),
        (2, 0.0, 1.0),
        (1, 0.5, 0.4375),
    ],
    ids=["first-retry", "second-retry", "draw-trims-the-wait"],
)
def test_plan_retry_waits_by_the_backoff(failed_attempt, fraction, expected):
    """The wait doubles per retry, and the draw trims it by at most a quarter."""
    assert plan_retry(_error(529), failed_attempt, fraction) == expected


@pytest.mark.parametrize(
    ("retry_after", "expected"),
    [
        (7.0, 7.0),
        (60.0, 60.0),
        (60.5, None),
    ],
    ids=["within-limit", "at-limit", "past-limit"],
)
def test_plan_retry_honours_a_retry_after_up_to_the_limit(retry_after, expected):
    """A server-requested wait replaces the backoff, but only up to the limit; past it, the error goes back to the caller."""
    assert plan_retry(_error(429, retry_after=retry_after), 1, 0.0) == expected


@pytest.mark.parametrize(
    ("error", "failed_attempt"),
    [
        (_error(401), 1),
        (_error(413), 1),
        (_error(529), MAX_ATTEMPTS),
    ],
    ids=["internal", "unusable-source", "budget-spent"],
)
def test_plan_retry_gives_up(error, failed_attempt):
    """The upstream cannot fix the failure, or the budget is spent: either way there is nothing to wait for."""
    assert plan_retry(error, failed_attempt, 0.0) is None


async def test_the_last_error_is_raised_unchanged_when_attempts_run_out():
    """When the budget runs out, the caller gets the last attempt's own error, not a new one."""
    outcomes = [_error(529), _error(503), _error(429)]
    client = FakeLLMClient(outcomes=outcomes)
    clock = FakeSleep()
    retrier = Retrier(sleep=clock.sleep, fraction=lambda: 0.0)

    with pytest.raises(LLMError) as caught:
        await retrier.run(lambda: client.complete(MESSAGES, max_tokens=10))

    assert caught.value is outcomes[-1]
    assert len(client.calls) == 3
    assert clock.waits == [0.5, 1.0]


async def test_a_non_retryable_failure_is_raised_on_the_first_attempt():
    """A failure the upstream cannot fix leaves on the attempt that produced it, without a wait."""
    outcomes = [_error(401)]
    client = FakeLLMClient(outcomes=outcomes)
    clock = FakeSleep()
    retrier = Retrier(sleep=clock.sleep, fraction=lambda: 0.0)

    with pytest.raises(LLMError):
        await retrier.run(lambda: client.complete(MESSAGES, max_tokens=10))

    assert len(client.calls) == 1
    assert clock.waits == []


async def test_an_error_that_is_not_an_llm_error_is_not_retried():
    """Only LLMError carries a category to read; anything else goes straight out on the first attempt."""
    outcomes = [TypeError("malformed response")]
    client = FakeLLMClient(outcomes=outcomes)
    clock = FakeSleep()
    retrier = Retrier(sleep=clock.sleep, fraction=lambda: 0.0)

    with pytest.raises(TypeError):
        await retrier.run(lambda: client.complete(MESSAGES, max_tokens=10))

    assert len(client.calls) == 1
    assert clock.waits == []