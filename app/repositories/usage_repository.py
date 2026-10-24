from uuid import UUID

import asyncpg

from app.core.usage import AttemptRecord


class UsageRepository:
    """Persistence for provider attempts. It only writes; nothing reads them yet."""

    def __init__(self, db: asyncpg.Pool | asyncpg.Connection) -> None:
        self._db = db

    async def record_attempts(
        self,
        request_id: UUID,
        prompt_identifier: str,
        attempts: list[AttemptRecord],
    ) -> None:
        """Insert every attempt of one request with a single executemany call.

        One call is all-or-nothing on a pool and on a connection alike, so a
        request is never left with only some of its attempts recorded. There
        is no ON CONFLICT: writing one request's attempts twice is a bug, and
        the primary key rejects it rather than letting it be counted twice. It
        cannot tell when one attempt is written under two request ids: that is
        the caller's to prevent.
        """
        query = """
            INSERT INTO llm_attempts (
                request_id, attempt, prompt_identifier, outcome, stop,
                input_tokens, output_tokens, model, reported_cost_usd,
                elapsed_seconds, status_code, provider_error, retry_after_seconds
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13);
        """
        await self._db.executemany(
            query,
            [
                (
                    request_id,
                    record.attempt,
                    prompt_identifier,
                    # Values, written out. asyncpg happens to store a str-Enum
                    # member by its value, but that is the driver's behaviour,
                    # not this code's; str() and an f-string of the same member
                    # give "AttemptOutcome.RESPONSE".
                    record.outcome.value,
                    record.stop.value if record.stop is not None else None,
                    record.input_tokens,
                    record.output_tokens,
                    record.model,
                    record.reported_cost_usd,
                    record.elapsed_seconds,
                    record.status_code,
                    record.provider_error,
                    record.retry_after_seconds,
                )
                for record in attempts
            ],
        )