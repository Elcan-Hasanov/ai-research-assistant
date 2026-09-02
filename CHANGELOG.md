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
- `jinja2` as a direct dependency. It was already present in the lockfile
  as a transitive dependency of `torch`; relying on that would mean the
  prompt layer breaks at import time the day the embedding stack is
  removed from the image
- `app/prompts/`: prompt content moved out of code and onto disk as
  versioned `.txt` files. A leaf package — it imports nothing else from
  this application
- `app/prompts/registry.py`: loads every template in a directory at import
  time and renders one on demand. Holds `PromptTemplate` (name, version,
  system, user, declared variables), `RenderedPrompt` (exactly the two
  pieces `LLMClient.complete()` accepts), `PromptError` with
  `PromptLoadError` / `PromptRenderError`, and the `load_templates` /
  `render_template` / `render` functions
- `app/prompts/templates/summarize_article.v1.txt`: the first prompt. Its
  variable names belong to the prompt's own vocabulary, not to the
  database schema — the template says `abstract` where the column says
  `summary`, and mapping the two is the calling service's job
- `tests/test_prompts.py`: seven tests covering the file contract
  (missing `user` section, malformed filename), both directions of
  variable mismatch, literal brace survival, an absent `system` section,
  and the happy path. No network, no database, no marker
- `app/generation/`: the home of LLM output contracts. A leaf package —
  it imports nothing else from this application, so parsing can be
  exercised with no database, no network, and no client. `app/schemas/`
  was rejected as the location: that package is the HTTP contract, and a
  model validated against a provider's output does not live at the HTTP
  boundary. A separate errors package was also rejected — in this project
  a domain error type lives in the module that raises it, as `LLMError`
  and `PromptRenderError` already do
- `app/generation/extraction.py`: holds `PaperFacts` (the expected
  response shape), `parse_paper_facts` (raw text in, validated object
  out), `ExtractionValidationError`, and `ExtractionErrorCause`
- `app/prompts/templates/extract_paper_facts.v1.txt`: the first prompt
  that asks for structured output. It describes three fields in prose and
  shows one compact example object rather than embedding a JSON Schema —
  the schema already travels as a request parameter, and carrying it in
  the prompt too would pay for it twice. Three different types, which is
  the smallest set that exercises three separate validation paths
- `tests/test_extraction.py`: three structural cases — valid JSON,
  unparseable text, and JSON that parses but violates the schema. A
  fourth case for output that satisfies the schema while being factually
  wrong is deliberately absent: this layer does not catch it, and testing
  for what a layer does not do misdescribes what the test protects.
  Fourth database-free, network-free test file in the project
- `scripts/probe_structured.py`: one-shot discovery probe. Answers three
  questions that cannot be answered by reading code — whether the model
  wraps its JSON without being asked, whether the gateway accepts
  `output_config`, and how many content blocks come back. Not a
  measurement script
- `scripts/measure_json_compliance.py`: repeated measurement over a fixed
  input, reporting a rate rather than a sample. Two arms, prompt-only and
  `output_config`, and a classifier that names the failure shape — a bare
  `0/10` does not distinguish a single systematic failure mode from three
  mixed ones, and the two lead to different decisions

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
- `CompletionStop` gains `REFUSED` and `CONTEXT_OVERFLOW`, and
  `_STOP_REASONS` maps `refusal` and `model_context_window_exceeded` onto
  them. The pinned SDK's `stop_reason` literal set holds seven values;
  four were mapped in Step 3 and the rest fell to `UNKNOWN`. That was
  correct at the time — nothing consumed them. A consumer arrived with
  structured output: a parse failure now has three candidate causes, and
  two of them were sitting in the same information-free bucket
- `LLMClient.complete()` gains an optional `response_schema`, and
  `FakeLLMClient` tracks the signature. The fake's job is to define the
  LLM contract for tests; if its signature drifts from the real one, a
  service that passes against the fake fails against the client and the
  fake stops being evidence

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
- **Template engine: Jinja2, configured with `StrictUndefined`.** Two
  constraints drove the choice: prompts carry literal braces (Step 5's
  structured-output schema examples), and a missing variable must be
  loud. `str.format` was rejected because escaping every brace stops the
  file from being plain text a human can copy into a playground —
  defeating the reason for putting prompts on disk at all.
  `string.Template` satisfies both constraints with zero dependencies and
  was the initial choice; it was reversed because it forces a planned
  engine migration once a prompt needs iteration, and the roughly half
  hour saved today does not cover that. Jinja2's unused loop support
  costs nothing: an unused capability inside a dependency carries no
  maintenance, unlike an unused abstraction one writes oneself
