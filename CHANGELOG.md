# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

From 4.0.0 on, this file says what changed in each release. The decisions
behind a release, with the measurements that settled them, are in
[`docs/decisions/`](docs/decisions/); what is known and still open is in
[`docs/known-gaps.md`](docs/known-gaps.md).

## [Unreleased]

## [4.0.0] - 2026-10-24

The first generation layer: an LLM extraction endpoint, built on a provider
client, versioned prompts, structured output, an error taxonomy, retries and
per-attempt usage records. The decisions behind it are in
[`docs/decisions/v4.0.md`](docs/decisions/v4.0.md).

### Added

- `POST /articles/{arxiv_id}/facts`: structured facts from one stored article's
  abstract, produced by the LLM — the problem the paper addresses, its claimed
  contributions, and whether it reports experiments of its own. It answers
  `200`, `404`, `422`, `500` or `503`; the README says what each means
- LLM provider settings: `LLM_API_KEY`, required at startup; `LLM_MODEL`;
  `LLM_TIMEOUT_SECONDS`; and `LLM_BASE_URL`, which routes requests through an
  Anthropic-compatible gateway when set
- `app/core/llm.py`, the only module that imports the provider SDK.
  `LLMClient.complete()` makes exactly one provider call and returns an
  `LLMCompletion`: text, stop reason, input and output tokens, model, duration,
  and the cost the gateway reported. A failed call raises `LLMError`, carrying
  the status code, the provider's error type, the wait the provider asked for
  and the duration. `create_llm_client` builds the client for the gateway or
  the direct path, with the SDK's own retries switched off, a connect timeout
  separate from the read, write and pool timeouts, and an optional HTTP client
  to send through
- `app/prompts/`: versioned prompt templates on disk, `<name>.v<N>.txt` —
  `extract_paper_facts.v1` and `summarize_article.v1` — and a registry that
  loads them at import and renders them with Jinja2 under `StrictUndefined`. A
  missing variable and an undeclared one both raise `PromptRenderError`; a
  malformed template stops the application at import with `PromptLoadError`
- `app/generation/extraction.py`: `PaperFacts`, whose JSON Schema travels with
  the request so that the provider constrains decoding, and
  `parse_paper_facts`, which validates the answer locally and raises
  `ExtractionValidationError` with its cause — `unparseable` or
  `schema_violation` — and without the model's output
- `app/services/generation_service.py`: `GenerationService` with
  `extract_facts` and `summarize_article`; the second has no route yet. The
  request each use case sends is a `GenerationRequest`, built by
  `extraction_request` or `summary_request`, functions that do no I/O
- `app/core/errors.py`: `AppError`, the base of every application error, with
  four failure categories, and `NotFoundError`. In `app/core/exceptions.py`,
  one handler turns a category into a status code and a log level, logs a
  single `key=value` line without the traceback, and answers with a message
  written for the caller
- `app/core/retry.py`: a provider call that fails as upstream-unavailable — a
  `429`, a `5xx` including `529`, a timeout or a refused connection — is
  retried: three attempts in all, a wait that starts at half a second and
  doubles, trimmed by at most a quarter, and a `Retry-After` honoured up to 60
  seconds. Each retry logs a `WARNING`
- Usage records: migration `009_create_llm_attempts.sql` creates
  `llm_attempts`, one row per provider attempt, keyed by request id and attempt
  number; `app/core/usage.py` records the attempts and
  `app/repositories/usage_repository.py` writes them. A request's attempts are
  written in one batch when it ends, whatever its outcome; a failed write is
  logged and never changes the response. The README's Usage Accounting section
  has the query for attempts and known cost per request
- Scripts: `probe_llm.py` and `probe_structured.py`, one-shot discovery probes;
  `measure_json_compliance.py` and `measure_response_variability.py`, repeated
  measurements on a fixed input. `measure_response_variability.py --record`
  saves one real response as a test recording
- Tests: `FakeLLMClient`, which plays back a script of completions and
  exceptions and records every call, and a fake clock; client tests over a real
  SDK client with a faked socket, covering error translation, timing, cost
  parsing, the outgoing request body, and a recorded gateway response in
  `tests/recordings/`; prompt, extraction, retry, usage, error-mapping and
  route-dispatch tests; service tests against the test database with a faked
  provider, including the exact request each use case sends; and one live test
  that sends the production request to the real gateway
- The `live` marker and the `--live` option: live tests are skipped unless
  `--live` is given, so a normal run never calls the provider. `pytest --live
  -m live` runs only them
- `anthropic` and `jinja2` as direct dependencies
- `docs/decisions/v4.0.md`, the decisions behind this release, and
  `docs/known-gaps.md`

