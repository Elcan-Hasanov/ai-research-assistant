"""Writing attempt records to llm_attempts, against the real test database."""

import uuid

import asyncpg
import pytest

from app.core.database import create_script_pool
from app.core.llm import CompletionStop
from app.core.usage import AttemptOutcome, AttemptRecord
from app.repositories.usage_repository import UsageRepository


pytestmark = pytest.mark.db


async def test_record_attempts_round_trips_every_column(db_conn, usage_repository):
    """Every column of every attempt is written as given and read back unchanged,
    NULLs included; created_at is filled by the database."""
    records = [
        AttemptRecord(
            attempt=1,
            outcome=AttemptOutcome.RESPONSE,
            stop=CompletionStop.TRUNCATED,
            input_tokens=247,
            output_tokens=500,
            model="fake/test-llm",
            reported_cost_usd=0.0137,
            elapsed_seconds=1.76,
            status_code=None,
            provider_error=None,
            retry_after_seconds=None,
        ),
        AttemptRecord(
            attempt=2,
            outcome=AttemptOutcome.LLM_ERROR,
            stop=None,
            input_tokens=None,
            output_tokens=None,
            model=None,
            reported_cost_usd=None,
            elapsed_seconds=2.41,
            status_code=529,
            provider_error="InternalServerError",
            retry_after_seconds=3.5,
        ),
    ]

    request_id = uuid.uuid4()

    await usage_repository.record_attempts(
        request_id,
        "extract_paper_facts.v1",
        records,
    )

    rows = await db_conn.fetch(
        """
        SELECT *
        FROM llm_attempts
        WHERE request_id = $1
        ORDER BY attempt
        """,
        request_id,
    )

    actual = [dict(row) for row in rows]

    for row in actual:
        created_at = row.pop("created_at")
        assert created_at is not None

    assert actual == [
        {
            "request_id": request_id,
            "attempt": 1,
            "prompt_identifier": "extract_paper_facts.v1",
            "outcome": "response",
            "stop": "truncated",
            "input_tokens": 247,
            "output_tokens": 500,
            "model": "fake/test-llm",
            "reported_cost_usd": 0.0137,
            "elapsed_seconds": 1.76,
            "status_code": None,
            "provider_error": None,
            "retry_after_seconds": None,
        },
        {
            "request_id": request_id,
            "attempt": 2,
            "prompt_identifier": "extract_paper_facts.v1",
            "outcome": "llm_error",
            "stop": None,
            "input_tokens": None,
            "output_tokens": None,
            "model": None,
            "reported_cost_usd": None,
            "elapsed_seconds": 2.41,
            "status_code": 529,
            "provider_error": "InternalServerError",
            "retry_after_seconds": 3.5,
        },
    ]


async def test_a_batch_refused_part_way_commits_none_of_its_attempts():
    """A batch the database refuses part-way commits none of its attempts.

    This test writes through its own pool, outside the db_conn transaction,
    as production does. Inside a transaction, the rollback that keeps the
    connection usable after the failure would also erase a half-written
    batch, so a half write would look the same as none. Repeating attempt 1
    is only the simplest way to make the last row fail. The test deletes its
    own rows; when the write is all-or-nothing, there are none to delete.
    """
    first = AttemptRecord(
        attempt=1,
        outcome=AttemptOutcome.UNCLASSIFIED,
    )
    second = AttemptRecord(
        attempt=2,
        outcome=AttemptOutcome.UNCLASSIFIED,
    )

    pool = await create_script_pool(min_size=1, max_size=1)
    request_id = uuid.uuid4()

    try:
        with pytest.raises(asyncpg.UniqueViolationError):
            await UsageRepository(pool).record_attempts(
                request_id,
                "extract_paper_facts.v1",
                [first, second, first],
            )

        committed = await pool.fetchval(
            "SELECT count(*) FROM llm_attempts WHERE request_id = $1",
            request_id,
        )
        assert committed == 0
    finally:
        await pool.execute(
            "DELETE FROM llm_attempts WHERE request_id = $1",
            request_id,
        )
        await pool.close()