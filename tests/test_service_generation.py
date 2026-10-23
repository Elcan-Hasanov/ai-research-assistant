"""Service-level tests for LLM generation and the usage records it leaves.

The database is real: the behaviour under test includes the repository query,
the column-to-template mapping that sits on top of it, and the attempt rows the
service writes. The provider is faked: a real call is non-deterministic,
billed, and slow.
"""

import json
import logging
from operator import itemgetter

import pytest

from app.core.errors import NotFoundError
from app.core.llm import CompletionStop, LLMCompletion, LLMError
from app.generation.extraction import PaperFacts
from app.prompts.registry import render
from app.services.generation_service import (
    GenerationError,
    GenerationService,
    NoSummaryError,
)
from tests.conftest import FakeLLMClient, recorded_attempts
from tests.factories import insert_article

pytestmark = pytest.mark.db


ARXIV_ID = "2603.00001"
TITLE = "Attention Is All You Need"
SUMMARY = (
    "We propose the Transformer, a network architecture based solely on "
    "attention mechanisms, dispensing with recurrence entirely."
)

FACTS_JSON = json.dumps(
    {
        "problem": "Sequence models rely on recurrence, which limits parallelism.",
        "contributions": [
            "An architecture based only on attention.",
            "Better translation quality at lower training cost.",
        ],
        "evaluated": True,
    }
)


# --- Helper Functions (Grouped Together) ---


def completed(text: str) -> LLMCompletion:
    """Build a fake completion that reports a normally finished generation."""
    return LLMCompletion(
        text=text,
        stop=CompletionStop.COMPLETED,
        input_tokens=247,
        output_tokens=88,
        model="fake/test-llm",
        elapsed_seconds=1.76,
    )


def truncated(text: str) -> LLMCompletion:
    """Build a fake completion that reports a truncated generation."""
    return LLMCompletion(
        text=text,
        stop=CompletionStop.TRUNCATED,
        input_tokens=247,
        output_tokens=500,
        model="fake/test-llm",
        elapsed_seconds=1.76,
    )


def unavailable(status_code: int) -> LLMError:
    """A retryable upstream failure that asks for no wait, so the shipped
    retrier moves on at once. A new object every call: a raised exception
    keeps its traceback, and one reused across attempts would carry them all.
    """
    return LLMError("LLM request failed", status_code=status_code, retry_after=0.0)


def select_columns(rows: list[dict], *columns: str) -> list[dict]:
    """The named columns of each row, so a test compares only what it is about."""
    return [{column: row[column] for column in columns} for row in rows]


# --- Fixtures ---


@pytest.fixture
async def seeded_article(db_conn) -> str:
    """One article that has a non-empty summary."""
    await insert_article(
        db_conn,
        arxiv_id=ARXIV_ID,
        title=TITLE,
        summary=SUMMARY,
    )
    return ARXIV_ID


# --- Tests ---


async def test_extract_facts_returns_validated_facts(
    repository, seeded_article, usage_repository
):
    client = FakeLLMClient(response=completed(FACTS_JSON))
    service = GenerationService(repository, client, usage_repository)

    facts = await service.extract_facts(seeded_article)

    assert isinstance(facts, PaperFacts)
    assert facts.problem.startswith("Sequence models")
    assert len(facts.contributions) == 2
    assert facts.evaluated is True


async def test_summarize_article_returns_free_text_summary(
    repository, seeded_article, usage_repository
):
    expected_summary = "A three-sentence concise summary of the academic paper."
    client = FakeLLMClient(response=completed(expected_summary))
    service = GenerationService(repository, client, usage_repository)

    summary = await service.summarize_article(seeded_article)

    assert summary == expected_summary