- **Both directions of variable mismatch are errors.** A declared
  variable the caller omitted, and a supplied variable the template never
  declared, both raise. The second is the one no library catches: Jinja2
  silently ignores extra keys, so the caller believes data was injected,
  the data never reaches the prompt, the model answers fluently from a
  partial input, and the call is billed. Mutation testing confirmed the
  asymmetry — removing the missing-variable check still fails loudly via
  `StrictUndefined` (with a worse message), while removing the
  extra-variable check produces no error at all
- **Errors carry the prompt identifier.** Jinja2's `UndefinedError` names
  the variable but not which prompt or which version failed; that
  information exists only in the registry. Two types, split by who can
  catch them: load failures happen at import and kill the process before
  anything can handle them, render failures happen in front of a caller
- **The version lives in the filename** (`<name>.v<N>.txt`), parsed into a
  name and an integer at load time. An integer rather than semver, because
  a prompt has no API surface for compatibility to describe; what Step 9
  persists and v6 groups by is order. In the filename rather than in
  file-internal metadata, because a frontmatter version can drift from the
  filename and nobody notices. A filename that does not match the pattern
  is an error, not a skipped file — skipping would hide the prompt's
  existence until something asked for it and got "not found"
- **Templates load once, at import, with no wiring.** The path resolves
  against the module's own location rather than the working directory,
  unlike `scripts/migrate.py`. Nothing is placed on `app.state` and no
  dependency accessor exists: that pattern is for resources that are
  expensive or need closing, and a few KB of text is neither. Eager
  loading buys fail-fast for free — a malformed template raises during
  import, so `uvicorn` never starts, rather than surfacing on the first
  request
- **One file per prompt, with named sections.** `user` required, `system`
  optional and rendered as `None` when absent, matching
  `complete(system=None)`. Two files per prompt was rejected because
  nothing forces them to move together across a version bump. TOML and
  YAML were rejected not because they cannot hold the text — a YAML block
  scalar can — but because they add a parser's worth of failure surface
  and stop the file from being plain text
- **Decision (calibrated):** all three checks this step introduces were
  verified by mutation. Removing the missing-variable check left one test
  red on the error message rather than the exception type; removing the
  extra-variable check left one test red with nothing raised at all.
  Removing `StrictUndefined` broke nothing, because the pre-check shadows
  it — recorded as a gap: the case it guards is a missing attribute on a
  supplied object, which no template in the project currently uses
- **Native structured output (measured, reversed).** The initial decision
  was to rely on prompt instructions alone and validate locally, on three
  grounds: gateway support was unverified, using it would widen Step 3's
  signature, and its only benefit — a lower validation-failure rate — had
  never been measured. All three were tested. The gateway accepts
  `output_config`. The failure rate was measured on a fixed input with
  the decision rule written first: **prompt-only produced directly
  parseable JSON 0 times in 30, `output_config` 30 times in 30.** Every
  prompt-only failure had the same shape — the model wrapped its JSON in
  a markdown fence, despite the prompt forbidding it in those words. A
  prompt instruction is a soft constraint competing with a formatting
  prior, not a rule. Stripping the fence in code was the third option and
  was rejected: it is correct only as long as one can enumerate the
  shapes a model might emit, and `{fence: 30}` is an observation about
  today's model, not a contract. Migration cost was at its lowest here —
  `complete()` still has no caller, so nothing broke
- **Local validation stays regardless.** Zero failures in 30 calls does
  not bound the true failure rate near zero; with no failures in 10
  trials the conservative upper bound on the failure rate is about 30%.
  No practical sample size would license removing the validation layer,
  which is why none was taken. Native constrains syntax; local validation
  is the contract, and the contract must not depend on a provider feature
- **The schema crosses the boundary as a plain `dict`.** The caller
  supplies JSON Schema; wrapping it in the provider's envelope is the
  client's job. Accepting a Pydantic model class instead was rejected:
  the client would then have to know that a task has a response shape,
  which is the same leak the prompt boundary already avoids. The
  observable form of this decision: `grep -rln "output_config" app/`
  returns one file. The schema's source is the Pydantic model in
  `extraction.py`; the service that will carry it to the client arrives
  in Step 6
- **One error type, carrying a discriminator.** Unparseable text and a
  schema violation reach Step 7's taxonomy at the same position — neither
  is retryable and the caller behaves identically — so two types would be
  a split with no consumer. Collapsing the *types* is not collapsing the
  *information*: `ExtractionErrorCause` distinguishes the two cases, in
  this project's vocabulary rather than Pydantic's. Naming the cause
  `json_invalid` after Pydantic's internal error string was rejected for
  the same reason provider stop reasons are mapped rather than passed
  through — a library upgrade would then change a domain contract
