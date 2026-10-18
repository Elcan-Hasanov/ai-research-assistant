"""Generation use cases over stored articles: structured facts and summaries.

Each public method is one use case: it loads the article, renders the prompt,
asks for a completion and decides whether the result is acceptable. Getting
the completion is the same for every use case and happens in one place,
GenerationService._generate, which retries the call and records every attempt.
"""

import logging
import uuid

from app.core.errors import AppError, FailureCategory, NotFoundError
from app.core.llm import CompletionStop, LLMClient, LLMCompletion
from app.core.retry import Retrier
from app.core.usage import AttemptRecord, AttemptRecorder
from app.generation.extraction import PaperFacts, parse_paper_facts
from app.prompts.registry import RenderedPrompt, render
from app.repositories.article_repository import ArticleRepository
from app.repositories.usage_repository import UsageRepository

logger = logging.getLogger(__name__)


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
    """Render a prompt template from an article's title and abstract.

    An article without an abstract gives the model nothing to work from, so it
    is refused here, before any provider call is made.
    """
    summary = record["summary"]
    if not summary or not summary.strip():
        raise NoSummaryError("Article summary is missing or empty.")

    return render(
        template_name,
        title=record["title"],
        abstract=summary,
    )


def _require_completed(completion: LLMCompletion) -> None:
    """Accept only a completion that finished normally.

    Any other stop is rejected even when the text looks usable: a truncated
    answer can still parse.
    """
    if completion.stop != CompletionStop.COMPLETED:
        raise GenerationError(
            "Generation failed to complete normally.",
            stop=completion.stop,
        )


class GenerationService:
    """LLM use cases over stored articles.

    One instance may serve any number of calls, so anything that belongs to a
    single request is created inside that call and never kept on the instance.
    """

    def __init__(
        self,
        repository: ArticleRepository,
        client: LLMClient,
        usage: UsageRepository,
    ) -> None:
        self._repository = repository
        self._client = client
        self._usage = usage
        self._retrier = Retrier()

    async def _save_attempts(
        self,
        request_id: uuid.UUID,
        prompt_identifier: str,
        attempts: list[AttemptRecord],
    ) -> None:
        """Write the attempts of one request, or log them if the write fails.

        By the time this runs, the provider calls are over and the caller's
        outcome is settled; a bookkeeping failure must not change it. The
        records go to the log instead, so the loss is visible rather than
        silent. Exception, not BaseException: a cancellation is not a failed
        write and keeps propagating.
        """
        try:
            await self._usage.record_attempts(request_id, prompt_identifier, attempts)
        except Exception:
            logger.exception(
                "Usage not recorded: request_id=%s prompt=%s attempts=%s",
                request_id,
                prompt_identifier,
                attempts,
            )

    async def _generate(
        self,
        prompt: RenderedPrompt,
        prompt_identifier: str,
        *,
        max_tokens: int,
        response_schema: dict | None = None,
    ) -> LLMCompletion:
        """Send one rendered prompt through the retrier and record every attempt.

        The attempts are saved whether the request succeeds or fails, since a
        failed attempt may still have been billed. The completion comes back as
        the provider gave it: whether it is acceptable is the caller's decision.
        """
        request_id = uuid.uuid4()
        recorder = AttemptRecorder()
        try:
            # The retrier calls the lambda once per attempt, so every attempt
            # sends a fresh request and is observed on its own.
            completion = await self._retrier.run(
                lambda: recorder.observe(
                    self._client.complete(
                        messages=[{"role": "user", "content": prompt.user}],
                        max_tokens=max_tokens,
                        system=prompt.system,
                        response_schema=response_schema,
                    )
                )
            )
        finally:
            await self._save_attempts(request_id, prompt_identifier, recorder.attempts)
        return completion

    async def extract_facts(self, arxiv_id: str) -> PaperFacts:
        """Extract structured facts from one article's abstract."""
        record = await self._repository.get_by_arxiv_id(arxiv_id)
        if record is None:
            raise NotFoundError(arxiv_id=arxiv_id)

        prompt_identifier = "extract_paper_facts.v1"
        prompt = _prepare_prompt(record, prompt_identifier)

        completion = await self._generate(
            prompt,
            prompt_identifier,
            max_tokens=500,
            response_schema=PaperFacts.model_json_schema(),
        )
        _require_completed(completion)

        return parse_paper_facts(completion.text)

    async def summarize_article(self, arxiv_id: str) -> str:
        """Summarize one article's abstract as free text."""
        record = await self._repository.get_by_arxiv_id(arxiv_id)
        if record is None:
            raise NotFoundError(arxiv_id=arxiv_id)

        prompt_identifier = "summarize_article.v1"
        prompt = _prepare_prompt(record, prompt_identifier)

        # max_tokens=500 is copied from extract_facts; unmeasured for free-text summary.
        completion = await self._generate(prompt, prompt_identifier, max_tokens=500)
        _require_completed(completion)

        return completion.text