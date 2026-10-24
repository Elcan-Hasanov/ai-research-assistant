# Known gaps

What is known to be missing or wrong and is still open. Each entry says why it
is accepted for now and gives its trigger — the observable condition under
which it is reassessed. An entry leaves this list when it is closed, and the
decision record of the version that closed it says how. The decisions these
gaps belong to are in [`decisions/`](decisions/).

Unless an entry says otherwise, it has been open since v4.0.

## LLM provider and client

- **The direct path has never run against the provider's own API.** It is
  implemented — selected by leaving `LLM_BASE_URL` empty — and its branch of
  the client factory is covered by offline tests. Running it needs a key from
  the provider, whose console was closed to new accounts, and the
  provider-native model id. The live test skips on it. Trigger: direct access
  becoming available, or a deployment on the direct path; it then gets a live
  test of its own, without the cost assertion.
- **The gateway may route a request to a provider that ignores a parameter.**
  The gateway balances requests across upstream providers — the recorded
  response came from Amazon Bedrock — and by default a provider that does not
  support a request parameter still receives the request and ignores the
  parameter. Whether `output_config`, sent through the Anthropic-compatible
  endpoint, takes part in that routing has not been verified. A provider that
  ignored it would return unconstrained text — without the schema, the model
  wrapped its JSON in a markdown fence 30 times in 30 — and local validation
  would turn that into a `500`. So far, all 31 calls of the
  response-variability measurement completed and parsed. Candidate: the
  gateway's `provider.require_parameters` option, which routes a request only
  to providers that support every parameter in it; unverified on this endpoint.
  Trigger: an extraction failing as `unparseable`, or the live test failing at
  the parse step, traced to the provider that served the call.
- **A gateway error sent inside a `200` raises `TypeError` in
  `to_completion`.** It is unclassified, surfaces as `500`, is recorded as an
  `unclassified` attempt, and is not retried: the retry layer reads only
  categories, and this failure has none. Whether it is transient, and so worth
  retrying, is unknown until it is classified. Documented and simulated, not
  observed live. Trigger: the first sighting.
- **The live test runs only when someone runs it.** A change on the provider's
  side is noticed at the next `pytest --live -m live`, not when it happens.
  Trigger: a scheduled CI job (v7), which passes `--live` explicitly.

## Generation

- **`summarize_article` has no consumer.** No route calls it, and its own
  guards — the not-found check and `_require_completed` — are pinned only
  through `extract_facts`: removing either from `summarize_article` breaks no
  test. Trigger: its first consumer.
- **`summarize_article`'s `max_tokens` is unmeasured.** The value is copied
  from extraction, where thirty calls used at most 122 of 500 tokens; a
  free-text summary has not been measured. Trigger: the method getting a
  consumer, or a `TRUNCATED` stop in its records.
- **Removing `StrictUndefined` breaks no test.** The registry checks the
  declared variables before rendering, which shadows it; what `StrictUndefined`
  alone guards, a missing attribute on a supplied object, no template uses.
  Trigger: a template that reads an attribute of a variable.

## Retries and timeouts

- **A caller that gives up does not stop the attempts.** At the ASGI level a
  handler runs to completion after the client disconnects, so retries go on,
  billed, for a reader who has left, and nothing inside the service can see it.
  `httpx`'s own default timeout is 5s, so the first Python client written with
  defaults carries a deadline this service cannot observe. Trigger: a caller
  that declares a deadline.
- **`Retry-After` in its HTTP-date form is read as absent,** and the retry
  falls back to the backoff. The raw header is not stored, so in the records a
  date-form header and no header look the same. Trigger: a date-form header
  observed.
- **A response that keeps trickling bytes is not bounded:** every phase timeout
  measures silence, and there is no deadline on the request. Trigger: an
  attempt in `llm_attempts` that outlasted connect plus read.

## Usage records

- **The attempts of a request wait in memory until the request ends,** so a
  process that dies between a provider call and the write loses that request's
  records. Accepted while the records serve cost visibility. Trigger: the
  records being used for billing.
- **A request's cost read from `llm_attempts` is a lower bound whenever one of
  its attempts failed:** a failed attempt's cost is unknown, and it may still
  have been billed. On the direct path no cost is known at all. The README's
  query counts priced attempts so that the bound shows. Trigger: a consumer
  that needs the exact cost of a request.
- **Cancelled attempts are not recorded:** the recorder catches `Exception`,
  not `BaseException`. Nothing cancels an attempt today. Trigger: the first
  change that does, such as a deadline.
- **`prompt_identifier` is stored as written,** so ordering by it is textual
  and `v10` sorts before `v9`. Trigger: records being grouped by prompt version
  (v6).

## Errors and logging

- **A chained `ValidationError` puts the failing field's value in a
  traceback.** Closed for the `AppError` path, whose errors are logged without
  their chain. `handle_database_error` still logs a traceback, deliberately
  (see its decision). Trigger: a leak observed on the `PostgresError` path.
- **The `log_level` half of `_CATEGORY_CONFIG` has no test.** Changing a
  category's level breaks nothing, and the levels carry a real decision —
  `NOT_FOUND` logs at `INFO` precisely because it is not a malfunction.
  Trigger: alerting rules binding to the levels (v6).
- **The request id in the fail-open log line is not asserted:** removing it
  from the message breaks no test. Nothing correlates log lines by request id
  yet. Trigger: tracing that does (v6).
- **The statuses `POST /articles/{arxiv_id}/facts` declares are kept consistent
  by hand.** The route's `responses`, `_CATEGORY_CONFIG` and the README's API
  table agree today, and no test ties them together. Trigger: a client
  generated from the OpenAPI document.
- **Readiness does not cover the LLM provider.** `/health/ready` checks the
  database and the embedding model; a revoked key or an unreachable gateway
  shows only on the first request that calls the provider. Trigger: a
  deployment that routes traffic by readiness (v7).

## Tests and tooling

- **The suite's one warning is not an error.** `StarletteDeprecationWarning`,
  raised when `fastapi.testclient` imports `starlette.testclient`, appears on
  every run; turning warnings into errors would stop the suite at import.
  Trigger: a CI run, where nobody reads the warnings summary (v7), or an
  upgrade that removes Starlette's `httpx` support.
- **The migration runner depends on the working directory** (open since v3.0).
  `scripts/migrate.py` reads `migrations/` relative to where it is started, so
  it runs only from the repository root, and the suite checks that the test
  database's schema exists instead of creating it. Trigger: a CI job that sets
  up its own database (v7).

## Naming

- **`search_articles` does not say which search it is,** while its sibling
  `semantic_search` does. The name was accurate in v2, when there was one
  search to name, and went stale when the second arrived rather than through
  any decision. Renaming touches the repository, the service, the router, a
  script and two test files, plus the `/articles/search` path, which is a
  public contract. Trigger: hybrid search (v5), which forces all three to be
  named at once; a path change belongs on a version boundary.