- **The error carries no model output.** Pydantic's `errors()` entries
  include an `input` key holding the value that failed, and `str()` on a
  `ValidationError` embeds it for some error types but not others. Only
  `type`, `loc`, and `msg` are copied, by allow-list rather than by
  deleting `input` — a deny-list silently leaks the day the library adds
  a field. Measured: with the canary in the field that fails validation,
  removing both defences leaves the leak test red; with the canary in any
  other field the same mutation passes all three tests
- **Field names belong to the prompt's vocabulary, not the database's.**
  Symmetric with the template-variable decision from Step 4: mapping is
  the calling service's job. The schema is kept minimal — every field is
  one more thing the model must get right and one more way validation can
  fail. A `reasoning` field, which gives a constrained model somewhere to
  think before committing to values, was considered and deferred: its
  benefit is unmeasured here, and it is reassessed together with any
  future change to the constraint decision
- **No repair layer, no retry on validation failure.** The scope says
  validate, not repair, and a repair loop is a retry under another name —
  both calls are billed. Trigger: validation failures being seen in
  practice and repeatably
- **Nothing is wired into the application.** No service, no endpoint,
  no dependency accessor. The consumer arrives in Step 6, which will wire
  both this and the client left unwired in Step 3
- **Truncation diagnosis is not this layer's job.** `parse_paper_facts`
  takes a `str`, so it never sees `stop`. That is what keeps the module a
  leaf, and the cost is that "the JSON is incomplete because `max_tokens`
  cut it" can only be established by whoever holds the completion and the
  error at once — the service, in Step 6
- **Decision (calibrated):** each behaviour this step claims to protect
  was verified by an isolating mutation. Widening the schema's field
  types to `Any` left exactly the schema-violation test red; forcing the
  error cause to a constant left exactly the unparseable test red;
  dropping `refusal` from the stop-reason table left exactly the new
  translation test red; carrying Pydantic's raw error entries left
  exactly the leak test red. A coarser mutation — replacing validation
  with a bare `json.loads` — turned all three extraction tests red and
  proved only that each protects *something*; how many tests a mutation
  reddens is not a measure of its value

### Measurements
- **JSON compliance, fixed input, decision rule written first.**
  Prompt-only 0/30 directly parseable, every failure a markdown fence;
  `output_config` 30/30. Three runs of ten per arm
- **Schema token cost.** Input tokens per call: 247 with no schema, 449
  with a hand-written schema (230 characters), 500 with the schema
  Pydantic generates (284 characters). The 51-token difference is
  entirely `title` metadata Pydantic attaches to every field and to the
  model; it constrains nothing. Not stripped: doing so requires a custom
  schema generator, and 51 tokens is not a measured cost problem.
  Trigger: the schema's share becoming a visible line item in Step 9's
  accounting, or the schema growing in v5. Note the density — 284
  characters cost 253 tokens, roughly 3.5 times the token-per-character
  rate of prose, because JSON punctuation tokenises badly
- **`additionalProperties` is not required by this gateway.** Pydantic's
  schema omits it and was accepted 10/10. Some providers' strict modes
  require it; this one does not
- **Input tokenisation is deterministic, sampling is not.** Input token
  counts were identical across every call in every run; output counts
  were not. Step 9's cost accounting can predict the input side and only
  the input side
- **The two arms have the same latency; the schema costs money, not
  time.** Under an interleaved run the medians are identical to two
  decimals (1.76s both arms) despite arm B sending 253 more input tokens
  per call. This is the prefill/decode asymmetry showing up as a number:
  input tokens are processed in parallel, output tokens sequentially, so
  a larger prompt buys a larger bill rather than a slower call. The
  earlier 6.5x gap between arms was an artefact of the blocked design and
  did not survive interleaving
- **Observed latency spans 1.43s to 12.34s** across all sessions for the
  same model and the same call. The 12.34s outlier was never reproduced
  and its cause is unknown; gateway-side load or provider selection is
  presumed. Recorded because Step 8's timeout threshold is a tail
  decision: the tail lives in this record, not in any single run's
  maximum, because a ten-call run in calm conditions reports a calm
  maximum. A threshold set from the ~1.8s median would have killed the
  12.34s call and billed the retry
- **Multi-block responses did not materialise on this path.** Both arms
  returned a single `text` block, so `to_completion` finds the payload
  and the concern that a structured response might arrive in a
  non-`text` block does not apply here

### Known gaps

- Chaining the `ValidationError` puts the failing field's value in the
  traceback, and the global handler logs tracebacks. The allow-list
  protects the error object, not Python's exception chain. Measured this
  step; the same family as the SDK attaching request bodies and asyncpg
  printing connection parameters. Logging discipline is Step 7
- The three conditional payload keys in `complete()` — `system`,
  `temperature`, `response_schema` — have no unit test. Testing them
  needs a fake SDK transport, and the method still has no application
  caller. Reassessed in Step 6, when the service supplies one

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