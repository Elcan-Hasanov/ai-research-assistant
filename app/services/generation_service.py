from app.core.llm import CompletionStop, LLMClient, LLMCompletion
from app.generation.extraction import PaperFacts, parse_paper_facts
from app.prompts.registry import RenderedPrompt, render
from app.repositories.article_repository import ArticleRepository


class NoSummaryError(Exception):
    """Raised when an article summary is missing or empty."""

    pass


class GenerationError(Exception):
    """Raised when LLM text generation fails or halts unexpectedly."""

    def __init__(self, message: str, stop: CompletionStop) -> None:
        super().__init__(message)
        self.stop = stop


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

    async def extract_facts(self, arxiv_id: str) -> PaperFacts | None:
        record = await self._repository.get_by_arxiv_id(arxiv_id)
        if record is None:
            return None

        prompt = _prepare_prompt(record, "extract_paper_facts.v1")

        completion = await self._client.complete(
            messages=[{"role": "user", "content": prompt.user}],
            max_tokens=500,
            system=prompt.system,
            response_schema=PaperFacts.model_json_schema(),
        )
        _require_completed(completion)

        return parse_paper_facts(completion.text)

    async def summarize_article(self, arxiv_id: str) -> str | None:
        record = await self._repository.get_by_arxiv_id(arxiv_id)
        if record is None:
            return None

        prompt = _prepare_prompt(record, "summarize_article.v1")

        # max_tokens=500 is copied from extract_facts; unmeasured for free-text summary.
        completion = await self._client.complete(
            messages=[{"role": "user", "content": prompt.user}],
            max_tokens=500,
            system=prompt.system,
        )
        _require_completed(completion)

        return completion.text