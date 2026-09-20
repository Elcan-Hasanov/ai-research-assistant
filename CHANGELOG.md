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
- `LLMClient.aclose()`: the wrapper releases the transport it owns. The SDK
  client holds an HTTP connection pool, which holds sockets and TLS sessions —
  operating-system resources, not Python objects that garbage collection will
  reclaim. The embedding model's pattern does not carry over here: it had
  nothing to close
- `app/services/generation_service.py`: the first orchestration layer over a
  dependency that is non-deterministic, billed per call, and able to fail
  partially. Holds `GenerationService`, `NoSummaryError`, `GenerationError`,
  and two module-level helpers. `ArticleService` is untouched — the decision
  not to open a separate service for semantic search does not transfer, since
  that one rested on a shared repository and a shared `RetrievalResult`
  contract
- `GenerationService.extract_facts(arxiv_id)`: fetches one article by primary
  key, maps its columns onto the template's vocabulary, renders the prompt,
  carries the schema to the client, checks the stop reason, and validates the
  text. Input selection belongs to the caller; a system that selects the
  document by retrieval is v5
- `GenerationService.summarize_article(arxiv_id)`: free-text summary over the
  same pipeline, without a schema and without structured validation. It has no
  consumer yet — no endpoint is bound to it
- `POST /articles/{arxiv_id}/facts`. `POST` rather than `GET`: the call has a
  side effect (it spends money) and is not idempotent (the same request
  produces different output), neither of which a cacheable, safe method should
  claim
- `get_llm_client` and `get_generation_service` in `app/api/dependencies.py`.
  The client is read from `app.state`, not constructed per request: an object
  holding a connection pool is application-scoped for the same reason the
  database pool is
- LLM client acquisition and release in the application lifespan. `LLM_API_KEY`
  now has a consumer inside the application; until this step it was required at
  startup with nothing reading it
- `tests/test_service_generation.py`: eight service-level tests against a real
  database and a faked provider. The database is not replaced — the behaviour
  under test includes the repository query and the nullable column it returns.
  The provider is, because a real call is non-deterministic, billed and slow
- `app/core/errors.py`: `AppError` and `FailureCategory`. Every error type the
  application raises derives from one base, so a single handler registration
  catches all of them through the MRO walk. The module holds vocabulary only —
  no HTTP, no provider names, no import from an upper layer
- `NotFoundError`, and `NOT_FOUND` as the fourth category. It is the one error
  type defined here rather than in the module that raises it: the other seven
  each belong to one boundary, while a missing resource belongs to any lookup
  and two services in `app/services` raise it. Defining it in either would make
  one service import the other
- `public_message` on `AppError`: a second message with a second audience. The
  first goes to the log and may name templates, models or internal state; this
  one crosses the network and holds fixed text plus, at most, values the caller
  supplied in the request itself
- `log_context()` on `AppError`: the discriminating fields a fixed message
  cannot carry. `LLMError` returns its status and provider class name,
  `GenerationError` its stop reason, `ExtractionValidationError` its cause. The
  four types whose message already carries the detail return nothing
- `app_error_handler` and `_CATEGORY_CONFIG` in `app/core/exceptions.py`: one
  table mapping each category to a status code and a log level, read by direct
  indexing so a category missing from it fails loudly rather than defaulting
- `tests/test_error_taxonomy.py`: twelve tests pinning error type → category,
  public message and log context, with no HTTP involved
- `tests/test_error_mapping.py`: five tests pinning category → status code and
  response body. The project's first endpoint tests; the app is driven through
  `TestClient` with `get_generation_service` overridden, so no lifespan runs and
  no database, model or network is touched
- Three tests in `tests/test_llm_client.py` covering the provider-error
  translation end to end: a real `AsyncAnthropic` over an `httpx.MockTransport`,
  so the SDK builds the request and raises the exception exactly as in
  production and only the socket is replaced

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
- Lifespan acquires resources inside `try/finally` and releases them in reverse
  order. Previously the pool was created before the block and the teardown
  reached through `app.state` to close it; with a second closeable resource,
  failing to acquire the second would leak the first, and a teardown that reads
  `app.state` raises on a path where the attribute was never set
