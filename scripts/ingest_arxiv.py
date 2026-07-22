import os
import logging
import psycopg2
import requests
from dotenv import load_dotenv

# Yeni modüllerimizden sınıfları çekiyoruz!
from app.scrapers.arxiv_client import ArxivClient
from app.repositories.article_repository import DatabaseManager

# 1. Ortam Değişkenlerini ve Log Yapılandırmasını Kuruyoruz
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# 2. Veritabanı Parametreleri ve URL (Adım 3'te config.py'a taşınacak)
connection_params = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": str(os.getenv("DB_PASSWORD")),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT")
}

arxiv_url = "http://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending"

# 3. İstemci Hazırlığı
client = ArxivClient()
db = None

# 4. Senin Taşıdığın Akış Bloğu
try:
    db = DatabaseManager(connection_params)
    
    soup = client.fetch_raw_data(arxiv_url)
    entries = soup.find_all("entry")

    for entry in entries:
        try:
            article_data = client.parse_entry(entry)
            db.save_article(article_data)
            logging.info(f"Makale işlendi: {article_data['title'][:40]}...")

        except AttributeError as e:
            logging.warning(f"Bir makale eksik/bozuk veri içeriyor, atlanıyor. Detay: {e}")
            continue

        except psycopg2.Error as db_err:
            logging.error(f"Kayıt başarısız: {db_err}")
            db.rollback()
            continue

    logging.info("Veritabanından güncel veriler okunuyor...")
    articles = db.get_articles()
    for row in articles:
        arxiv_id, title, categories, published_at = row
        print(f"[{published_at.date()}] {title}")
        print(f"   Kategori: {categories}")
        print(f"   ID: {arxiv_id}")
        print("-" * 60)

except requests.exceptions.RequestException as e:
    logging.error(f"İnternet hatası: {e}")

except psycopg2.DatabaseError as e:
    logging.error(f"Veritabanı hatası: {e}")

finally:
    if db is not None:
        db.close()