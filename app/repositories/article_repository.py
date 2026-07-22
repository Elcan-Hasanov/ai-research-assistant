import sys
import logging
import psycopg2

# Eğer V1'de UPSERT_SORGUSU bağımsız bir değişkense, onu da buraya eklemelisin:
UPSERT_SORGUSU = """
INSERT INTO articles (arxiv_id, title, summary, authors, categories, published_at)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (arxiv_id) DO UPDATE SET
    title = EXCLUDED.title,
    summary = EXCLUDED.summary,
    authors = EXCLUDED.authors,
    categories = EXCLUDED.categories,
    published_at = EXCLUDED.published_at;
"""

class DatabaseManager:
    def __init__(self, connection_params):
        try:
            self.conn = psycopg2.connect(**connection_params)
            self.cursor = self.conn.cursor()
        except psycopg2.OperationalError as e:
            logging.error("Veritabanına bağlanılamadı!")
            logging.error("Lütfen PostgreSQL servisinin çalıştığından ve .env bilgilerinin doğru olduğundan emin olun.")
            logging.error(f"Sistem Mesajı: {e}")
            sys.exit(1)

    def save_article(self, article_data):
        self.cursor.execute(UPSERT_SORGUSU, (
            article_data["arxiv_id"],
            article_data["title"],
            article_data["summary"],
            article_data["authors"],
            article_data["categories"],
            article_data["published_at"]
        ))
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.cursor.close()
        self.conn.close()

    def get_articles(self):
        self.cursor.execute(
            "SELECT arxiv_id, title, categories, published_at FROM articles ORDER BY published_at DESC;"
        )
        return self.cursor.fetchall()