async def test_extract_facts_sends_the_expected_request(
    repository, seeded_article, usage_repository
):
    """complete() receives exactly this request, so no part of it can change unseen.

    Rendering the expectation from TITLE and SUMMARY also pins which column
    fills which template variable. The prompt text is rendered rather than
    copied: what a template says belongs to the prompt's version, not to this
    test.
    """
    client = FakeLLMClient(response=completed(FACTS_JSON))
    service = GenerationService(repository, client, usage_repository)

    await service.extract_facts(seeded_article)

    prompt = render("extract_paper_facts.v1", title=TITLE, abstract=SUMMARY)
    assert client.calls == [
        {
            "messages": [{"role": "user", "content": prompt.user}],
            "max_tokens": 500,
            "system": prompt.system,
            "response_schema": PaperFacts.model_json_schema(),
            "model": None,
            "temperature": None,
        }
    ]


async def test_summarize_article_sends_the_expected_request(
    repository, seeded_article, usage_repository
):
    """The summary counterpart of test_extract_facts_sends_the_expected_request."""
    client = FakeLLMClient(response=completed("A concise summary of the paper."))
    service = GenerationService(repository, client, usage_repository)

    await service.summarize_article(seeded_article)

    prompt = render("summarize_article.v1", title=TITLE, abstract=SUMMARY)
    assert client.calls == [
        {
            "messages": [{"role": "user", "content": prompt.user}],
            "max_tokens": 500,
            "system": prompt.system,
            "response_schema": None,
            "model": None,
            "temperature": None,
        }
    ]


@pytest.mark.parametrize("empty_summary", [None, "", "   "])
async def test_extract_facts_raises_no_summary_error_when_summary_is_empty_or_none(
    db_conn, repository, empty_summary, usage_repository
):
    arxiv_id = "2603.00002"
    await insert_article(
        db_conn,
        arxiv_id=arxiv_id,
        title="Title Without Summary",
        summary=empty_summary,
    )

    client = FakeLLMClient()
    service = GenerationService(repository, client, usage_repository)

    with pytest.raises(NoSummaryError):
        await service.extract_facts(arxiv_id)

    assert len(client.calls) == 0


async def test_extract_facts_rejects_truncated_response_even_when_text_parses(
    repository, seeded_article, usage_repository
):
    client = FakeLLMClient(response=truncated(FACTS_JSON))
    service = GenerationService(repository, client, usage_repository)

    with pytest.raises(GenerationError) as exc:
        await service.extract_facts(seeded_article)

    assert exc.value.stop == CompletionStop.TRUNCATED
    assert len(client.calls) == 1


async def test_extract_facts_raises_not_found_when_article_not_found(
    repository, usage_repository
):
    client = FakeLLMClient()
    service = GenerationService(repository, client, usage_repository)

    with pytest.raises(NotFoundError) as caught:
        await service.extract_facts("nonexistent.00000")

    assert caught.value.arxiv_id == "nonexistent.00000"
    assert len(client.calls) == 0


async def test_extract_facts_retries_an_unavailable_upstream(
    repository, seeded_article, usage_repository
):
    """The provider call goes through the retry layer the service ships with:
    an unavailable first attempt is followed by a second, and the facts come
    from that one."""
    client = FakeLLMClient(outcomes=[unavailable(429), completed(FACTS_JSON)])
    service = GenerationService(repository, client, usage_repository)

    facts = await service.extract_facts(seeded_article)

    assert len(client.calls) == 2
    assert isinstance(facts, PaperFacts)


async def test_summarize_article_retries_an_unavailable_upstream(
    repository, seeded_article, usage_repository
):
    """The same holds for the summary: the first attempt fails as unavailable,
    and the summary comes from the second."""
    expected_summary = "A three-sentence concise summary of the academic paper."
    client = FakeLLMClient(outcomes=[unavailable(429), completed(expected_summary)])
    service = GenerationService(repository, client, usage_repository)

    summary = await service.summarize_article(seeded_article)

    assert len(client.calls) == 2
    assert summary == expected_summary


# --- Usage recording ---


class _UnreachableUsageRepository:
    """Stands in for a usage store the service cannot reach: every write fails."""

    async def record_attempts(self, request_id, prompt_identifier, attempts) -> None:
        raise ConnectionRefusedError("usage store unreachable")


