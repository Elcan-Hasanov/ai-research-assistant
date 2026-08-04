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

        arxiv_id_raw = entry.find("id").text
        id_with_prefix = arxiv_id_raw.split("abs/")[-1]
        clean_id = re.sub(r"v\d+$", "", id_with_prefix)

        return {
            "arxiv_id": clean_id,
            "title": title,
            "summary": summary,
            "authors": authors_str,
            "categories": categories_list,
            "published_at": published_at,
        }