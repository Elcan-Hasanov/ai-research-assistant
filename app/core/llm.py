import logging
from enum import Enum
from typing import Any

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import Message
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CompletionStop(str, Enum):
    """Provider-agnostic reason a generation stopped."""

    COMPLETED = "completed"
    TRUNCATED = "truncated"
    TOOL_USE = "tool_use"
    REFUSED = "refused"
    CONTEXT_OVERFLOW = "context_overflow"
    UNKNOWN = "unknown"


# Provider vocabulary on the left, ours on the right. A value the provider adds
# unilaterally falls through to UNKNOWN rather than breaking working code.
# Only reasons with a consumer are mapped: "pause_turn" belongs to agent loops
# and has none yet.
_STOP_REASONS: dict[str, CompletionStop] = {
    "end_turn": CompletionStop.COMPLETED,
    "stop_sequence": CompletionStop.COMPLETED,
    "max_tokens": CompletionStop.TRUNCATED,
    "tool_use": CompletionStop.TOOL_USE,
    "refusal": CompletionStop.REFUSED,
    "model_context_window_exceeded": CompletionStop.CONTEXT_OVERFLOW,
}


class LLMCompletion(BaseModel):
    """A single generation, expressed in this project's own terms."""

    text: str
    stop: CompletionStop
    input_tokens: int
    output_tokens: int
    model: str


class LLMError(Exception):
    """Provider-agnostic failure raised at the LLM boundary."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        provider_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider_error = provider_error


def to_completion(message: Message) -> LLMCompletion:
    """Translate an SDK response object into this project's completion type."""
    text = "".join(
        block.text for block in message.content if block.type == "text"
    )
    return LLMCompletion(
        text=text,
        stop=_STOP_REASONS.get(message.stop_reason, CompletionStop.UNKNOWN),
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
        model=message.model,
    )


class LLMClient:
    """The single place in this application that talks to the LLM SDK."""

    def __init__(self, client: AsyncAnthropic, default_model: str) -> None:
        self._client = client
        self._default_model = default_model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        model: str | None = None,
        system: str | None = None,
        temperature: float | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> LLMCompletion:
        """Perform exactly one provider call and return its result.

        Args:
            response_schema: A plain JSON Schema object. The caller supplies the
                schema itself; wrapping it in the provider's envelope is this
                method's job, so no caller needs to know that envelope's shape.
                Constraining generation raises the odds of parseable output but
                proves nothing about it: the response is validated locally either
                way.

        Raises:
            LLMError: The provider call failed. Carries the HTTP status and the
                provider exception's type name as data, so callers can classify
                without importing the SDK.
        """
        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        # Optional keys are added only when supplied. Sending an explicit None
        # is not the same as omitting the key, and can be rejected as a 400.
        if system is not None:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature
        if response_schema is not None:
            payload["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": response_schema,
                }
            }

        try:
            message = await self._client.messages.create(**payload)
        except anthropic.APIError as exc:
            # A fixed string, never str(exc): SDK errors can echo the request
            # body back, and that body holds the prompt.
            raise LLMError(
                "LLM request failed",
                status_code=getattr(exc, "status_code", None),
                provider_error=type(exc).__name__,
            ) from exc

        return to_completion(message)


def create_llm_client(model: str | None = None) -> LLMClient:
    """Factory that builds the SDK client with this project's transport policy."""
    settings = get_settings()
    name = model or settings.llm_model
    credential = settings.llm_api_key.get_secret_value()

    # The SDK's own retry policy is switched off on both paths. Left at its
    # default of 2, it would multiply with the retry budget added in Step 8:
    # a three-attempt budget would become nine billed calls.
    if settings.llm_base_url:
        # Gateway path: bearer token, not x-api-key. api_key is passed as None
        # explicitly so the SDK does not fall back to the environment.
        sdk_client = AsyncAnthropic(
            api_key=None,
            auth_token=credential,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
    else:
        sdk_client = AsyncAnthropic(
            api_key=credential,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    logger.info(
        "LLM client ready — model=%s, gateway=%s",
        name,
        bool(settings.llm_base_url),
    )
    return LLMClient(sdk_client, name)