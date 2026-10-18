"""What each provider attempt was, recorded as it happens.

A retried request makes several provider attempts, and any of them may have
been billed. This module turns the end of each attempt into a record in this
project's own terms. It persists nothing: the service decides when and where.
"""

from collections.abc import Awaitable
from enum import Enum

from pydantic import BaseModel

from app.core.llm import CompletionStop, LLMCompletion, LLMError


class AttemptOutcome(str, Enum):
    """How one provider attempt ended, as far as this side can tell."""

    RESPONSE = "response"
    LLM_ERROR = "llm_error"
    UNCLASSIFIED = "unclassified"


class AttemptRecord(BaseModel):
    """One provider attempt.

    None in a field means unknown or not applicable, and the outcome decides
    which: a response has no status code to report, while a failed attempt's
    tokens are unknown, since a timed-out call may still have been billed.
    """

    attempt: int
    outcome: AttemptOutcome
    stop: CompletionStop | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    reported_cost_usd: float | None = None
    elapsed_seconds: float | None = None
    status_code: int | None = None
    provider_error: str | None = None
    retry_after_seconds: float | None = None


def _record_response(attempt: int, completion: LLMCompletion) -> AttemptRecord:
    """An attempt that returned a response, whether or not it was usable."""
    return AttemptRecord(
        attempt=attempt,
        outcome=AttemptOutcome.RESPONSE,
        stop=completion.stop,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        model=completion.model,
        reported_cost_usd=completion.reported_cost_usd,
        elapsed_seconds=completion.elapsed_seconds,
    )


def _record_llm_error(attempt: int, error: LLMError) -> AttemptRecord:
    """An attempt the client translated into an LLMError; its usage is unknown."""
    return AttemptRecord(
        attempt=attempt,
        outcome=AttemptOutcome.LLM_ERROR,
        elapsed_seconds=error.elapsed_seconds,
        status_code=error.status_code,
        provider_error=error.provider_error,
        retry_after_seconds=error.retry_after,
    )


def _record_unclassified(attempt: int) -> AttemptRecord:
    """An attempt that ended in an exception the client did not translate."""
    return AttemptRecord(
        attempt=attempt,
        outcome=AttemptOutcome.UNCLASSIFIED,
    )


class AttemptRecorder:
    """Records every attempt of one logical request, in the order they were made."""

    def __init__(self) -> None:
        self.attempts: list[AttemptRecord] = []

    async def observe(
        self,
        call: Awaitable[LLMCompletion],
    ) -> LLMCompletion:
        """Await one attempt, record how it ended, and pass its result or
        exception on unchanged."""
        attempt = len(self.attempts) + 1

        try:
            completion = await call
        except LLMError as error:
            self.attempts.append(_record_llm_error(attempt, error))
            # The same object goes on: the retrier reads its category and
            # retry_after, and the HTTP layer chooses a handler by its type.
            raise

        except Exception:
            # Exception, not BaseException: process shutdown is not an outcome
            # of the call, and nothing in the application cancels an attempt
            # yet. The first change that does, such as a deadline, needs its
            # own branch here: a cancelled attempt may still have been billed.
            self.attempts.append(_record_unclassified(attempt))
            raise
        else:
            self.attempts.append(_record_response(attempt, completion))
            return completion