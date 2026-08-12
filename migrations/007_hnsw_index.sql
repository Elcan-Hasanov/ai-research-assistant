CREATE INDEX IF NOT EXISTS idx_article_embeddings_embedding
ON article_embeddings USING HNSW (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);