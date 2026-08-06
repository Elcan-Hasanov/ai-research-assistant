CREATE TABLE IF NOT EXISTS article_embeddings (
    arxiv_id VARCHAR(50) NOT NULL REFERENCES articles (arxiv_id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (arxiv_id, model_name)
);