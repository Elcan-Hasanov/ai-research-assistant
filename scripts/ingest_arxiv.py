import argparse
import asyncio
import logging
from urllib.parse import quote_plus

import asyncpg
import requests

from app.core.database import create_script_pool
from app.repositories.article_repository import ArticleRepository
from app.scrapers.arxiv_client import ArxivClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

ARXIV_ENDPOINT = "http://export.arxiv.org/api/query"

# cs.AI alone does not cover the query set used from Step 10 onward
# (RLHF, PEFT, MoE, CoT). Those papers live mostly under cs.CL and cs.LG.
DEFAULT_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG"]


def build_query_url(categories: list[str], start: int, page_size: int) -> str:
    """Compose one page request. Category terms are OR-ed into a single search_query."""
    search_query = " OR ".join(f"cat:{category}" for category in categories)

    return (
        f"{ARXIV_ENDPOINT}"
        f"?search_query={quote_plus(search_query)}"
        f"&start={start}"
        f"&max_results={page_size}"
        f"&sortBy=submittedDate"
        f"&sortOrder=descending"
    )


async def ingest_page(
    repo: ArticleRepository, client: ArxivClient, url: str
) -> tuple[int, int]:
    """Fetch and persist one page. Returns (entries_seen, rows_written)."""
    soup = client.fetch_raw_data(url)
    entries = soup.find_all("entry")

    written = 0
    for entry in entries:
        try:
            article_data = client.parse_entry(entry)

            await repo.upsert_article(
                arxiv_id=article_data["arxiv_id"],
                title=article_data["title"],
                summary=article_data["summary"],
                authors=article_data["authors"],
                categories=article_data["categories"],
                published_at=article_data["published_at"],
            )
            written += 1

        except AttributeError as exc:
            logger.warning("Malformed entry skipped: %s", exc)

        except asyncpg.PostgresError as exc:
            logger.error("Database write failed: %s", exc)

    return len(entries), written


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest arXiv metadata into PostgreSQL."
    )
    parser.add_argument("--categories", nargs="+", default=DEFAULT_CATEGORIES)
    parser.add_argument("--target", type=int, default=5000)
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--delay", type=float, default=3.0)
    args = parser.parse_args()

    pool = None
    seen = 0
    written = 0
    start = 0

    try:
        pool = await create_script_pool()
        repo = ArticleRepository(pool)
        client = ArxivClient()

        while seen < args.target:
            page_size = min(args.page_size, args.target - seen)
            url = build_query_url(args.categories, start, page_size)
            logger.info("Fetching start=%d size=%d", start, page_size)

            try:
                page_seen, page_written = await ingest_page(repo, client, url)
            except requests.exceptions.RequestException as exc:
                logger.error("Request failed at start=%d: %s. Stopping.", start, exc)
                break

            if page_seen == 0:
                logger.warning("Empty page at start=%d. Stopping.", start)
                break

            seen += page_seen
            written += page_written
            start += page_seen

            if seen < args.target:
                await asyncio.sleep(args.delay)

        total = await repo.count_articles()
        logger.info(
            "Ingest finished. seen=%d written=%d table_total=%d", seen, written, total
        )

    finally:
        if pool is not None:
            await pool.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))