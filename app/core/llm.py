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
    UNKNOWN = "unknown"


_STOP_REASONS: dict[str, CompletionStop] = {
    "end_turn": CompletionStop.COMPLETED,
    "stop_sequence": CompletionStop.COMPLETED,
    "max_tokens": CompletionStop.TRUNCATED,
    "tool_use": CompletionStop.TOOL_USE,
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
    ) -> LLMCompletion:
        """Perform exactly one provider call and return its result."""
        payload: dict[str, Any] = {
            "model": model or self._default_model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system is not None:
            payload["system"] = system
        if temperature is not None:
            payload["temperature"] = temperature

        try:
            message = await self._client.messages.create(**payload)
        except anthropic.APIError as exc:
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

    if settings.llm_base_url:
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