### Changed

- `GET /articles/{arxiv_id}` answers a missing article through the shared error
  handler: `ArticleService.get_by_arxiv_id` raises `NotFoundError` instead of
  returning `None` for the router to turn into an `HTTPException`, and the
  route declares its `404` and `500`
- The lifespan acquires the database pool, the embedding model and the LLM
  client inside one `try`/`finally`, and closes the client and the pool in
  reverse order
- The test database check runs only when a selected test is marked `db`, so
  `pytest -m "not db"` runs without PostgreSQL. A test that uses `db_conn`
  without the `db` marker fails at setup
- The application's version is defined in code, as `app.__version__`
- `app/core/exceptions.py` logs through a module logger instead of the root
  logger
- README restructured: no table of contents, a top-level directory tree, no
  feature list; sections added for the LLM configuration, usage accounting, and
  recorded and live tests
- Step numbers removed from comments in application code and scripts

### Removed

- The `APP_VERSION` setting. A leftover `APP_VERSION` line in a local `.env` is
  ignored

### Fixed

- An unexpected error was logged with its traceback twice — by the
  application's handler, and again by the server, because Starlette re-raises
  after a handler registered for `Exception` has responded. The handler now
  logs one line and leaves the traceback to the server

---

## [3.0.0] - 2026-08-17

### Added

- pgvector extension enabled on a minimal, volume-backed PostgreSQL
  container; schema versioning via numbered migration files and an
  async runner script
- Common retrieval contract (`RetrievalResult`: document id, score,
  method) shared across the Router → Service → Repository layers
- Lexical search endpoint (`/articles/search`) using PostgreSQL native
  full-text search (tsvector, GIN index, `ts_rank_cd`)
- Local embedding inference via Sentence Transformers; model selected
  against measured criteria (output dimension, `max_seq_length`,
  license) rather than leaderboard rank
- `article_embeddings` table: vector(384) column, composite PK
  (`arxiv_id`, `model_name`), `content_hash` for staleness detection
- pgvector type codec registration on connection pool init (API and scripts)
- Startup-time verification that the loaded model's output dimension
  matches the configured schema dimension
- `EmbeddingModel.encode_documents()` / `encode_query()`, routed through
  sentence-transformers' prompt-aware encoding methods
- Embedding backfill pipeline (`scripts/backfill_embeddings.py`): embeds
  articles missing a vector and re-embeds ones whose `content_hash` no
  longer matches the current `build_embedding_text()` output
- `ArticleRepository.count_missing_embeddings()` / `fetch_missing_embeddings()`
  / `fetch_existing_embeddings()` / `upsert_embeddings()` for the backfill
  read/write paths
- `compute_content_hash()`, computing the embedding text's SHA-256 for
  staleness detection
- `article_embeddings.updated_at`, distinguishing a freshly written
  vector from a re-embedded one
- `--dry-run` and `--only-missing` flags for previewing and scoping
  backfill runs without writing
- Semantic search endpoint (`/articles/semantic-search`) ranking articles by
  pgvector cosine distance (`<=>`) against a target model's stored embeddings
- `ArticleRepository.semantic_search()` / `count_embedded_articles()` for the
  vector retrieval read path
- `ArticleService.semantic_search()`: offloads query encoding to a worker
  thread (`asyncio.to_thread`) to avoid blocking the event loop, converts
  cosine distance to a similarity score (`score = 1 - distance`), and maps
  results onto the shared `RetrievalResult` contract (`method="semantic"`)
- `/health/ready` now also verifies the embedding model was loaded at startup
- `scripts/measure_query_prefix.py`: measures whether BAAI's documented query
  instruction prefix changes retrieval ranking for `encode_query()`
- **Decision (measured):** no manual query prefix is applied. `encode_query()`
  was confirmed to apply no prompt on its own (`model.prompts` empty,
  verified against raw `encode()` output). Manually injecting BAAI's
  instruction prefix showed mixed, weak impact on ranking (mean
  overlap@10 = 0.73 across 10 queries, top-1 changed in 4/10) — one clear
  quality signal out of ten sampled queries is not sufficient evidence to
  add a permanent code path. Revisit with the larger query set in Step 12.
- **Decision (re-measured, closed):** re-ran the frozen 10-query prefix
  control set on the 5,000-document corpus (up from 100). Result unchanged
  within rounding — mean overlap@10 = 0.730, top-1 changed 4/10, versus 0.73
  and 4/10 on the original corpus. The 50x corpus growth produced no
  meaningful shift. Per the pre-committed decision rule (overlap@10 ≥ 0.65
  and top-1 changed ≤ 5/10), this question is now closed permanently — no
  manual query prefix will be added.
