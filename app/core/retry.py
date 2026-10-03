"""Retrying an LLM call while the upstream is unavailable.

This module is the one place that decides whether a failed attempt is worth
another. It reads the answer from the error's category: only
UPSTREAM_UNAVAILABLE is retried, and every other failure is raised on the
attempt that produced it.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from app.core.errors import FailureCategory
from app.core.llm import LLMCompletion, LLMError

logger = logging.getLogger(__name__)

# The SDK's own retry policy, which the client switches off, restored at this
# layer: three attempts in all, a wait that starts at half a second and
# doubles, and a server-requested wait honoured up to a minute. The values are
# borrowed, not measured in this project.
MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 0.5
MAX_RETRY_AFTER_SECONDS = 60.0


def backoff_delay(failed_attempt: int, fraction: float) -> float:
    """Seconds to wait after the given attempt failed, before the next one.

    fraction is a random draw from [0, 1) that trims the wait by up to a
    quarter. It never trims more: with a single caller there is no crowd to
    spread out, and a wait that could fall to zero would send the next request
    to an overloaded upstream at once.
    """
    return BASE_DELAY_SECONDS * 2 ** (failed_attempt - 1) * (1 - 0.25 * fraction)


def plan_retry(error: LLMError, failed_attempt: int, fraction: float) -> float | None:
    """Seconds to wait before the next attempt, or None to give up."""
    if error.category is not FailureCategory.UPSTREAM_UNAVAILABLE:
        return None
    if failed_attempt >= MAX_ATTEMPTS:
        return None
    if error.retry_after is not None:
        # Retrying sooner than the server asked would repeat the request it
        # has just refused; a longer wait than this is not worth holding the
        # caller for, so the error goes back instead.
        if error.retry_after > MAX_RETRY_AFTER_SECONDS:
            return None
        return error.retry_after
    return backoff_delay(failed_attempt, fraction)


class Retrier:
    """Runs one LLM call, retrying it as the policy above allows.

    The wait and the random draw are injected so tests can see both without
    waiting; production uses asyncio.sleep and random.random.
    """

    def __init__(
        self,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        fraction: Callable[[], float] = random.random,
    ) -> None:
        self._sleep = sleep
        self._fraction = fraction

    async def run(self, call: Callable[[], Awaitable[LLMCompletion]]) -> LLMCompletion:
        """Return what call() returns, retrying while the policy allows.

        call is invoked once per attempt and must build a new awaitable each
        time, as a lambda around the client call does. A coroutine created
        once and handed back on every attempt fails on the first retry: a
        coroutine can be awaited only once. When the policy gives up, the
        last error is re-raised unchanged.
        """
        failed_attempt = 0
        while True:
            try:
                return await call()
            except LLMError as error:
                failed_attempt += 1
                wait = plan_retry(error, failed_attempt, self._fraction())
                if wait is None:
                    raise
                logger.warning(
                    "[%s] %s%s (attempt %d of %d); retrying in %.2fs",
                    error.category.value,
                    error,
                    _context_text(error),
                    failed_attempt,
                    MAX_ATTEMPTS,
                    wait,
                )
                await self._sleep(wait)


def _context_text(error: LLMError) -> str:
    # The HTTP error handler renders context the same way, so a retried
    # attempt and the request's final outcome read alike in the log.
    return "".join(f" {key}={value}" for key, value in error.log_context().items())