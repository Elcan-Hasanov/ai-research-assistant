"""Service-level tests for LLM fact extraction.

The database is real: the behaviour under test includes the repository query
and the column-to-template mapping that sits on top of it. The provider is
faked: a real call is non-deterministic, billed, and slow.
"""

import json

import pytest

from app.core.llm import CompletionStop, LLMCompletion
from app.core.errors import NotFoundError
from app.generation.extraction import PaperFacts
from app.services.generation_service import (
    GenerationError,
    GenerationService,
    NoSummaryError,
)
from tests.conftest import FakeLLMClient
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
    )


def truncated(text: str) -> LLMCompletion:
    """Build a fake completion that reports a truncated generation."""
    return LLMCompletion(
        text=text,
        stop=CompletionStop.TRUNCATED,
        input_tokens=247,
        output_tokens=500,
        model="fake/test-llm",
    )


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

async def test_extract_facts_returns_validated_facts(repository, seeded_article):
    client = FakeLLMClient(response=completed(FACTS_JSON))
    service = GenerationService(repository, client)

    facts = await service.extract_facts(seeded_article)

    assert isinstance(facts, PaperFacts)
    assert facts.problem.startswith("Sequence models")
    assert len(facts.contributions) == 2
    assert facts.evaluated is True


async def test_summarize_article_returns_free_text_summary(
    repository, seeded_article
):
    expected_summary = "A three-sentence concise summary of the academic paper."
    client = FakeLLMClient(response=completed(expected_summary))
    service = GenerationService(repository, client)

    summary = await service.summarize_article(seeded_article)

    assert summary == expected_summary

    last_call = client.calls[-1]
    assert last_call["response_schema"] is None
    assert "summarises academic papers" in last_call["system"]

async def test_extract_facts_passes_correct_parameters_to_llm(
    repository, seeded_article
):
    client = FakeLLMClient(response=completed(FACTS_JSON))
    service = GenerationService(repository, client)

    await service.extract_facts(seeded_article)

    assert len(client.calls) == 1
    call = client.calls[0]

    assert call["system"] is not None
    assert call["system"] != call["messages"][0]["content"]
    assert call["response_schema"] == PaperFacts.model_json_schema()
    assert SUMMARY in call["messages"][0]["content"]
    assert TITLE in call["messages"][0]["content"]


@pytest.mark.parametrize("empty_summary", [None, "", "   "])
async def test_extract_facts_raises_no_summary_error_when_summary_is_empty_or_none(
    db_conn, repository, empty_summary
):
    arxiv_id = "2603.00002"
    await insert_article(
        db_conn,
        arxiv_id=arxiv_id,
        title="Title Without Summary",
        summary=empty_summary,
    )

    client = FakeLLMClient()
    service = GenerationService(repository, client)

    with pytest.raises(NoSummaryError):
        await service.extract_facts(arxiv_id)

    assert len(client.calls) == 0


async def test_extract_facts_rejects_truncated_response_even_when_text_parses(
    repository, seeded_article
):
    client = FakeLLMClient(response=truncated(FACTS_JSON))
    service = GenerationService(repository, client)

    with pytest.raises(GenerationError) as exc:
        await service.extract_facts(seeded_article)

    assert exc.value.stop == CompletionStop.TRUNCATED
    assert len(client.calls) == 1


async def test_extract_facts_raises_not_found_when_article_not_found(repository):
    client = FakeLLMClient()
    service = GenerationService(repository, client)

    with pytest.raises(NotFoundError) as caught:
        await service.extract_facts("nonexistent.00000")

    assert caught.value.arxiv_id == "nonexistent.00000"
    assert len(client.calls) == 0