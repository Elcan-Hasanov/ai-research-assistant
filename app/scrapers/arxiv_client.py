import re
from datetime import datetime
from typing import Any, Dict
import requests
from bs4 import BeautifulSoup, Tag


class ArxivClient:

    def fetch_raw_data(self, url: str) -> BeautifulSoup:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.text, "lxml-xml")

    def parse_entry(self, entry: Tag) -> Dict[str, Any]:
        title = entry.find("title").text.strip()
        summary = entry.find("summary").text.strip()

        published_raw = entry.find("published").text
        published_at = datetime.fromisoformat(
            published_raw.replace("Z", "+00:00")
        )

        authors_list = [
            author.find("name").text for author in entry.find_all("author")
        ]
        authors_str = ", ".join(authors_list)

        categories_list = [
            cat.get("term") for cat in entry.find_all("category")
        ]
        categories_str = ", ".join(categories_list)

        # Preserve category prefix for older arXiv IDs and trim trailing versioning safely
        arxiv_id_raw = entry.find("id").text
        if "/abs/" in arxiv_id_raw:
            raw_path = arxiv_id_raw.split("/abs/")[-1]
        else:
            raw_path = arxiv_id_raw.rstrip("/").split("/")[-1]
        clean_id = re.sub(r"v\d+$", "", raw_path)

        return {
            "arxiv_id": clean_id,
            "title": title,
            "summary": summary,
            "authors": authors_str,
            "categories": categories_str,
            "published_at": published_at,
        }