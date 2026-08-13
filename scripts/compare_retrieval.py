import argparse
import asyncio
import json
import logging
from pathlib import Path

from app.core.database import create_script_pool
from app.core.embedding import create_embedding_model
from app.repositories.article_repository import ArticleRepository
from app.schemas.retrieval import RetrievalResult
from app.services.article_service import ArticleService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

# Resolved from this file, never from the process CWD. The script must behave
# identically whether launched from the repo root or elsewhere (see O7).
QUERY_SET_PATH = Path(__file__).resolve().parents[1] / "evaluation" / "queries_v1.json"

TITLE_WIDTH = 84

KNOWN_TARGETS = {
    "q09": "2608.01247",
    "q10": "2608.01247",
    "q14": "2608.01247",
    "q17": "2608.01247",
    "q12": "2607.21861",
    "q15": "2607.21861",
    "q13": "2608.04286",
    "q16": "2608.04286",
}


def rank_of(items, target_id: str) -> int | None:
    """1-based rank of target_id in items, or None if absent."""
    for rank, item in enumerate(items, start=1):
        if item.document_id == target_id:
            return rank
    return None

def load_query_set(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["queries"]


async def fetch_titles(repo: ArticleRepository, arxiv_ids: list[str]) -> dict[str, str]:
    """Build an id -> title lookup for every document either system returned."""
    unique_ids = list(dict.fromkeys(arxiv_ids))
    if not unique_ids:
        return {}

    records = await repo.get_by_ids(unique_ids)
    return {record["arxiv_id"]: record["title"] for record in records}


def format_ranking(
    items: list[RetrievalResult], titles: dict[str, str], shared: set[str]
) -> list[str]:
    lines = []
    for rank, item in enumerate(items, start=1):
        marker = "*" if item.document_id in shared else " "
        title = titles.get(item.document_id, "<TITLE MISSING — investigate>")
        lines.append(
            f"{marker}{rank:>2}. [{item.score:>8.4f}] {item.document_id:<13} {title[:TITLE_WIDTH]}"
        )
    return lines


def print_query_report(entry: dict, lexical, semantic, titles: dict[str, str], k: int) -> None:
    lexical_ids = {item.document_id for item in lexical.items}
    semantic_ids = {item.document_id for item in semantic.items}
    shared = lexical_ids & semantic_ids

    print("\n" + "=" * 110)
    print(f"[{entry['id']}]  type = {entry['type']}")
    print(f"  query                    : {entry['text']!r}")
    print(f"  why in set               : {entry.get('note', '-')}")
    print(f"  lexical matches in corpus: {lexical.total}")
    print("=" * 110)

    print("\n  LEXICAL   score = ts_rank_cd (unbounded, corpus-dependent)")
    if not lexical.items:
        print("     (no rows — no document contains every query term)")
    else:
        for line in format_ranking(lexical.items, titles, shared):
            print("   " + line)

    print("\n  SEMANTIC  score = 1 - cosine distance (normalised vectors)")
    if not semantic.items:
        print("     (no rows — the embeddings table is empty for this model)")
    else:
        for line in format_ranking(semantic.items, titles, shared):
            print("   " + line)

    print(f"\n  overlap: {len(shared)}/{k}   ('*' marks documents returned by both)")

    target_id = KNOWN_TARGETS.get(entry["id"])
    if target_id is not None:
        lex_rank = rank_of(lexical.items, target_id)
        sem_rank = rank_of(semantic.items, target_id)
        print(f"  known-item target {target_id}: lexical={lex_rank or 'not found'}  semantic={sem_rank or 'not found'}")


async def run_query(
    service: ArticleService, repo: ArticleRepository, text: str, k: int
) -> tuple:
    lexical = await service.search_articles(query=text, limit=k, offset=0)
    semantic = await service.semantic_search(query=text, limit=k, offset=0)

    returned_ids = [item.document_id for item in lexical.items] + [
        item.document_id for item in semantic.items
    ]
    titles = await fetch_titles(repo, returned_ids)
    return lexical, semantic, titles


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the evaluation query set through both retrieval paths, side by side."
    )
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument("--limit", type=int, default=5, help="Results shown per system")
    parser.add_argument("--queries", type=Path, default=QUERY_SET_PATH)
    parser.add_argument(
        "--type", dest="type_filter", default=None, help="Run only one query type"
    )
    args = parser.parse_args()

    entries = load_query_set(args.queries)
    if args.type_filter:
        entries = [entry for entry in entries if entry["type"] == args.type_filter]
    if not entries:
        logger.error("Query set is empty after filtering by %r.", args.type_filter)
        return 1

    model = create_embedding_model(args.model)
    pool = await create_script_pool(min_size=1, max_size=2)
    try:
        async with pool.acquire() as conn:
            repo = ArticleRepository(conn)
            service = ArticleService(repo, model)

            embedded = await repo.count_embedded_articles(model.model_name)
            if embedded == 0:
                logger.error(
                    "No embeddings stored for %r. Run scripts.backfill_embeddings first.",
                    model.model_name,
                )
                return 1

            print("\n" + "=" * 110)
            print(f"  model     : {model.model_name}")
            print(f"  corpus    : {embedded} embedded documents")
            print(f"  query set : {args.queries.name}  ({len(entries)} queries)")
            print(f"  depth     : top-{args.limit} per system")
            print("=" * 110)

            for entry in entries:
                lexical, semantic, titles = await run_query(
                    service, repo, entry["text"], args.limit
                )
                print_query_report(entry, lexical, semantic, titles, args.limit)
    finally:
        await pool.close()

    print("\n" + "=" * 110 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))