- `FakeLLMClient` records the arguments of every call. A canned response cannot
  show whether the service rendered the right prompt, mapped the right columns,
  or passed the schema at all; those are exactly the decisions this step
  introduces. The trigger for call recording was written as this step when the
  fake was first added. It still has no failure mode
- The seven existing error types derive from `AppError` and declare a category.
  `PromptError` declares one and both subtypes inherit it; inheritance of the
  field is allowed, because the requirement is enforced by the constructor
  signature rather than by a class-creation check
- `GenerationService.extract_facts` and `summarize_article` return
  `PaperFacts` and `str` rather than `… | None`, and raise `NotFoundError`
  instead. A return value cannot be bound to an exception handler, so moving
  the 404 into the taxonomy meant changing the service contract, not the router
- `POST /articles/{arxiv_id}/facts` no longer raises `HTTPException`; all five
  of its statuses now come from the same handler. `GET /articles/{arxiv_id}`
  still raises it from a return value and is left for a separate commit —
  `ArticleService` is untouched by this version
- The endpoint's `responses` declares every status it actually produces. The
  README table was carrying `200, 404, 500` and has been brought in sync
- `handle_unexpected_error` logs without a traceback. `ServerErrorMiddleware`
  re-raises unconditionally, so the ASGI server prints the chain anyway and the
  handler's own copy was the second one
- `app/core/exceptions.py` uses a module logger rather than the root logger,
  matching every other module in the application
- Step numbers removed from comments in application code and scripts. Nothing
  in the repository defines them, so the references resolved to nothing; the
  README roadmap defines versions, and a comment now either states its
  constraint or points at a version
- `ArticleService.get_by_arxiv_id` still returns `None` for a missing article
  and `GET /articles/{arxiv_id}` still raises `HTTPException` from that return
  value, so the application holds two 404 mechanisms. Closed in a separate
  commit immediately after this one; the method has no test today, so pinning
  its current behaviour comes first
  
### Fixed

- `LLMClient.aclose()` called `aclose()` on the SDK client, which does not
  have it. `AsyncAnthropic` exposes `close()`; the `aclose()` name belongs
  to the `httpx` client one layer below, which `AsyncAPIClient.close()`
  calls internally. Every shutdown raised `AttributeError` from the first
  statement of the lifespan's `finally` block, so `pool.close()` below it
  never ran and the database pool leaked — the same resource-leak shape the
  `try/finally` restructuring was written to prevent, arriving from the
  release side instead of the acquisition side. The wrapper keeps its own
  `aclose()` name: the `a` prefix marks a coroutine for this project's
  callers and does not have to match what the wrapped SDK calls it
  
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
- **The stop reason is a precondition, not an explanation.** The service checks
  `stop` before it calls the parser, rather than reading it to explain a failure
  the parser already reported. Two measured facts drive the ordering:
  constrained decoding guarantees syntax but not completion, so a truncation
  landing after the closing brace parses cleanly and a parse-first ordering
  accepts it silently; and a refusal returns prose, which parse-first would
  report as unparseable output — technically true, diagnostically wrong. The
  test that separates the two orderings feeds a truncated stop reason together
  with *valid* JSON; with malformed JSON both orderings fail and the test proves
  nothing
- **An article with no usable abstract is rejected before the request is sent.**
  Rendering a null value is silent — the template engine's strict-undefined mode
  fires on missing variables, not on `None`, and puts the literal string in the
  prompt. The response built from it satisfies the schema, so no downstream
  layer catches it. Substituting an empty string, as the embedding pipeline
  does for the same column, was rejected: the pattern transfers but its
  conclusion does not, because that path costs CPU and this one costs a billed
  call plus a persisted invention
- **Two error types, split by when they occur rather than by what caused them.**
  `NoSummaryError` is raised before any provider call and carries no token cost;
  `GenerationError` is raised after one and always does. That boundary is what
  the retry budget and the usage accounting will each need. `GenerationError`
  carries the stop reason as data rather than folding four situations into one
  message — truncation is retryable with a different token limit, a refusal is
  not retryable at all, and a context overflow is not retryable without
  shrinking the input. Same rule as the two error types before it: the type
  carries data, so the layer above classifies without importing anything or
  parsing a string. The message is a fixed string
- **Not-found stays a return value.** The service returns `None` and the router
  raises the HTTP error, as the article endpoint already does. An exception
  handler binds to an exception type and cannot bind to a return value, so
  moving this into the global handler would mean promoting a lookup's expected
  outcome into an exception — a separate decision, revisited in the step that
  builds the domain-error handlers