async def test_a_retried_request_records_every_attempt_under_one_id(
    repository, seeded_article, usage_repository, db_conn
):
    """Every attempt of a retried request is recorded under one request id,
    the failed one included, in the order it was made."""
    client = FakeLLMClient(outcomes=[unavailable(529), completed(FACTS_JSON)])
    service = GenerationService(repository, client, usage_repository)

    await service.extract_facts(seeded_article)

    rows = await recorded_attempts(db_conn)
    assert len({row["request_id"] for row in rows}) == 1
    assert select_columns(
        rows, "attempt", "prompt_identifier", "outcome", "stop", "status_code"
    ) == [
        {
            "attempt": 1,
            "prompt_identifier": "extract_paper_facts.v1",
            "outcome": "llm_error",
            "stop": None,
            "status_code": 529,
        },
        {
            "attempt": 2,
            "prompt_identifier": "extract_paper_facts.v1",
            "outcome": "response",
            "stop": "completed",
            "status_code": None,
        },
    ]


async def test_attempts_are_recorded_when_retries_run_out(
    repository, seeded_article, usage_repository, db_conn
):
    """When the retries run out, the attempts are still recorded before the
    error leaves: each of them may have been billed."""
    client = FakeLLMClient(
        outcomes=[unavailable(429), unavailable(529), unavailable(503)]
    )
    service = GenerationService(repository, client, usage_repository)

    with pytest.raises(LLMError):
        await service.extract_facts(seeded_article)

    rows = await recorded_attempts(db_conn)
    assert len({row["request_id"] for row in rows}) == 1
    assert select_columns(rows, "attempt", "outcome", "status_code") == [
        {"attempt": 1, "outcome": "llm_error", "status_code": 429},
        {"attempt": 2, "outcome": "llm_error", "status_code": 529},
        {"attempt": 3, "outcome": "llm_error", "status_code": 503},
    ]


async def test_each_call_is_recorded_as_its_own_request(
    repository, seeded_article, usage_repository, db_conn
):
    """Two calls on one service are two requests: each gets its own id,
    starts again at attempt 1 and carries its own prompt."""
    client = FakeLLMClient(
        outcomes=[completed(FACTS_JSON), completed("A short summary.")]
    )
    service = GenerationService(repository, client, usage_repository)

    await service.extract_facts(seeded_article)
    await service.summarize_article(seeded_article)

    rows = await recorded_attempts(db_conn)
    assert len({row["request_id"] for row in rows}) == 2
    # Request ids are random, so the two requests' rows come back in either
    # order: sorting by prompt gives them one order to compare against.
    assert sorted(
        select_columns(rows, "prompt_identifier", "attempt"),
        key=itemgetter("prompt_identifier"),
    ) == [
        {"prompt_identifier": "extract_paper_facts.v1", "attempt": 1},
        {"prompt_identifier": "summarize_article.v1", "attempt": 1},
    ]


async def test_a_failed_usage_write_keeps_the_result_and_logs_the_attempts(
    repository, seeded_article, caplog
):
    """A usage store the service cannot reach changes nothing for the caller:
    the facts come back, and the attempts go to an ERROR log instead."""
    client = FakeLLMClient(outcomes=[completed(FACTS_JSON)])
    service = GenerationService(repository, client, _UnreachableUsageRepository())

    # Scoped to the service's logger, so the capture does not depend on how
    # logging is configured elsewhere in the test session.
    with caplog.at_level(logging.ERROR, logger="app.services.generation_service"):
        facts = await service.extract_facts(seeded_article)

    assert isinstance(facts, PaperFacts)
    assert (
        facts.problem == "Sequence models rely on recurrence, which limits parallelism."
    )

    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1

    message = errors[0].getMessage()
    assert message.startswith("Usage not recorded:")
    assert "prompt=extract_paper_facts.v1" in message
    assert "input_tokens=247" in message
    
    # Only logger.exception attaches the exception: logged with logger.error,
    # the record would carry no traceback of the failed write.
    assert errors[0].exc_info is not None
    assert errors[0].exc_info[0] is ConnectionRefusedError