- HNSW index on `article_embeddings.embedding` (`vector_cosine_ops`,
  `m=16`, `ef_construction=64`, explicitly pinned rather than left at
  extension defaults, since the server image tag is mutable)
- `hnsw_ef_search` setting in `Settings`, kept in sync with
  `SearchParams.limit`'s ceiling (100) so the ANN candidate pool is never
  narrower than the largest result count the API allows
- `scripts/measure_ann_index.py`: characterises the HNSW index against
  the exact NumPy ranking already established in
  `measure_query_prefix.py` — reads server-side extension version and
  index definition, verifies `EXPLAIN_TARGET_SQL` stays identical to
  `ArticleRepository.semantic_search()`, plans the query under three
  scan modes (`exact` / `default` / `forced`), and sweeps `ef_search`
  for recall@k and latency
- `ingest_arxiv.py` now paginates and accepts `--categories` /
  `--target`; default categories expanded to `cs.AI`, `cs.CL`, `cs.LG`
  (Step 12's query set — RLHF, PEFT, MoE, CoT — lives mostly outside
  `cs.AI` alone). Cross-listed papers are handled for free by the
  existing `upsert_article()` idempotency (`ON CONFLICT DO UPDATE`),
  no additional code required
- Corpus grown to ~5,000 articles, backfilled with existing embedding
  pipeline unchanged (idempotent, missing-only by design since Step 9)
- **Decision (measured):** at n=5,000 the planner does not select the
  HNSW index under default cost settings — `EXPLAIN ANALYZE` shows
  `Seq Scan` for both the exact and default-config plans (~8-13ms,
  fully buffer-resident). Forcing `enable_seqscan = off` confirms the
  index *is* usable (`Index Scan` executes, operator class correct);
  the planner's choice is a cost decision, not a broken index. Recall
  sweep across `ef_search ∈ {1,5,10,20,40,100}` returned 1.000 at every
  setting, consistent with the index never being selected. This is not
  a failed measurement — it's the expected outcome at this scale.
  Revisit when corpus size grows enough for the planner's cost
  estimate to flip (V7).
- `ArticleRepository.get_by_ids()`: batch document hydration for retrieval
  results. Retrieval returns ids and scores; the documents themselves are
  fetched separately from the source-of-truth table. Row order is
  deliberately unspecified — ranking belongs to the caller that produced it
- `evaluation/queries_v1.json`: 18-query retrieval evaluation set, stratified
  by query type (exact_term, acronym, named_entity, paraphrase, conceptual,
  out_of_corpus) before any query was written, so the set measures the
  systems rather than the author's query habits
- `scripts/compare_retrieval.py`: runs the evaluation set through both
  retrieval paths via `ArticleService`, hydrates the union of both result
  sets in one round-trip, and prints the two rankings with shared documents
  marked
- `evaluation/findings_step12.md`: qualitative comparison of lexical and
  semantic retrieval. Relevance criterion committed before inspection;
  pooling bias and sample size recorded as explicit limitations. This is the
  first version of the V6 benchmark dataset
- Test suite (`tests/`): 35 tests across schema validation, the
  `distance → score` conversion, vector dimension consistency, and
  repository query correctness. Scope is deliberately narrow — not
  coverage-driven. The targets are surfaces where a wrong answer is
  *silent*: a swapped `ORDER BY` direction, a dropped `WHERE`, a
  transposed `LIMIT`/`OFFSET` pair. Paths that fail loudly (schema
  constraints, invalid SQL) and paths whose output a human already
  reads (lab scripts) are excluded
- Per-test transactional isolation (`tests/conftest.py`): each test runs
  inside an open transaction that is always rolled back, including when
  the test raises. Cleanup is a property of the transaction rather than
  code at the end of the test, so it cannot be skipped by an early
  failure. This is only possible because `ArticleRepository` accepts a
  `Connection` as well as a `Pool` — the test's transaction and the
  repository's queries must share one connection, or uncommitted rows
  stay invisible to the reader
- Tests run against a separate database (`DB_NAME` overridden at conftest
  import, `get_settings.cache_clear()` applied). Application code carries
  no test awareness. A second guard is behavioural rather than
  name-based: if the target database holds more than
  `MAX_ROWS_IN_TEST_DATABASE` articles it is a working corpus, and the
  session refuses to start — a name comparison would have been defeated
  by a stale `DB_NAME` left in the shell
- `FakeEmbeddingModel`: a hand-written stand-in exposing exactly the
  surface the service uses (`encode_query`, `model_name`). Deterministic
  by construction (same text → same unit vector) but never semantic;
  ranking quality is V6's question, not this layer's. Written as a class
  rather than `MagicMock` so that calling a method the real class does
  not have raises instead of silently succeeding