- **No endpoint test.** The handler registered for bare `Exception` returns its
  response and then re-raises, so the test client's default settings surface the
  exception instead of the 500. Writing the first HTTP-level test in the project
  to pin a behaviour the next step will change was not worth it; the three paths
  were exercised by hand against the running application instead
- **The second generation task shares preparation, not validation.** Fetching,
  the empty-abstract check and rendering became module-level helpers once a
  second method needed all three; the structured path keeps its schema and its
  parser, and the free-text path has neither. The stop check is shared, because
  an incomplete generation is unusable regardless of the output shape
  - **Classification is carried on the error type, not looked up in a central
  table.** A table would let a newly added type fall through to a default while
  nothing complained; a required keyword-only constructor argument means a type
  that supplies no category cannot be constructed at all. The enforcement is
  the signature, so no `__init_subclass__` check was written: a mechanism was
  drafted twice and both drafts leaked — the first through `hasattr` walking
  the MRO, the second through an `is_abstract` escape hatch that is itself
  inherited
- **One handler registered on the base type, not one per type.** Because
  classification is data, the handler body does not branch on the concrete
  type; per-type registration would register the same function eight times and
  force `app/core/exceptions.py` to import four upper-layer modules, breaking a
  direction rule that has held since v2. Trigger: one type needing HTTP
  behaviour different from its category's — the MRO walk resolves a specific
  registration ahead of the base one
- **HTTP status is not a field on the error type.** Error types carry a
  category in our own vocabulary; the translation to a status code happens only
  at the outermost layer. A status on the type would make a retry loop or a
  background worker — neither of them HTTP consumers — carry HTTP vocabulary
- **No `retryable` field.** Across all thirteen failure modes, retryability is
  `category is UPSTREAM_UNAVAILABLE`; a second hand-declared field is a second
  field that can contradict the first. Trigger: a mode becoming retryable
  without being upstream-unavailable — the two known candidates are a
  truncation retried with a larger `max_tokens` and a schema violation retried
  against non-deterministic sampling, and both already have their own triggers
- **Domain errors are logged without a traceback; unclassified ones keep
  theirs.** The exception chain carries what the error types were built to
  withhold: a chained `ValidationError` prints the rejected value in
  `input_value`, and an SDK error's message embeds the provider's full response
  body. The allow-list protects the error object, not Python's chain. A genuine
  bug has no structured fields, so for it the traceback is the only evidence
- **`handle_database_error` left as it is.** The concrete reason to touch it
  was a reported leak of connection parameters; the leak could not be
  reproduced this step, and a failed connection raises `ConnectionRefusedError`,
  which is not a `PostgresError` and never reaches that handler. Trigger: a
  leak observed on the `PostgresError` path
- **Not found joined the taxonomy.** An endpoint's success/failure line follows
  the contract it declares, not how ordinary the event is: `POST /facts`
  promises a `PaperFacts` object, and a missing article means it cannot be
  produced — the same reasoning already applied to a model refusal. The
  alternative kept status codes defined in two places, so the handler was not
  the single source of the set an API can return. The member needed three
  exceptions to the rules the other categories follow: `INFO` rather than
  `WARNING`/`ERROR`, an interpolated public message rather than a fixed
  literal, and a home in `errors.py` rather than in the module that raises it.
  Trigger: a fourth
- **`public_message` may interpolate values the caller supplied.** The rule was
  written as "never interpolates anything" and was relaxed deliberately when
  the 404 body had to keep naming the requested id. A value that arrived in the
  caller's own URL is not a leak; a provider response, model output or piece of
  internal state still is
- **The provider-error translation is tested through the real SDK, not through
  `FakeLLMClient`.** A double raising a hand-built `LLMError` would only assert
  what the test itself constructed. Driving a real `AsyncAnthropic` over a
  faked socket means the SDK maps the status to its own exception class and the
  client translates that, which is the behaviour the whole taxonomy rests on.
  It also covers the branch where `status_code` is absent: a transport-level
  connection failure produces `APIConnectionError`, a class that has no such
  attribute at all. `FakeLLMClient` still has no failure mode, and its written
  trigger fired this step and was declined
