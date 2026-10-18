CREATE TABLE llm_attempts (
    request_id UUID NOT NULL,
    attempt SMALLINT NOT NULL,
    prompt_identifier TEXT NOT NULL,
    outcome TEXT NOT NULL,
    stop TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    model TEXT,
    reported_cost_usd DOUBLE PRECISION,
    elapsed_seconds DOUBLE PRECISION,
    status_code SMALLINT,
    provider_error TEXT,
    retry_after_seconds DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (request_id, attempt)
);