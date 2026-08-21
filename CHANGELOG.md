# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `anthropic` SDK as a direct dependency; `requirements.txt` regenerated
  from `requirements.in`
- LLM provider settings in `Settings`: `llm_api_key` (`SecretStr`, no
  default — a missing credential is a configuration error and fails at
  startup), `llm_model`, `llm_timeout_seconds`, and `llm_base_url`
- `scripts/probe_llm.py`: one-shot discovery probe for the LLM provider.
  Reports the SDK's default timeout and retry policy, dumps a raw
  response object, and forces a `max_tokens` truncation to observe the
  difference between a successful HTTP response and a complete
  generation. Not a measurement script — no decision rule is written and
  no threshold is derived from a single sample
- `.env.example` extended with the four `LLM_*` keys (names only, no values)
- `app/core/llm.py`: the single module in the application permitted to
  import the provider SDK. Holds `LLMClient` (one `complete()` call, no
  loop), `LLMCompletion` (the project's own return contract),
  `CompletionStop`, `LLMError`, the `to_completion` translation
  function, and the `create_llm_client` factory
- `FakeLLMClient` in `tests/conftest.py`: hand-written, duck-typed
  stand-in that returns a canned `LLMCompletion`. Second test double in
  the project after `FakeEmbeddingModel`, and the seam every generation
  test from the service layer onward will depend on
- `tests/test_llm_client.py`: five translation tests built from a real
  captured response, covering the normal case, truncation, multiple text
  blocks, non-text blocks, and an unrecognised stop reason. No network,
  no database, no marker


### Changed

- `app_version` advanced to `4.0.0-dev`; the `.env` template in the README
  was carrying `3.0.0` and has been brought in sync. A `Settings` default
  is only a default — an `.env` file that still sets the old value silently
  overrides it, which is why all three (config, `.env.example`, README)
  are updated together
- README restructured: table of contents removed (GitHub generates one),
  the per-file directory tree reduced to top-level directories, and the
  `Features (v3.0.0)` section dropped. The per-file tree required an edit
  on every added migration or test, and the feature list restated what
  this changelog already records. Design rationale that is not derivable
  from the code — the retrieval contract, the testing scope decision, the
  evaluation findings — was kept

### Decisions

- **Provider transport (measured, revisited):** the original choice was a
  direct connection to `api.anthropic.com`, with aggregators rejected on
  the grounds that two stacked abstraction layers make it impossible to
  tell whose behaviour is being observed. That decision was reopened
  against its own written trigger — a real access barrier — when the
  provider console proved closed to new accounts. Requests now route
  through an Anthropic-compatible gateway via `llm_base_url`, using
  `auth_token` (Bearer) rather than `api_key` (`x-api-key`). The trigger
  to revisit is direct provider access becoming available; `llm_base_url`
  defaults to `None`, so returning to the direct path is a `.env` change,
  not a code change
- **Gateway model identifiers are not provider-native.** The compatibility
  endpoint is wire-compatible on request and response shape but resolves
  model names against its own catalogue: the provider-native id
  (`claude-haiku-4-5-20251001`) returns `404`, and the gateway form
  (`anthropic/claude-haiku-4.5`) is required. Because model choice lives
  in configuration rather than in code, this was a one-line `.env` change
- **Gateway `usage` is richer than the native contract and will not be
  trusted.** Responses through the gateway carry `cost`, `cost_details`,
  `provider`, and `speed` alongside the two fields the provider's own API
  returns. Those extra fields disappear on the direct path, so the usage
  accounting in Step 9 will compute cost from `input_tokens` /
  `output_tokens` against our own price model rather than reading a
  precomputed figure
- **SDK defaults confirmed against documentation, not inferred from one
  run.** Observed `max_retries=2` and a 600-second default timeout match
  the published SDK behaviour. The agreement matters: a single
  observation through a gateway could have reflected an overridden value,
  and Step 8's retry budget depends on knowing which of the two is true
- **No SDK type crosses the boundary.** Five fields leave this module:
  text, stop, `input_tokens`, `output_tokens`, and model. The gateway's
  extra fields (`cost`, `provider`, `speed`, `service_tier`) are
  deliberately dropped — they vanish on the direct path, so code reading
  them would break silently the day direct access is restored. The
  response `id` is also excluded; its format differs between the two
  paths, and it gains a consumer only if Step 9's correlation work needs
  a provider-side identifier. No `ABC` or `Protocol` is introduced: with
  a single implementation, an interface can only be a copy of that
  implementation's signature. Trigger: a second provider actually being
  connected
- **The SDK's own retry policy is switched off (`max_retries=0`).** Left
  at its default of 2, it would multiply with the retry budget added in
  Step 8 rather than add to it — a three-attempt budget becoming nine
  billed calls. The failure would surface in Step 8, in a file that does
  not mention retries, which is why it is closed here
- **The error type carries data, not just a message.** `LLMError` holds
  the provider's status code and the provider exception's *type name* as
  a string. Without them, Step 7's taxonomy would have to either import
  the SDK to catch its exception classes — defeating the boundary — or
  parse error text. The message itself is a fixed string: SDK errors can
  attach the request body, and that body will hold prompts and, later,
  retrieved context. `getattr` is used for the status code because
  connection and timeout errors do not carry one
- **Stop reasons are mapped into this project's vocabulary, with a
  fallback.** The provider's strings are confined to a lookup table and
  an unrecognised value resolves to `UNKNOWN` instead of raising — a
  unilateral addition on the provider's side should not break working
  code. `stop_sequence` is folded into `COMPLETED` because no stop
  sequence is configured; trigger to split it: one actually being passed
- **The model identifier is read from the response, not from the
  request.** The gateway resolves model names against its own catalogue,
  so the configured value and the value actually used need not match.
  Step 9 prices what was used, not what was asked for
- **Nothing is wired into the application yet.** The client is not placed
  on `app.state` and no dependency accessor exists, because no consumer
  does. Wiring arrives in Step 6 alongside the endpoint that needs it.
  For the same reason `FakeLLMClient` has no error mode and records no
  calls; both are added when a test requires them
- **Translation is a module-level function rather than a method**, so it
  can be exercised without constructing a client or reaching the
  network. Testing the full client path through a mock HTTP transport
  was rejected: it would bind the tests to wire JSON while the client
  has no behaviour beyond one call and a translation. Trigger: the
  client acquiring behaviour beyond that
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