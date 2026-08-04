ALTER TABLE articles
    ALTER COLUMN categories TYPE TEXT[]
    USING CASE
        WHEN categories IS NULL OR trim(categories) = '' THEN '{}'::TEXT[]
        ELSE string_to_array(categories, ', ')
    END;

CREATE INDEX IF NOT EXISTS idx_articles_categories
    ON articles USING GIN (categories);

CREATE INDEX IF NOT EXISTS idx_articles_published_at
    ON articles (published_at DESC);