- **`RetryableError` and `WorkloadIdentityError` are out of scope because they
  are unreachable, not because they are unlikely.** `RetryableError` is an
  input to the SDK's retry policy — something middleware raises to request a
  retry — and the SDK never raises it; `WorkloadIdentityError` comes only from
  the workload-identity credential providers, which a plain `api_key` never
  engages. The earlier note describing the first as a gap in `except
  anthropic.APIError` was a reachability error
- **This file is doing four jobs and will be split at the version tag.**
  `Added`/`Changed`/`Fixed` are a changelog; `Decisions` is an architecture
  decision record, `Measurements` is the evidence behind it, and `Known gaps`
  is an issue list. Measured across versions the file grows roughly fivefold
  per release — 6, 21, 192, 470 lines — and `Decisions` is already 54% of the
  unreleased section. The lifetimes conflict: a changelog entry is written once
  and frozen, while a decision can be superseded, and three were this version.
  Writing a superseded decision into a frozen document is what produced the
  correction line that used to sit under the `test_llm_client.py` entry.
  Deferred to the `v4.0.0` tag rather than done now, because the version close
  rewrites this file anyway and splitting earlier means doing it twice.
  Measurements will move into the decision that used them, not into a file of
  their own; separating them would leave the decisions without their evidence

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
- **The two exception middlewares behave differently, and this decided the log
  discipline.** `Starlette.build_middleware_stack` routes handlers registered
  for `500` or bare `Exception` to `ServerErrorMiddleware` and everything else
  to `ExceptionMiddleware`. The first sends its response and then re-raises
  unconditionally; the second does not re-raise when a handler is found. The
  double traceback observed in Step 6 came from the first path, and registering
  specific types removes it without any change to the handler
- **Handler lookup walks `type(exc).__mro__`.** A handler on a base type
  catches every descendant, and when both a base and a child are registered the
  child wins regardless of registration order. Verified by running both
  orderings; `HTTPException` is resolved by integer status code first, ahead of
  the MRO walk
- **The SDK collapses every status ≥ 500 into `InternalServerError`.**
  `_make_status_error` maps 400, 401, 403, 404, 409, 413, 422, 429 and 529 to
  their own classes and everything else above 500 to one. `ServiceUnavailable`
  and `DeadlineExceeded` exist as classes but this code path never produces
  them, so 500, 502, 503 and 504 share a class name and only the number tells
  them apart — which is why the category is derived from `status_code` and not
  from the class
- **`extra=` is invisible with this log format.** Passing structured fields
  through `logging`'s `extra` parameter sets attributes on the record, and the
  formatter — `%(asctime)s - %(levelname)s - %(message)s` — never reads them.
  Nothing is printed and nothing warns. Fields go into the message through
  `%`-args instead
- **Test suite cost is an import, not the database.** Of a 6.9-second warm run,
  5.35s is collection and 1.55s is execution; excluding
  `tests/test_service_retrieval.py` from collection drops it to 0.07s, because
  that file is the only one that reaches `sentence_transformers` through
  `ArticleService`. The 28 database cases cost roughly 1.4s in total. A first
  cold run measured 23.85s and did not reproduce
  
### Known gaps

- Chaining the `ValidationError` puts the failing field's value in the
  traceback. Closed for the `AppError` path this step — those errors are logged
  without a chain. `handle_database_error` still logs one, deliberately: see
  the decision above
- The three conditional payload keys in `complete()` — `system`,
  `temperature`, `response_schema` — have no unit test. The fake SDK transport
  that was named as the blocker now exists in `tests/test_llm_client.py`, so
  the cost of closing this is a handler that records the outgoing request body
  rather than new infrastructure
- `create_llm_client` passes `max_retries=0` and nothing pins it. Left at the
  SDK default of 2, it would multiply with any retry budget layered above the
  client: a three-attempt budget becomes nine billed calls. The translation
  tests set the value themselves, so they pin their own setup rather than the
  factory's. Reassessed in Step 8, when a retry budget gives the invariant a
  live consumer
- The `log_level` half of `_CATEGORY_CONFIG` has no test. Changing a category's
  level breaks nothing, and the levels carry a real decision — `NOT_FOUND` logs
  at `INFO` precisely because it is not a malfunction. Reassessed in v6, when
  alerting rules bind to them

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