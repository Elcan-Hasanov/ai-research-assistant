"""Measure which fields of a real extraction response vary between identical calls.

Like scripts/measure_json_compliance.py this IS a measurement script: it makes
N calls with one fixed request and reports, for every field this project reads
from a response, which values it took. The request comes from
extraction_request, the function extract_facts itself uses, so what is
measured is what production sends, temperature included: none is sent. The
article is the fixed paper defined in scripts/probe_structured.py.

WRITE YOUR DECISION RULE BEFORE RUNNING. A field whose assertion you choose
after seeing its values has no decision rule behind it, only a rationalisation.

The calls are made one after another. With a single arm there is no second
arm that a drift in gateway load could be attributed to.

--record saves the first call that came back complete and parseable to
tests/recordings/<prompt identifier>.json: the article it was asked about and
the response body as the gateway sent it. The body is taken on the wire,
below the SDK. Dumping the SDK's Message object instead would add keys the
gateway never sent.

Run:
    python -m scripts.measure_response_variability             # N=30
    python -m scripts.measure_response_variability -n 1        # smoke run
    python -m scripts.measure_response_variability --record    # N=30, then record
"""

import argparse
import asyncio
import json
import logging
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from anthropic import DefaultAsyncHttpxClient

from app.core.config import get_settings
from app.core.llm import CompletionStop, LLMClient, LLMCompletion, LLMError, create_llm_client
from app.generation.extraction import ExtractionValidationError, parse_paper_facts
from app.services.generation_service import GenerationRequest, extraction_request
from scripts.probe_structured import ABSTRACT, TITLE

logging.basicConfig(level=logging.WARNING, force=True)

# Resolved from this file, never from the process CWD, so the script behaves
# the same wherever it is launched from.
RECORDINGS_DIR = Path(__file__).resolve().parents[1] / "tests" / "recordings"

# Shaped like the record ArticleRepository returns, so extraction_request
# takes it as it is, and so does a test that replays the recording.
ARTICLE = {"title": TITLE, "summary": ABSTRACT}

SEPARATOR = "=" * 68


class Wire:
    """Keeps the body of the last HTTP response the SDK received."""

    def __init__(self) -> None:
        self.last_body: bytes | None = None

    async def keep(self, response: httpx.Response) -> None:
        # A response hook runs before the SDK reads the body. Reading it here
        # caches it on the response, and the SDK then reads the same bytes.
        await response.aread()
        self.last_body = response.content


def build_client(wire: Wire) -> LLMClient:
    """The application's client, sending through an HTTP client that keeps what it receives."""
    http_client = DefaultAsyncHttpxClient(event_hooks={"response": [wire.keep]})
    return create_llm_client(http_client=http_client)


class Call:
    """What one call produced."""

    def __init__(self) -> None:
        self.completion: LLMCompletion | None = None
        # "valid", or the ExtractionErrorCause value when the text does not parse.
        self.text: str | None = None
        # Set instead of completion when the call raised.
        self.error: str | None = None
        self.body: bytes | None = None


async def make_call(client: LLMClient, wire: Wire, request: GenerationRequest) -> Call:
    """Send the request once and classify what came back."""
    call = Call()
    wire.last_body = None
    try:
        call.completion = await client.complete(**request.to_completion_kwargs())
    except LLMError as exc:
        call.error = f"api_error status={exc.status_code} provider={exc.provider_error}"
    except Exception as exc:
        # A response this project cannot read: a gateway error inside a 200
        # raises TypeError in to_completion. The body is the evidence.
        call.error = f"unclassified {type(exc).__name__}"
    call.body = wire.last_body

    if call.completion is not None:
        try:
            parse_paper_facts(call.completion.text)
            call.text = "valid"
        except ExtractionValidationError as exc:
            call.text = exc.cause.value
    return call


def describe(call: Call) -> str:
    """One line per call."""
    if call.error is not None:
        if call.error.startswith("unclassified") and call.body is not None:
            return f"{call.error}  body={call.body[:200]!r}"
        return call.error

    c = call.completion
    cost = "-" if c.reported_cost_usd is None else f"{c.reported_cost_usd:.6f}"
    return (
        f"stop={c.stop.value:<18} text={call.text:<16} "
        f"in={c.input_tokens} out={c.output_tokens} cost={cost} model={c.model}"
    )


def print_counts(label: str, values: list) -> None:
    """A field that takes a few distinct values: each value and how often."""
    counts = Counter(values).most_common()
    print(f"  {label:<20}: " + ", ".join(f"{value} x{n}" for value, n in counts))


def print_spread(label: str, values: list[float], note: str = "") -> None:
    """A numeric field: one value if they are all equal, otherwise min, median and max."""
    if len(set(values)) == 1:
        text = f"{values[0]} in every call"
    else:
        text = (
            f"min {min(values)} | median {statistics.median(values)} | "
            f"max {max(values)} ({len(set(values))} distinct)"
        )
    print(f"  {label:<20}: {text}{note}")


def report(calls: list[Call], request: GenerationRequest) -> None:
    answered = [call for call in calls if call.completion is not None]
    print(f"\n  {'with a response':<20}: {len(answered)}/{len(calls)}")

    errors = [call.error for call in calls if call.error is not None]
    if errors:
        print_counts("errors", errors)
    if not answered:
        return

    completions = [call.completion for call in answered]
    print_counts("stop", [c.stop.value for c in completions])
    print_counts("text", [call.text for call in answered])
    print_counts("model", [c.model for c in completions])
    print_spread("input_tokens", [c.input_tokens for c in completions])
    print_spread(
        "output_tokens",
        [c.output_tokens for c in completions],
        note=f"   (max_tokens {request.max_tokens})",
    )

    costs = [c.reported_cost_usd for c in completions]
    present = [cost for cost in costs if cost is not None]
    print(f"  {'reported_cost_usd':<20}: present in {len(present)}/{len(costs)}")
    if present:
        print_spread("  when present", present)


def record(calls: list[Call], request: GenerationRequest) -> Path | None:
    """Save the first complete, parseable response as a test recording."""
    for call in calls:
        c = call.completion
        if c is None or c.stop != CompletionStop.COMPLETED or call.text != "valid":
            continue
        recording = {
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "prompt_identifier": request.prompt_identifier,
            "article": ARTICLE,
            "response": json.loads(call.body),
        }
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        path = RECORDINGS_DIR / f"{request.prompt_identifier}.json"
        path.write_text(
            json.dumps(recording, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path
    return None


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=30, help="number of identical calls")
    parser.add_argument(
        "--record",
        action="store_true",
        help="save one complete, parseable response as a test recording",
    )
    args = parser.parse_args()

    request = extraction_request(ARTICLE)
    path_name = "gateway" if get_settings().llm_base_url else "direct"

    print("\n" + SEPARATOR)
    print(
        f"{args.n} identical calls - {request.prompt_identifier}, "
        f"max_tokens={request.max_tokens}, {path_name} path"
    )
    print(SEPARATOR)

    wire = Wire()
    client = build_client(wire)
    calls: list[Call] = []
    try:
        for i in range(args.n):
            call = await make_call(client, wire, request)
            calls.append(call)
            print(f"  {i + 1:2}/{args.n}  {describe(call)}")
    finally:
        await client.aclose()

    print(SEPARATOR)
    report(calls, request)

    if args.record:
        path = record(calls, request)
        if path is None:
            print("\n  nothing recorded: no call came back complete and parseable")
            return 1
        print(f"\n  recorded            : {path.relative_to(RECORDINGS_DIR.parents[1])}")

    print(SEPARATOR + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))