CREATE TABLE IF NOT EXISTS articles (
    arxiv_id VARCHAR(50) PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    authors TEXT,
    categories TEXT,
    published_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);