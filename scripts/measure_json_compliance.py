"""Measure how reliably each mechanism produces directly parseable JSON.

Unlike scripts/probe_structured.py this IS a measurement script: it makes N
repeated calls on a fixed input and reports rates, not samples.

WRITE YOUR DECISION RULE BEFORE RUNNING. A rate you interpret after seeing it
is not a decision rule, it is a rationalisation.

Calls are interleaved (A, B, A, B, ...) rather than blocked (ten of A, then
ten of B). A blocked run attributes any drift in gateway load to whichever
arm happened to be running at the time. It did exactly that once: one arm
reported a 12.34s mean and the other 1.88s, a causal story was built on the
difference, and re-running the same configuration produced 1.65s for the
supposedly slow arm.

Run:
    python -m scripts.measure_json_compliance            # N=10 per arm
    python -m scripts.measure_json_compliance -n 3
"""

import argparse
import asyncio
import json
import logging
import statistics
import time

from app.core.llm import LLMError, create_llm_client
from app.generation.extraction import PaperFacts
from app.prompts.registry import render
from scripts.probe_structured import ABSTRACT, TITLE

logging.basicConfig(level=logging.WARNING, force=True)
logging.getLogger("httpx").setLevel(logging.WARNING)

MAX_TOKENS = 500
SEPARATOR = "=" * 68


def classify(text: str) -> str:
    """Name the failure shape, so the report distinguishes causes."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        stripped = text.strip()
        if stripped.startswith("```"):
            return "fence"
        if "{" in stripped and not stripped.startswith("{"):
            return "preamble"
        return "unparseable"
    return "ok" if isinstance(parsed, dict) else "not_an_object"


class Arm:
    """One measurement arm: the schema it sends and what its calls produced."""

    def __init__(self, label: str, response_schema: dict | None) -> None:
        self.label = label
        self.response_schema = response_schema
        self.results: list[str] = []
        self.input_tokens: list[int] = []
        self.elapsed: list[float] = []

    async def call_once(self, client, prompt) -> str:
        """Make one call, record it, and return a one-line description."""
        started = time.perf_counter()
        try:
            completion = await client.complete(
                messages=[{"role": "user", "content": prompt.user}],
                max_tokens=MAX_TOKENS,
                system=prompt.system,
                response_schema=self.response_schema,
            )
        except LLMError as exc:
            # The fixed message carries nothing; the status and the provider
            # exception's type name are why LLMError holds them as data.
            self.results.append("api_error")
            return (
                f"API ERROR      status={exc.status_code} "
                f"provider={exc.provider_error}"
            )

        # Only successful calls contribute a duration. A failed call's
        # elapsed time measures the failure, not the generation.
        self.elapsed.append(time.perf_counter() - started)

        verdict = classify(completion.text)
        self.results.append(verdict)
        self.input_tokens.append(completion.input_tokens)
        return (
            f"{verdict:14} stop={completion.stop.value:16} "
            f"in={completion.input_tokens}"
        )

    def report(self) -> None:
        total = len(self.results)
        ok = self.results.count("ok")
        print(f"\n  {self.label}")
        print(f"    directly parseable : {ok}/{total}")

        shapes = {
            v: self.results.count(v)
            for v in sorted(set(self.results))
            if v != "ok"
        }
        if shapes:
            print(f"    failure shapes     : {shapes}")

        if self.input_tokens:
            low, high = min(self.input_tokens), max(self.input_tokens)
            span = str(low) if low == high else f"{low}-{high}"
            print(f"    input tokens       : {span}")

        if self.elapsed:
            # min / median / max, never the mean. A single tail observation
            # moved the mean of ten calls by 64% while leaving the median
            # untouched — the mean describes neither the typical call nor the
            # worst one. No percentile is printed either: p95 computed from
            # ten samples interpolates past the largest value actually seen,
            # which is inventing data. With this sample size the observed max
            # is the strongest honest statement about the tail.
            print(
                f"    latency (s)        : "
                f"min {min(self.elapsed):5.2f} | "
                f"median {statistics.median(self.elapsed):5.2f} | "
                f"max {max(self.elapsed):5.2f}  <- worst in this run"
            )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=10, help="calls per arm")
    args = parser.parse_args()

    client = create_llm_client()
    prompt = render("extract_paper_facts.v1", title=TITLE, abstract=ABSTRACT)

    arms = [
        Arm("A  prompt only  ", None),
        Arm("B  output_config", PaperFacts.model_json_schema()),
    ]

    print("\n" + SEPARATOR)
    print(
        f"INTERLEAVED RUN — {args.n} per arm, "
        f"{args.n * len(arms)} calls total"
    )
    print(SEPARATOR)

    for i in range(args.n):
        for arm in arms:
            line = await arm.call_once(client, prompt)
            print(f"  {i + 1:2}/{args.n}  {arm.label}  {line}")
        print()

    print(SEPARATOR)
    for arm in arms:
        arm.report()
    print("\n" + SEPARATOR + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))