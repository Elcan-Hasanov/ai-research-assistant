import asyncio
import logging
from datetime import datetime

import asyncpg
import requests

from app.core.database import create_script_pool
from app.repositories.article_repository import ArticleRepository
from app.scrapers.arxiv_client import ArxivClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


arxiv_url = (
    "http://export.arxiv.org/api/query?"
    "search_query=cat:cs.AI&start=0&max_results=100&"
    "sortBy=submittedDate&sortOrder=descending"
)


client = ArxivClient()


async def main():
    pool = None

    try:
        pool = await create_script_pool()
        db = ArticleRepository(pool)

        soup = client.fetch_raw_data(arxiv_url)
        entries = soup.find_all("entry")

        for entry in entries:
            try:
                article_data = client.parse_entry(entry)

                await db.upsert_article(
                    arxiv_id=article_data["arxiv_id"],
                    title=article_data["title"],
                    summary=article_data["summary"],
                    authors=article_data["authors"],
                    categories=article_data["categories"],
                    published_at=article_data["published_at"],
                )

                logging.info(
                    f"Article processed: {article_data['title'][:40]}..."
                )

            except AttributeError as e:
                logging.warning(
                    f"Article contains invalid data and was skipped. Details: {e}"
                )
                continue

            except asyncpg.PostgresError as db_err:
                logging.error(f"Database save error: {db_err}")
                continue

            except Exception as e:
                logging.error(f"Unexpected error while processing article: {e}")
                continue

        logging.info("Reading latest stored articles from database...")
        articles = await db.list_articles()

        for row in articles:
            arxiv_id = row["arxiv_id"]
            title = row["title"]
            categories = row["categories"]
            published_at = row["published_at"]

            date_display = (
                published_at.date()
                if isinstance(published_at, datetime)
                else published_at
            )

            print(f"[{date_display}] {title}")
            print(f"   Category: {categories}")
            print(f"   ID: {arxiv_id}")
            print("-" * 60)

    except requests.exceptions.RequestException as e:
        logging.error(f"Internet error: {e}")

    except Exception as e:
        logging.error(f"Critical error in main process: {e}")

    finally:
        if pool is not None:
            await pool.close()


if __name__ == "__main__":
    asyncio.run(main())