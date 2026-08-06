import argparse
import asyncio
import logging
import math
import statistics

from app.core.database import create_script_pool
from app.core.embedding import (
    EmbeddingModel,
    build_embedding_text,
    create_embedding_model,
)
from app.repositories.article_repository import ArticleRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

SAMPLE_TEXT_LIMIT = 10_000


def percentile(sorted_values: list[int], p: float) -> int:
    if not sorted_values:
        return 0
    index = min(int(len(sorted_values) * p), len(sorted_values) - 1)
    return sorted_values[index]


async def fetch_texts() -> list[str]:
    pool = await create_script_pool(min_size=1, max_size=2)
    try:
        repo = ArticleRepository(pool)
        records = await repo.list_articles(limit=SAMPLE_TEXT_LIMIT, offset=0)
        return [
            build_embedding_text(record["title"], record["summary"])
            for record in records
        ]
    finally:
        await pool.close()


def report_model_facts(model: EmbeddingModel) -> None:
    print("\n" + "=" * 62)
    print("MODEL FACTS")
    print("=" * 62)
    print(f"  name              : {model.model_name}")
    print(f"  output dimension  : {model.dimension}")
    print(f"  max_seq_length    : {model.max_seq_length}   <- ST truncates HERE")


def report_token_distribution(model: EmbeddingModel, texts: list[str]) -> None:
    lengths = sorted(model.count_tokens(text) for text in texts)
    limit = model.max_seq_length
    truncated = sum(1 for length in lengths if length > limit)

    print("\n" + "=" * 62)
    print(f"TOKEN LENGTH DISTRIBUTION  (n = {len(lengths)})")
    print("=" * 62)
    print(f"  min               : {lengths[0]}")
    print(f"  median            : {int(statistics.median(lengths))}")
    print(f"  p90               : {percentile(lengths, 0.90)}")
    print(f"  p95               : {percentile(lengths, 0.95)}")
    print(f"  max               : {lengths[-1]}")
    print(f"\n  limit             : {limit}")
    print(
        f"  TRUNCATED         : {truncated} / {len(lengths)} "
        f"({truncated / len(lengths) * 100:.1f}%)"
    )

    if truncated:
        lost = [length - limit for length in lengths if length > limit]
        print(f"  avg tokens lost   : {int(statistics.mean(lost))}")
        print(f"  max tokens lost   : {max(lost)}")
        print("\n  -> This ratio provides the quantitative rationale for chunking in V5.")
    else:
        print("\n  -> No truncation observed for this corpus.")


def report_normalization(model: EmbeddingModel, texts: list[str]) -> None:
    sample = texts[:16]
    raw_vectors = model.encode_documents(sample, normalize=False)
    norms = [math.sqrt(sum(value * value for value in vec)) for vec in raw_vectors]

    print("\n" + "=" * 62)
    print("NORMALIZATION CHECK  (raw model output, normalize=False)")
    print("=" * 62)
    print(f"  min L2 norm       : {min(norms):.6f}")
    print(f"  max L2 norm       : {max(norms):.6f}")

    natively_normalized = all(abs(norm - 1.0) < 1e-3 for norm in norms)
    if natively_normalized:
        print("\n  -> Model normalizes NATIVELY.")
        print("     cosine == inner product, L2 is monotonically equivalent.")
    else:
        print("\n  -> Model DOES NOT normalize natively.")
        print("     Operator selection is critical. encode(normalize=True) is required.")
    print("=" * 62 + "\n")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Override model name")
    args = parser.parse_args()

    model = create_embedding_model(args.model)
    report_model_facts(model)

    texts = await fetch_texts()
    if not texts:
        logger.error("No articles in database. Run scripts.ingest_arxiv first.")
        return 1

    report_token_distribution(model, texts)
    report_normalization(model, texts)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))