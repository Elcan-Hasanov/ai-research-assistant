"""One-shot discovery probe for structured output.

This is NOT a measurement script. No decision rule is written here and no
threshold is derived from its output. It answers three questions that cannot
be answered by reading code, and it captures one real payload for the tests.

Run:
    python -m scripts.probe_structured

BEFORE RUNNING: write down your prediction for every marker below.

    P1  With no constraint at all, will the model's text be parseable JSON,
        or will it carry a preamble / markdown fence around it?
    P2  Does the gateway accept `output_config`? If it refuses, does it
        refuse loudly (an error) or silently (a normal answer)?
    P3  If the gateway accepts it, how many content blocks come back, and
        of what type? Does `to_completion` still find the payload?
"""

import json
import logging

import anthropic
from anthropic import Anthropic

from app.core.config import get_settings
from app.core.llm import to_completion
from app.prompts.registry import render

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

MAX_TOKENS = 500
SEPARATOR = "=" * 62

# A fixed paper, hardcoded so the probe needs no database and stays repeatable.
TITLE = "Attention Is All You Need"
ABSTRACT = (
    "The dominant sequence transduction models are based on complex recurrent "
    "or convolutional neural networks that include an encoder and a decoder. "
    "We propose a new simple network architecture, the Transformer, based "
    "solely on attention mechanisms, dispensing with recurrence and "
    "convolutions entirely. Experiments on two machine translation tasks show "
    "these models to be superior in quality while being more parallelizable "
    "and requiring significantly less time to train."
)

# Hand-written on purpose. The Pydantic model does not exist yet, and a probe
# that depends on the thing it is probing for cannot report a clean result.
SCHEMA = {
    "type": "object",
    "properties": {
        "problem": {"type": "string"},
        "contributions": {"type": "array", "items": {"type": "string"}},
        "evaluated": {"type": "boolean"},
    },
    "required": ["problem", "contributions", "evaluated"],
    "additionalProperties": False,
}


def report(response, label: str) -> None:
    """Expose the whole response, then the five fields that cross the boundary."""
    print("\n" + SEPARATOR)
    print(label)
    print(SEPARATOR)

    print("  block count : ", len(response.content))
    print("  block types : ", [block.type for block in response.content])
    print("  stop_reason : ", response.stop_reason)
    print("  stop_details: ", getattr(response, "stop_details", None))
    print("  tokens      : ", response.usage.input_tokens, "->", response.usage.output_tokens)

    completion = to_completion(response)
    print("  to_completion().stop        : ", completion.stop)
    print("  to_completion().text length : ", len(completion.text))
    print("\n--- text, verbatim ---")
    print(repr(completion.text))

    print("\n--- json.loads on that text ---")
    try:
        parsed = json.loads(completion.text)
        print("  parsed OK, keys:", sorted(parsed) if isinstance(parsed, dict) else type(parsed))
    except json.JSONDecodeError as exc:
        print(f"  JSONDecodeError: {exc.msg} (pos {exc.pos})")


def main() -> int:
    settings = get_settings()
    credential = settings.llm_api_key.get_secret_value()

    if settings.llm_base_url:
        client = Anthropic(
            api_key=None,
            auth_token=credential,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
    else:
        client = Anthropic(
            api_key=credential,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    prompt = render("extract_paper_facts.v1", title=TITLE, abstract=ABSTRACT)
    payload = {
        "model": settings.llm_model,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt.user}],
    }
    if prompt.system is not None:
        payload["system"] = prompt.system

    try:
        report(client.messages.create(**payload), "CALL 1 - PROMPT ONLY   P1")
    except anthropic.APIError as exc:
        logger.error("Call 1 failed: %s (status=%s)",
                     type(exc).__name__, getattr(exc, "status_code", "n/a"))
        return 1

    print("\n" + SEPARATOR)
    print("CALL 2 - WITH output_config   P2 P3")
    print(SEPARATOR)
    try:
        constrained = client.messages.create(
            **payload,
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
    except anthropic.APIError as exc:
        # Only the type and status. SDK errors can echo the request body,
        # and that body holds the prompt.
        print(f"  REFUSED: {type(exc).__name__} (status={getattr(exc, 'status_code', 'n/a')})")
        print("  -> the gateway does not accept output_config on this path")
        print("\n" + SEPARATOR + "\n")
        return 0

    report(constrained, "CALL 2 - WITH output_config   P2 P3")
    print("\n" + SEPARATOR + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())