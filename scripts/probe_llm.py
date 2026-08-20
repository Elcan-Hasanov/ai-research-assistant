"""One-shot discovery probe for the LLM provider.

This is NOT a measurement script. No decision rule is written here and no
threshold is derived from its output: a single latency sample is an
order-of-magnitude observation, not a distribution. Real measurement with a
pre-written decision rule happens in Step 10.

Run:
    python -m scripts.probe_llm

BEFORE RUNNING: write down your prediction for every 🔮 marker below.
Reading the output first and then "predicting" is not an exercise.

    🔮 1  What is the SDK's default timeout, and its default retry count?
    🔮 2  How many seconds will a ~300-token answer take, end to end?
    🔮 3  input_tokens vs output_tokens — which is larger, and by how much?
    🔮 4  How many entries will `content` hold, and of what type?
    🔮 5  In the second call (max_tokens=16), what changes in the response
          besides the text being shorter?
"""

import logging
import time

import anthropic
from anthropic import Anthropic

from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

PROMPT = "In two sentences, explain what a vector database is."

# Call-site parameters, deliberately absent from Settings: they vary by task,
# not by deployment environment. See config.py for the rule.
MAX_TOKENS = 300
TRUNCATION_MAX_TOKENS = 16

SEPARATOR = "=" * 62


def report_sdk_defaults(api_key: str, base_url: str | None) -> None:
    if base_url:
        bare_client = Anthropic(api_key=None, auth_token=api_key, base_url=base_url)
    else:
        bare_client = Anthropic(api_key=api_key)

    print("\n" + SEPARATOR)
    print("SDK DEFAULTS   🔮 1")
    print(SEPARATOR)
    print(f"  sdk version         : {anthropic.__version__}")
    print(f"  default timeout     : {bare_client.timeout}")
    print(f"  default max_retries : {bare_client.max_retries}")
    print(f"  AsyncAnthropic      : {hasattr(anthropic, 'AsyncAnthropic')}")
    print(f"  base_url            : {bare_client.base_url}")


def report_call(client: Anthropic, model: str, max_tokens: int, label: str) -> None:
    """Make one call and expose the entire response object."""
    print("\n" + SEPARATOR)
    print(f"{label}   (max_tokens={max_tokens})")
    print(SEPARATOR)

    started = time.perf_counter()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": PROMPT}],
    )
    elapsed = time.perf_counter() - started

    print("\n--- raw response object ---")
    print(response.model_dump_json(indent=2))

    print("\n--- fields that will cross the Step 3 boundary ---")
    print(f"  wall clock (s)      : {elapsed:.2f}")
    print(f"  stop_reason         : {response.stop_reason}")
    print(f"  content block count : {len(response.content)}")
    print(f"  content block types : {[block.type for block in response.content]}")
    print(f"  input_tokens        : {response.usage.input_tokens}")
    print(f"  output_tokens       : {response.usage.output_tokens}")
    print(f"  request id          : {response._request_id}")


def main() -> int:
    settings = get_settings()
    api_key = settings.llm_api_key.get_secret_value()

    report_sdk_defaults(api_key, settings.llm_base_url)

    if settings.llm_base_url:
        logger.info("Routing via gateway: %s", settings.llm_base_url)
        client = Anthropic(
            api_key=None,
            auth_token=api_key,
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
        )
    else:
        client = Anthropic(
            api_key=api_key,
            timeout=settings.llm_timeout_seconds,
        )

    try:
        report_call(client, settings.llm_model, MAX_TOKENS, "CALL 1 — NORMAL   🔮 2 3 4")
        report_call(
            client, settings.llm_model, TRUNCATION_MAX_TOKENS, "CALL 2 — TRUNCATED   🔮 5"
        )
    except anthropic.APIError as exc:
        # Only the exception TYPE is printed. SDK errors can carry the request
        # body — which holds the prompt, and in other shapes, credentials.
        status = getattr(exc, "status_code", "n/a")
        logger.error("Provider call failed: %s (status=%s)", type(exc).__name__, status)
        return 1

    print("\n" + SEPARATOR + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())