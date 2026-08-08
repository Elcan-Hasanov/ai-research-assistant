import argparse
import asyncio
import logging

from app.core.config import get_settings
from app.core.database import create_script_pool
from app.core.embedding import (
    EmbeddingModel,
    build_embedding_text,
    compute_content_hash,
    create_embedding_model,
)
from app.repositories.article_repository import ArticleRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)


async def _encode(model: EmbeddingModel, texts: list[str], batch_size: int) -> list[list[float]]:
    """Offloads CPU-bound inference out of the event loop to a separate thread worker."""
    return await asyncio.to_thread(model.encode_documents, texts, batch_size)


async def _write_batch(
    pool, model_name: str, rows: list[tuple[str, str, list[float]]]
) -> None:
    """Persists a single batch within an isolated transaction using an acquired connection."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            write_repo = ArticleRepository(conn)
            await write_repo.upsert_embeddings(model_name, rows)


async def backfill_missing(
    pool,
    read_repo: ArticleRepository,
    model_name: str,
    model: EmbeddingModel,
    fetch_size: int,
    batch_size: int,
) -> int:
    """Phase 1 — Embeds articles that have no existing embeddings for the target model.

    Consuming query behavior: Processed rows automatically drop out of the candidate set in 
    subsequent fetches, so `fetch_missing_embeddings` does not require OFFSET. Without database
    writes, this loop would be infinite — which is why dry-run uses `count_missing_embeddings`.
    """
    total = 0

    while True:
        batch = await read_repo.fetch_missing_embeddings(model_name, fetch_size)
        if not batch:
            break

        prepared = []
        for article in batch:
            text = build_embedding_text(article["title"], article["summary"])
            if not text:
                logger.warning("Skipped (empty text): %s", article["arxiv_id"])
                continue
            prepared.append((article["arxiv_id"], text))

        if not prepared:
            logger.error(
                "%d articles fetched but none contain processable text — "
                "aborting to prevent infinite loop.",
                len(batch),
            )
            break

        texts = [text for _, text in prepared]
        vectors = await _encode(model, texts, batch_size)

        write_rows = [
            (arxiv_id, compute_content_hash(text), vector)
            for (arxiv_id, text), vector in zip(prepared, vectors)
        ]
        await _write_batch(pool, model_name, write_rows)

        total += len(write_rows)
        logger.info("Phase 1 — %d articles embedded (total: %d)", len(write_rows), total)

    return total


async def backfill_stale(
    pool,
    read_repo: ArticleRepository,
    model_name: str,
    model: EmbeddingModel | None,
    fetch_size: int,
    batch_size: int,
    dry_run: bool = False,
) -> int:
    """Phase 2 — Updates articles whose content hash differs from the stored hash.

    Non-consuming query behavior: Updated rows still satisfy the "embedding exists" filter.
    Pagination via ORDER BY + OFFSET is mandatory to avoid infinite loops.

    Staleness checks rely on Python-level text building logic and cannot be performed purely in SQL;
    therefore, counting in dry-run mode traverses this loop. When dry_run=True, inference and
    writes are skipped, and `model` can be None.
    """
    if not dry_run and model is None:
        raise ValueError("backfill_stale: model parameter is required when dry_run=False")

    total = 0
    offset = 0

    while True:
        batch = await read_repo.fetch_existing_embeddings(model_name, fetch_size, offset)
        if not batch:
            break
        offset += len(batch)

        prepared = []
        for article in batch:
            text = build_embedding_text(article["title"], article["summary"])
            if not text:
                continue
            current_hash = compute_content_hash(text)
            if current_hash == article["stored_hash"]:
                continue
            prepared.append((article["arxiv_id"], text, current_hash))

        if not prepared:
            continue

        if dry_run:
            total += len(prepared)
            continue

        texts = [text for _, text, _ in prepared]
        vectors = await _encode(model, texts, batch_size)
        write_rows = [
            (arxiv_id, content_hash, vector)
            for (arxiv_id, _, content_hash), vector in zip(prepared, vectors)
        ]
        await _write_batch(pool, model_name, write_rows)

        total += len(write_rows)
        logger.info("Phase 2 — %d stale vectors updated (total: %d)", len(write_rows), total)

    return total


async def _run_dry(
    pool,
    read_repo: ArticleRepository,
    model_name: str,
    fetch_size: int,
    batch_size: int,
    only_missing: bool,
) -> None:
    """Simulates backfill and prints article counts without encoding or writing to DB."""
    missing_count = await read_repo.count_missing_embeddings(model_name)

    stale_count = 0
    if not only_missing:
        stale_count = await backfill_stale(
            pool, read_repo, model_name, None, fetch_size, batch_size, dry_run=True
        )

    print(f"DRY RUN — model: {model_name}")
    print(f"  Phase 1 (missing, upper bound): {missing_count}")
    print(f"  Phase 2 (stale, exact):         {stale_count}")
    print(f"  Total (estimated):              {missing_count + stale_count}")
    print("  Note: Phase 1 count includes empty-text articles; actual encoded count may be lower.")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill document embeddings into the database.")
    parser.add_argument("--model", default=None, help="Override default embedding model")
    parser.add_argument(
        "--fetch-size", type=int, default=200, help="Number of records to fetch per DB batch"
    )
    parser.add_argument("--only-missing", action="store_true", help="Execute Phase 1 only")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without database writes")
    args = parser.parse_args()

    settings = get_settings()
    model_name = args.model or settings.embedding_model_name
    batch_size = settings.embedding_batch_size

    pool = await create_script_pool()
    try:
        read_repo = ArticleRepository(pool)

        if args.dry_run:
            await _run_dry(
                pool, read_repo, model_name, args.fetch_size, batch_size, args.only_missing
            )
            return 0

        model = create_embedding_model(model_name)

        missing_count = await backfill_missing(
            pool, read_repo, model_name, model, args.fetch_size, batch_size
        )

        stale_count = 0
        if not args.only_missing:
            stale_count = await backfill_stale(
                pool, read_repo, model_name, model, args.fetch_size, batch_size
            )

        logger.info(
            "Backfill completed — new: %d, updated: %d", missing_count, stale_count
        )
        return 0
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))