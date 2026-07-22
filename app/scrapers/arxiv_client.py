import requests
from bs4 import BeautifulSoup

class ArxivClient:
    def fetch_raw_data(self, url):
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.text, "lxml-xml")

    def parse_entry(self, entry):
        title = entry.find("title").text.strip()
        summary = entry.find("summary").text.strip()
        published_at = entry.find("published").text

        authors_list = [author.find("name").text for author in entry.find_all("author")]
        authors_str = ", ".join(authors_list)

        categories_list = [cat.get("term") for cat in entry.find_all("category")]
        categories_str = ", ".join(categories_list)

        arxiv_id_raw = entry.find("id").text
        id_with_version = arxiv_id_raw.split("/")[-1]
        clean_id = id_with_version.split("v")[0]

        return {
            "arxiv_id": clean_id,
            "title": title,
            "summary": summary,
            "authors": authors_str,
            "categories": categories_str,
            "published_at": published_at
        }