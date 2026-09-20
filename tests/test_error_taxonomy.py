from app.core.errors import FailureCategory, NotFoundError
from app.core.llm import CompletionStop, LLMError
from app.generation.extraction import ExtractionErrorCause, ExtractionValidationError
from app.prompts.registry import PromptRenderError
from app.services.generation_service import GenerationError, NoSummaryError

_DEFAULT_PUBLIC_MESSAGE = "The request could not be completed."


# ============================================================================
# Extraction & prompt failures — fixed category, no discriminating field
# ============================================================================

def test_extraction_validation_carries_cause_and_stays_internal():
    error = ExtractionValidationError(
        "LLM output validation failed.",
        cause=ExtractionErrorCause.SCHEMA_VIOLATION,
        details=[],
    )

    assert error.category is FailureCategory.INTERNAL
    assert error.log_context() == {"cause": "schema_violation"}
    assert error.public_message == _DEFAULT_PUBLIC_MESSAGE


def test_prompt_render_error_inherits_its_category_from_prompt_error():
    error = PromptRenderError("variable mismatch")

    assert error.category is FailureCategory.INTERNAL
    assert error.log_context() == {}
    assert error.public_message == _DEFAULT_PUBLIC_MESSAGE


# ============================================================================
# LLM boundary — category derived from the provider status code
# ============================================================================

def test_rate_limit_is_upstream_unavailable():
    error = LLMError("LLM request failed", status_code=429, provider_error="RateLimitError")

    assert error.category is FailureCategory.UPSTREAM_UNAVAILABLE
    assert error.log_context() == {"status": 429, "provider": "RateLimitError"}
    assert error.public_message == (
        "The language model service is temporarily unavailable. "
        "Please try again shortly."
    )


def test_missing_status_code_is_upstream_unavailable():
    """A connection or timeout failure never reached HTTP, so status_code is
    absent. That is a branch of its own, not missing data."""
    error = LLMError("LLM request failed", status_code=None, provider_error="APITimeoutError")

    assert error.category is FailureCategory.UPSTREAM_UNAVAILABLE
    assert error.log_context() == {"status": None, "provider": "APITimeoutError"}
    assert error.public_message == (
        "The language model service is temporarily unavailable. "
        "Please try again shortly."
    )


def test_server_error_range_is_upstream_unavailable():
    """503 arrives as InternalServerError: the SDK collapses every code >= 500
    into that class, so only the number distinguishes them."""
    error = LLMError("LLM request failed", status_code=503, provider_error="InternalServerError")

    assert error.category is FailureCategory.UPSTREAM_UNAVAILABLE
    assert error.log_context() == {"status": 503, "provider": "InternalServerError"}


def test_request_too_large_is_unusable_source():
    """The only 4xx the caller's choice of article can produce."""
    error = LLMError("LLM request failed", status_code=413, provider_error="RequestTooLargeError")

    assert error.category is FailureCategory.UNUSABLE_SOURCE
    assert error.log_context() == {"status": 413, "provider": "RequestTooLargeError"}
    assert error.public_message == "This article is too large to send to the language model."


def test_authentication_failure_is_internal():
    """Our credentials, not the caller's request."""
    error = LLMError("LLM request failed", status_code=401, provider_error="AuthenticationError")

    assert error.category is FailureCategory.INTERNAL
    assert error.log_context() == {"status": 401, "provider": "AuthenticationError"}
    assert error.public_message == _DEFAULT_PUBLIC_MESSAGE


# ============================================================================
# Generation — category and message both derived from the stop reason
#
# TOOL_USE and UNKNOWN are deliberately untested: this project defines no
# tools, and an unmapped provider stop reason already lands on UNKNOWN by way
# of _STOP_REASONS. A test pinning either would have to be deleted the moment
# V8 makes tool use legitimate.
# ============================================================================

def test_refusal_is_unusable_source():
    error = GenerationError("Generation failed to complete normally.", stop=CompletionStop.REFUSED)

    assert error.category is FailureCategory.UNUSABLE_SOURCE
    assert error.log_context() == {"stop": "refused"}
    assert error.public_message == "The model declined to produce an answer for this article."


def test_context_overflow_shares_the_category_but_not_the_message():
    """Same category as a refusal, different text. This is the whole reason
    _STOP_OUTCOMES holds both in one table."""
    error = GenerationError(
        "Generation failed to complete normally.", stop=CompletionStop.CONTEXT_OVERFLOW
    )

    assert error.category is FailureCategory.UNUSABLE_SOURCE
    assert error.log_context() == {"stop": "context_overflow"}
    assert error.public_message == "This article is too long for the language model to process."


def test_truncation_is_internal():
    """max_tokens is our configuration; the caller cannot act on it."""
    error = GenerationError("Generation failed to complete normally.", stop=CompletionStop.TRUNCATED)

    assert error.category is FailureCategory.INTERNAL
    assert error.log_context() == {"stop": "truncated"}
    assert error.public_message == _DEFAULT_PUBLIC_MESSAGE


def test_missing_summary_is_unusable_source():
    error = NoSummaryError("Article summary is missing or empty.")

    assert error.category is FailureCategory.UNUSABLE_SOURCE
    assert error.log_context() == {}
    assert error.public_message == "This article has no abstract to work from."


# ============================================================================
# Domain lookup boundary — boundary-independent failure
# ============================================================================

def test_missing_article_is_not_found():
    error = NotFoundError(arxiv_id="fake_999.999")

    assert error.category is FailureCategory.NOT_FOUND
    assert error.public_message == "Article not found: fake_999.999"
    assert str(error) == "Article not found for arxiv_id: fake_999.999"
    assert error.log_context() == {}