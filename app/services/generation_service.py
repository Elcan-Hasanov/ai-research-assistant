from app.core.llm import CompletionStop, LLMClient, LLMCompletion
from app.core.errors import FailureCategory, AppError, NotFoundError
from app.generation.extraction import PaperFacts, parse_paper_facts
from app.prompts.registry import RenderedPrompt, render
from app.repositories.article_repository import ArticleRepository


# Category and caller-facing message both derive from `stop`, and they do not
# co-vary: REFUSED and CONTEXT_OVERFLOW share a category but need different
# text. Two separate tables could drift, so one table answers both.
_STOP_OUTCOMES: dict[CompletionStop, tuple[FailureCategory, str | None]] = {
    CompletionStop.REFUSED: (
        FailureCategory.UNUSABLE_SOURCE,
        "The model declined to produce an answer for this article.",
    ),
    CompletionStop.CONTEXT_OVERFLOW: (
        FailureCategory.UNUSABLE_SOURCE,
        "This article is too long for the language model to process.",
    ),
    CompletionStop.TRUNCATED: (FailureCategory.INTERNAL, None),
    CompletionStop.TOOL_USE: (FailureCategory.INTERNAL, None),
    CompletionStop.UNKNOWN: (FailureCategory.INTERNAL, None),
}


class GenerationError(AppError):
    """Raised when LLM text generation fails or halts unexpectedly."""

    def __init__(self, message: str, *, stop: CompletionStop) -> None:
        category, public_message = _STOP_OUTCOMES.get(
            stop, (FailureCategory.INTERNAL, None)
        )
        super().__init__(message, category=category, public_message=public_message)
        self.stop = stop

    def log_context(self) -> dict[str, object]:
        return {"stop": self.stop.value}


class NoSummaryError(AppError):
    """Raised when an article summary is missing or empty."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            category=FailureCategory.UNUSABLE_SOURCE,
            public_message="This article has no abstract to work from.",
        )


def _prepare_prompt(record: dict, template_name: str) -> RenderedPrompt:
    summary = record["summary"]
    if not summary or not summary.strip():
        raise NoSummaryError("Article summary is missing or empty.")

    return render(
        template_name,
        title=record["title"],
        abstract=summary,
    )


def _require_completed(completion: LLMCompletion) -> None:
    if completion.stop != CompletionStop.COMPLETED:
        raise GenerationError(
            "Generation failed to complete normally.",
            stop=completion.stop,
        )


class GenerationService:

    def __init__(self, repository: ArticleRepository, client: LLMClient) -> None:
        self._repository = repository
        self._client = client

    async def extract_facts(self, arxiv_id: str) -> PaperFacts:
        record = await self._repository.get_by_arxiv_id(arxiv_id)
        if record is None:
            raise NotFoundError(arxiv_id=arxiv_id)

        prompt = _prepare_prompt(record, "extract_paper_facts.v1")

        completion = await self._client.complete(
            messages=[{"role": "user", "content": prompt.user}],
            max_tokens=500,
            system=prompt.system,
            response_schema=PaperFacts.model_json_schema(),
        )
        _require_completed(completion)

        return parse_paper_facts(completion.text)

    async def summarize_article(self, arxiv_id: str) -> str:
        record = await self._repository.get_by_arxiv_id(arxiv_id)
        if record is None:
            raise NotFoundError(arxiv_id=arxiv_id)

        prompt = _prepare_prompt(record, "summarize_article.v1")

        # max_tokens=500 is copied from extract_facts; unmeasured for free-text summary.
        completion = await self._client.complete(
            messages=[{"role": "user", "content": prompt.user}],
            max_tokens=500,
            system=prompt.system,
        )
        _require_completed(completion)

        return completion.text