- `requirements-dev.in` / `requirements-dev.txt`: test dependencies kept
  out of the production manifest, constrained (`-c requirements.txt`) so
  the two resolutions cannot disagree on a shared transitive dependency
- `pyproject.toml` with `[tool.pytest.ini_options]` only. `asyncio_mode`
  must be set or async tests are skipped without failing the suite;
  `--strict-config` turns an unrecognised option into an error so that
  misconfiguration cannot itself be silent. Package metadata deliberately
  omitted — that is a packaging decision, not a test one
- **Decision (calibrated):** every test was verified by mutation — the
  SQL or service decision it claims to protect was deliberately broken
  and the test confirmed to fail. Weakening (`WHERE ... OR TRUE`) rather
  than deletion, since deleting a clause leaves an unused bind parameter
  and the query stops being valid SQL, which proves nothing about the
  test. Four repository decisions and three service decisions were
  calibrated this way. A green suite is evidence only after this step
- **Decision (revised):** index-usage verification (`Index Scan using
  articles_pkey`, observed on the 5,000-row corpus in Step 12) was not
  carried into a test. Query plans are a function of data volume; on a
  five-row test table the planner correctly chooses `Seq Scan`, so the
  assertion would fail for the right reason. Plan assertions belong to a
  benchmark suite against realistic volumes (V6/V7). The remaining
  `get_by_ids` cases — empty input, unknown ids, repeated ids, absence of
  an order guarantee — are covered

### Changed
- `ArticleRepository` now accepts `Pool | Connection` instead of `Pool`
  only, enabling transactional writes; returns plain `dict` instead of
  `asyncpg.Record` for testability
- Standalone scripts now share a single connection pool factory
  (`create_script_pool`)
- `content_hash`-based staleness detection is now active (the column
  was added earlier but unused until this pipeline)
- `embedding_batch_size` moved from an implicit script constant to
  `Settings`, shared across scripts
- `search_articles()` and `semantic_search()` both order by a deterministic
  tie-break (`arxiv_id`) after the primary score/distance, preventing
  duplicate or skipped rows across paginated requests when scores tie
- Test database schema is applied manually (`DB_NAME=... python -m
  scripts.migrate`); the suite asserts the schema exists rather than
  creating it, since `migrate.py` is still CWD-dependent. Automating
  this is blocked on that fix (V7)
  
### Fixed
- `hnsw.ef_search` set via `set_config()` in the pool's
  `_init_connection` hook did not persist — `SHOW hnsw.ef_search`
  reported the server default (40) regardless of the configured value
  (100), even after forcing pgvector's shared library to load first.
  Root cause not fully isolated between two candidates (pgvector
  library load timing vs. asyncpg pool connection-return behavior).
  Fixed by moving the setting from connection scope to database scope:
  `ALTER DATABASE ... SET hnsw.ef_search = 100` in a new migration,
  applied once at the session's start regardless of how the connection
  was opened. `_init_connection` simplified back to codec registration
  only.

---

## [2.0.0] - 2026-07-29

### Added
- **Asynchronous REST API:** Built FastAPI layer served with Uvicorn.
- **PostgreSQL Connectivity:** Integrated `asyncpg` with connection pooling managed via application lifespan events.
- **Layered Architecture:** Restructured codebase into `api`, `repositories`, `schemas`, and `core` layers using the Repository Pattern.
- **DTOs & Data Validation:** Created Pydantic v2 schemas (`ArticleResponse`, `ArticleFilterParams`) for request/response serialization.
- **API Endpoints:**
  - `GET /health` (Liveness check)
  - `GET /health/ready` (Readiness check for DB connectivity)
  - `GET /articles` (Paginated article listing with category filter)
  - `GET /articles/{arxiv_id}` (Single article lookup)
- **Global Error Handling:** Implemented central exception handlers for HTTP 404, 500, and 503 status codes.
- **Interactive Documentation:** Auto-generated Swagger UI (`/docs`) and ReDoc (`/redoc`) OpenAPI specs.
- **Configuration Management:** Environment configuration via `pydantic-settings` and `.env`.

### Changed
- Refactored CLI workflow to serve data through an API layer instead of direct database scripts.

---

## [1.0.0] - 2026-07-22

### Added
- **ArXiv Scraper:** Initial CLI tool for scraping research paper metadata from ArXiv.
- **Data Ingestion Pipeline:** Web scraping, HTML parsing, and data cleaning routines.
- **Persistence Layer:** Initial PostgreSQL database schema for storing research articles.