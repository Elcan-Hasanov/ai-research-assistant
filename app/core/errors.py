from enum import Enum


class FailureCategory(str, Enum):
    """What the system does about a failure, in our own vocabulary.

    Not the provider's vocabulary and not HTTP's: the translation to a status
    code happens at the outermost boundary.

    UNUSABLE_SOURCE is not "the caller sent bad data" — the caller sends an
    arxiv_id and it is valid. It means the article that id names cannot be
    turned into the output this endpoint promises, and the only party who can
    change that is the caller, by naming a different one. NOT_FOUND is the
    narrower case where no article answers to that id at all.
    """

    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    INTERNAL = "internal"
    UNUSABLE_SOURCE = "unusable_source"
    NOT_FOUND = "not_found"


class AppError(Exception):
    """Base for every failure this application classifies.

    Carries two messages with two different audiences. `message` is ours: it
    goes to the log and may name templates, models or internal state. It is
    read with str(exc); there is no .message attribute.

    `public_message` crosses the network to the caller. It holds fixed text
    and, at most, values the caller supplied in the request itself — never a
    provider response, model output or internal state.
    """

    def __init__(
        self,
        message: str,
        *,
        category: FailureCategory,
        public_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.public_message = public_message or "The request could not be completed."

    def log_context(self) -> dict[str, object]:
        """Diagnostic fields for the log line, in our own vocabulary.

        Subclasses override this to surface discriminating data their message
        cannot carry — a fixed message is what creates the need. Everything
        returned here is written to the log, so it holds only values we
        produced: our enums, status codes, provider type names. Never model
        output, prompt text or a provider response body.
        """
        return {}


class NotFoundError(AppError):
    """The article a caller named does not exist.

    The only error type here rather than in the module that raises it: every
    other type belongs to one boundary — the LLM client, the prompt registry,
    the extraction parser. This one belongs to any lookup, and two services in
    app/services will raise it. Defining it in either of them would make one
    service import the other.

    Its public message interpolates the arxiv_id: that value came from the
    caller's own URL, so echoing it back is not a leak.
    """

    def __init__(self, arxiv_id: str) -> None:
        super().__init__(
            f"Article not found for arxiv_id: {arxiv_id}",
            category=FailureCategory.NOT_FOUND,
            public_message=f"Article not found: {arxiv_id}",
        )
        self.arxiv_id = arxiv_id