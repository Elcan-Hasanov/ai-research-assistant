import argparse
import asyncio
import logging
import time

import numpy as np

from app.core.database import create_script_pool
from app.core.embedding import create_embedding_model
from app.repositories.article_repository import ArticleRepository
from scripts.measure_query_prefix import (
    DEFAULT_QUERIES,
    fetch_corpus,
    report_corpus_facts,
    top_k,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

# Must stay semantically identical to ArticleRepository.semantic_search.
# Enforced at runtime by verify_sql_parity(); do not "tidy" this string.
EXPLAIN_TARGET_SQL = """
    SELECT
        arxiv_id,
        embedding <=> $1 AS distance
    FROM article_embeddings
    WHERE model_name = $2
    ORDER BY distance ASC, arxiv_id
    LIMIT $3 OFFSET $4;
"""

DEFAULT_EF_SWEEP = [1, 5, 10, 20, 40, 100]


async def report_server_facts(pool) -> None:
    version = await pool.fetchval(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector';"
    )
    indexes = await pool.fetch(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'article_embeddings';"
    )

    ef_search = await pool.fetchval("SHOW hnsw.ef_search;")

    print("\n" + "=" * 78)
    print("SERVER FACTS")
    print("=" * 78)
    print(f"  vector extension (server) : {version}")
    print(f"  hnsw.ef_search (pool)     : {ef_search}")
    for row in indexes:
        print(f"  {row['indexname']}")
        print(f"      {row['indexdef']}")
    if not indexes:
        print("  (no indexes on article_embeddings — migration 007 not applied?)")


async def verify_sql_parity(pool, query_vector, model_name, k) -> bool:
    """The EXPLAIN target must be the query the application actually runs."""
    async with pool.acquire() as conn:
        repo = ArticleRepository(conn)
        via_repo = [
            row["arxiv_id"]
            for row in await repo.semantic_search(query_vector, model_name, k, 0)
        ]
        via_literal = [
            row["arxiv_id"]
            for row in await conn.fetch(
                EXPLAIN_TARGET_SQL, query_vector, model_name, k, 0
            )
        ]
    return via_repo == via_literal


async def explain(
    pool, mode: str, query_vector, model_name: str, k: int, ef_search: int | None
) -> list[str]:
    """Executes EXPLAIN ANALYZE for a target SQL query under three scan modes:

    - 'exact': Disables index scans (enable_indexscan = off) to measure sequential scan.
    - 'forced': Disables sequential scans (enable_seqscan = off) to force HNSW index usage.
    - 'default': Leaves query planner to choose its own path.

    Optionally sets local transaction 'hnsw.ef_search' if ef_search is provided.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            if mode == "exact":
                await conn.execute("SET LOCAL enable_indexscan = off;")
            elif mode == "forced":
                await conn.execute("SET LOCAL enable_seqscan = off;")

            if ef_search is not None:
                await conn.execute(
                    "SELECT set_config('hnsw.ef_search', $1, true);", str(ef_search)
                )

            rows = await conn.fetch(
                "EXPLAIN (ANALYZE, BUFFERS) " + EXPLAIN_TARGET_SQL,
                query_vector,
                model_name,
                k,
                0,
            )
    return [row["QUERY PLAN"] for row in rows]


async def evaluate(
    pool, model, matrix, ids, queries, k, ef_search: int | None
) -> tuple[float, float]:
    """Run every query through the production SQL path at one setting.

    Returns (mean recall@k against the exact NumPy ranking, mean latency in ms).
    """
    recalls: list[float] = []
    latencies: list[float] = []

    async with pool.acquire() as conn:
        repo = ArticleRepository(conn)

        for query in queries:
            query_vector = model.encode_query(query)

            exact_order, _ = top_k(
                matrix, np.asarray(query_vector, dtype=np.float32), k
            )
            exact_ids = {ids[index] for index in exact_order}

            async with conn.transaction():
                if ef_search is None:
                    await conn.execute("SET LOCAL enable_indexscan = off;")
                else:
                    await conn.execute(
                        "SELECT set_config('hnsw.ef_search', $1, true);", str(ef_search)
                    )

                started = time.perf_counter()
                rows = await repo.semantic_search(query_vector, model.model_name, k, 0)
                latencies.append((time.perf_counter() - started) * 1000)

            returned = {row["arxiv_id"] for row in rows}
            recalls.append(len(exact_ids & returned) / k)

    return float(np.mean(recalls)), float(np.mean(latencies))


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Characterise the HNSW index: plan, recall, latency."
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--ef-sweep", type=int, nargs="+", default=DEFAULT_EF_SWEEP)
    args = parser.parse_args()

    model = create_embedding_model(args.model)
    ids, _titles, matrix = await fetch_corpus(model.model_name)

    if not ids:
        logger.error("No embeddings stored. Run scripts.backfill_embeddings first.")
        return 1

    report_corpus_facts(matrix)
    k = min(args.top_k, len(ids))

    pool = await create_script_pool(min_size=1, max_size=2)
    try:
        await report_server_facts(pool)

        probe_vector = model.encode_query(DEFAULT_QUERIES[0])
        if not await verify_sql_parity(pool, probe_vector, model.model_name, k):
            logger.error(
                "EXPLAIN_TARGET_SQL diverged from ArticleRepository.semantic_search. "
                "Every plan below would describe a query the API does not run."
            )
            return 1

        modes = [
            ("EXACT (enable_indexscan = off)", "exact", None),
            ("DEFAULT (planner choice)", "default", 100),
            ("FORCED (enable_seqscan = off)", "forced", 100),
        ]

        for label, mode, ef in modes:
            print("\n" + "=" * 78)
            print(f"PLAN — {label}")
            print("=" * 78)
            lines = await explain(pool, mode, probe_vector, model.model_name, k, ef)
            for line in lines:
                print(f"  {line}")

            if mode == "forced":
                plan_text = "\n".join(lines)
                if "Index Scan" in plan_text or "idx_article_embeddings_embedding" in plan_text:
                    print("\n  -> [INDEX EVALUATION] Index is usable (Index Scan executed under forced condition).")
                else:
                    print("\n  -> [INDEX EVALUATION] Index NOT usable — check operator class or index definition.")

        exact_recall, exact_latency = await evaluate(
            pool, model, matrix, ids, DEFAULT_QUERIES, k, None
        )

        print("\n" + "=" * 78)
        print(f"RECALL / LATENCY SWEEP  (k = {k}, n_queries = {len(DEFAULT_QUERIES)})")
        print("=" * 78)
        print(f"  {'ef_search':>12} | {'recall@k':>9} | {'latency ms':>11}")
        print("  " + "-" * 40)
        print(f"  {'exact':>12} | {exact_recall:>9.3f} | {exact_latency:>11.2f}")

        for ef in args.ef_sweep:
            recall, latency = await evaluate(
                pool, model, matrix, ids, DEFAULT_QUERIES, k, ef
            )
            print(f"  {ef:>12} | {recall:>9.3f} | {latency:>11.2f}")

        print("=" * 78 + "\n")
    finally:
        await pool.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))