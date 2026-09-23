# AI Research Assistant API

A backend service for collecting, storing, and retrieving ArXiv research papers, built with **FastAPI**, **PostgreSQL**, and **pgvector**.

The project is developed as a single long-lived system rather than a series of disposable demos. It began as a data collection pipeline (v1.0), became a structured asynchronous API (v2.0), and now provides both lexical and semantic retrieval over a vector-indexed corpus (v3.0). v4.0 adds the first generation layer: a disciplined LLM integration with managed prompts, structured output, and token/cost accounting.

**Latest release:** `v3.0.0` · **In development:** `v4.0.0-dev`

---

## Architecture

A layered backend where each layer owns exactly one kind of decision:

```text
Client
  │
  ▼
FastAPI Router          HTTP concerns only — params, status codes
  │
  ▼
Service Layer           Retrieval and generation orchestration; query
  │                     encoding, distance → score conversion, prompt
  │                     rendering, stop-reason diagnosis, contract mapping
  ▼
Repository Layer        Raw SQL only — no ranking policy, no HTTP
  │
  ▼
PostgreSQL + pgvector   Lexical index (GIN) and vector index (HNSW)
```

```text
app/
├── api/              Routers and the composition root for request-scoped wiring
├── core/             Config, database pool, embedding model, lifespan, error handlers
├── generation/       LLM output contracts — response schemas, parsing, validation
├── prompts/          Versioned prompt templates and the loader that renders them
├── repositories/     Data access — raw SQL via asyncpg
├── schemas/          Pydantic DTOs
├── scrapers/         ArXiv ingestion client
└── services/         Retrieval and generation orchestration

migrations/           Numbered, forward-only SQL migrations
scripts/              Operational and laboratory scripts (migrate, ingest, backfill, measure_*)
tests/                Integration and unit tests
evaluation/           Retrieval evaluation set and findings
```

### Key design decisions

- **Shared retrieval contract.** Lexical and semantic search both return `RetrievalResult` (`document_id`, `score`, `method`), so a future hybrid ranker can combine them without either side leaking its internals upward.
- **Two-phase retrieve → hydrate.** Retrieval returns identifiers and scores; documents are fetched separately from the source-of-truth table. The contract stays stable when chunk-level retrieval arrives in v5.
- **Vectors are namespaced by model.** `article_embeddings` uses a composite primary key (`arxiv_id`, `model_name`), so vectors from different models never share a ranking. `content_hash` records the exact text that produced each vector, making the backfill idempotent.
- **Fail fast on mismatch.** The application verifies at startup that the loaded model's output dimension matches the configured schema dimension, rather than writing vectors the column will reject.
- **CPU-bound work leaves the event loop.** Query encoding runs on a worker thread (`asyncio.to_thread`).
- **Prompts are data, not code.** Templates live on disk as versioned files and are addressed by a `<name>.v<N>` identifier, so a generation can be tied to the exact prompt revision that produced it. Rendering is strict in both directions: a missing variable and an unexpected one both raise, because either one silently produces a prompt the caller did not intend.
- **Generation is constrained at the source and validated on arrival.** Requests carry a JSON Schema so the provider constrains decoding, and the response is still validated locally against the same Pydantic model that produced that schema. The two are not redundant: constrained decoding guarantees syntax and only while the provider supports it, while local validation is the contract and holds regardless. Prompt instructions alone were measured and rejected — asked in words not to wrap its JSON in a markdown fence, the model did so on every one of 30 calls. Validation is structural: output that satisfies the schema while being factually wrong passes, which is why faithfulness is a separate concern for v6.
- **Diagnosis lives where the evidence is complete.** A parse failure has four
  possible causes — the model produced malformed JSON, `max_tokens` cut the
  stream, the model refused, or the context window overflowed — and the parser
  cannot tell them apart, because the distinguishing evidence is the stop
  reason and that never reaches it. The service is the only layer holding the
  completion and the parse outcome at once, so the check sits there and runs
  *before* validation rather than as an explanation after it. Constrained
  decoding does not exempt a response from truncation: a cut that lands after
  the closing brace still parses, and a parse-first ordering would accept it
  silently.
- **Checks that can run before the call, do.** An article with no abstract is
  rejected before a request is sent. Rendering a null abstract produces the
  literal string `None` in the prompt — the strict-undefined setting does not
  catch it, because `None` is a value rather than a missing variable — and the
  answer built on it satisfies the schema while being invented. The embedding
  pipeline solved the same nullable column by substituting an empty string;
  that answer is not carried over, because there the cost was CPU and here it
  is a billed call plus a plausible wrong result.
- **Failures are classified by what the caller can do, not by where they came
  from.** Every error type carries one of four categories in the application's
  own vocabulary — neither the provider's nor HTTP's — and a single handler at
  the outermost layer is the only place that turns a category into a status
  code. Two failures raised in different modules share a status when they leave
  the caller the same options: a model refusal and an article with no abstract
  both surface as `422`. The category is also what a retry layer will read, so
  the decision to retry never has to be reconstructed from a status code chosen
  for a different audience. Domain errors are logged without their traceback,
  because the exception chain carries exactly what the error types were built to
  withhold — the value a validation rejected, the response body a provider
  attached. Unclassified failures keep theirs: for a genuine bug there is
  nothing else to log.

---

## Technology Stack

| Category | Technology |
| --- | --- |
| **Language** | Python 3.12+ |
| **Framework** | FastAPI · Uvicorn |
| **Database** | PostgreSQL 16 + pgvector (GIN and HNSW indexes) |
| **Database Driver** | asyncpg |
| **Embeddings** | Sentence Transformers (`BAAI/bge-small-en-v1.5`, 384-dim) |
| **LLM** | Anthropic SDK (Messages API) |
| **Validation** | Pydantic v2 · pydantic-settings |
| **Testing** | pytest · pytest-asyncio |
| **Data Collection** | Requests · BeautifulSoup4 |
| **Runtime** | Docker Compose |
| **Prompt Templates** | Jinja2 (`StrictUndefined`) |

---

## Getting Started

**Prerequisites:** Python 3.12+, Docker, Git.

```bash
git clone https://github.com/Elcan-Hasanov/ai-research-assistant.git
cd ai-research-assistant

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r requirements-dev.txt    # test dependencies, never in a production image
```

Create a `.env` file in the project root — see `.env.example` for the full key list:

```env
DB_NAME=arxiv_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

PYTHONPATH=.
APP_NAME="AI Research Assistant API"
APP_VERSION="4.0.0-dev"

EMBEDDING_MODEL_NAME="BAAI/bge-small-en-v1.5"
EMBEDDING_DEVICE="cpu"
EMBEDDING_DIMENSION=384
EMBEDDING_BATCH_SIZE=32
HNSW_EF_SEARCH=100

LLM_API_KEY=
LLM_BASE_URL="https://openrouter.ai/api/v1"
LLM_MODEL="anthropic/claude-haiku-4.5"
LLM_TIMEOUT_SECONDS=30
```

LLM_BASE_URL selects the transport. Requests currently route through an Anthropic-compatible gateway, because direct provider access is closed to new accounts. The two paths do not share model identifiers: the gateway resolves names against its own catalogue, so the provider-native id returns 404 through it. Leaving LLM_BASE_URL empty switches back to the direct path and requires the native id.

`EMBEDDING_DIMENSION` must match the vector column width defined in migration `005`; the application refuses to start if the loaded model disagrees. `LLM_API_KEY` is required at startup — a missing credential is a configuration error and should fail before the first request, not during it.

Then bring the system up:

```bash
docker compose up -d                 # PostgreSQL 16 with pgvector, named volume
python -m scripts.migrate            # forward-only, numbered, idempotent
python -m scripts.ingest_arxiv --categories cs.AI cs.CL cs.LG --target 5000
python -m scripts.backfill_embeddings    # add --dry-run to preview
uvicorn app.main:app --reload
```

Ingestion is idempotent (`ON CONFLICT DO UPDATE`), so cross-listed papers and repeated runs are handled without duplication. The backfill processes only articles without a current vector; its first run downloads the embedding model and may take several minutes. The application then runs at `http://127.0.0.1:8000`.

---

## API

Interactive documentation is generated automatically: [Swagger UI](http://127.0.0.1:8000/docs) · [ReDoc](http://127.0.0.1:8000/redoc)

| Method | Endpoint | Purpose | Status Codes |
| --- | --- | --- | --- |
| `GET` | `/health` | Application liveness check | `200` |
| `GET` | `/health/ready` | Database and embedding model readiness | `200`, `503` |
| `GET` | `/articles` | Paginated article listing with category filter | `200`, `422` |
| `GET` | `/articles/search` | Lexical full-text search with relevance ranking | `200`, `422` |
| `GET` | `/articles/semantic-search` | Vector similarity search by cosine distance | `200`, `422` |
| `GET` | `/articles/{arxiv_id}` | Fetch a single article by ArXiv ID | `200`, `404`, `500` |
| `POST` | `/articles/{arxiv_id}/facts` | Extract structured facts from one article via the LLM | `200`, `404`, `422`, `500`, `503` |

`POST /articles/{arxiv_id}/facts` returns a `PaperFacts` object — the problem
the paper addresses, its claimed contributions, and whether it reports
experiments of its own:

```json
{
  "problem": "There is a lack of publicly available Arabic datasets for evaluating cross-target generalization in stance detection.",
  "contributions": [
    "Released a dataset of manually annotated Arabic tweets",
    "Established baselines with transformer and zero-shot models"
  ],
  "evaluated": true
}
```

`404` means no article answers to that id. `422` means the article exists but
cannot be turned into facts: it has no abstract, the model declined it, or it
is longer than the context window — a different article may work. `503` means
the language model service was saturated or unreachable, so the same request
may succeed later. `500` means the failure is on this side — a bad credential,
a response the schema rejected, a bug — and there is nothing the caller can do
differently.

Both search endpoints return a paginated envelope of `RetrievalResult` objects:

```json
{
  "items": [
    { "document_id": "2608.01247", "score": 0.8332, "method": "semantic" }
  ],
  "total": 4981,
  "limit": 20,
  "offset": 0
}
```

`score` is comparable only within a single method. Lexical `ts_rank_cd` values and cosine-derived similarities live on different scales — a fact measured directly on this corpus, and the reason a future hybrid ranker will use rank fusion rather than score addition.

---

## Testing

The suite targets the surfaces where a wrong answer is **silent** — a swapped
`ORDER BY` direction, a dropped `WHERE` clause, a transposed `LIMIT`/`OFFSET`
pair, a deleted route whose requests are quietly absorbed by the catch-all
below it. Paths that fail loudly, and lab scripts whose output a human already
reads, are deliberately out of scope. This is not a coverage-driven suite.

Create a dedicated test database once, then apply the schema to it:

```sql
CREATE DATABASE arxiv_test;
```

```bash
DB_NAME=arxiv_test python -m scripts.migrate
```

```powershell
# Windows PowerShell
$env:DB_NAME = "arxiv_test"; python -m scripts.migrate; Remove-Item Env:\DB_NAME
```

```bash
pytest                    # full suite
pytest -m "not db"        # deselect the database-backed tests
pytest --collect-only -q  # verify every test is actually collected
```

-m "not db" deselects the tests that query PostgreSQL, but it does not currently let the suite run without one: a session-scoped readiness fixture connects before selection happens, so any subset still requires arxiv_test to exist. Making that fixture marker-aware is open work.

### Design

### Design

- **Isolation:** Each test runs inside an open transaction that is always rolled back, including when the test raises. Cleanup is a property of the transaction, not code at the end of the test, so it cannot be skipped by an early failure.
- **Separate database:** Tests never touch the working corpus. A behavioural guard refuses to run if the target database holds more articles than a test database plausibly would.
- **Hand-written test doubles, not mocks:** the embedding model and the LLM client are each replaced by a small duck-typed stand-in. Service-level doubles sit at the dependency boundary instead: one returns canned results or raises, another records which method the router dispatched to, because a request that reaches the wrong handler can still answer `200`. One double goes the other way and replaces nothing — the provider-error tests keep a real SDK client and fake only the socket beneath it, so the SDK still maps the status to its own exception class. The database is never replaced — the behaviour under test (`= ANY` semantics, `websearch_to_tsquery` conjunction, cosine distance) lives inside PostgreSQL, and mocking it would verify nothing. A double is written only where a dependency must be injected; the prompt registry and the output parser are pure and deterministic, so neither has one.
- **Mutation-calibrated:** Every test was validated by deliberately breaking the decision it claims to protect and confirming the test fails. A green suite is evidence only after this step.

---

## Evaluation & Measurement

`evaluation/` holds a hand-built comparison of the two retrieval strategies, stratified by query type (exact term, acronym, named entity, paraphrase, conceptual, out-of-corpus) before any query was written. Selected findings:

- **Failure modes differ more than success rates.** Lexical search fails honestly — zero results means "not found". Semantic search fails silently, returning full, high-scoring, topically plausible lists that do not contain the target.
- **Score is not a reliability signal.** The single highest semantic score observed across the whole evaluation sat on a wrong result.
- **Out-of-corpus queries expose the asymmetry.** Lexical returns nothing; semantic returns its nearest neighbours at scores indistinguishable from genuine matches.
- **The two scales are incomparable.** Lexical and semantic top scores differ by nearly an order of magnitude on the same corpus.

These artefacts form the first version of the benchmark dataset that v6's evaluation harness will build on.

The `scripts/measure_*.py` family characterises the system rather than testing it: token-length distributions against the model's sequence limit, query-prefix impact on ranking, and HNSW recall versus latency across `ef_search` settings. `scripts/probe_llm.py` is a one-shot discovery probe for the LLM provider — it reports the SDK's default timeout and retry policy and dumps a raw response object, deliberately deriving no thresholds from a single sample.

scripts/probe_structured.py does the same for structured output. scripts/measure_json_compliance.py is a measurement rather than a probe: it compares prompt-only instruction against a schema sent with the request over repeated calls on a fixed input, with the decision rule written before the run. Its two arms are interleaved rather than run in blocks — a blocked earlier version attributed a swing in gateway load to whichever arm happened to be running, and the causal claim built on it did not survive a second run.

---

## Roadmap

- [x] **v1.0 — Data Infrastructure:** Scraping, PostgreSQL integration, data cleaning, filtering, modular OOP structure.
- [x] **v2.0 — Backend Fundamentals & Lexical Search:** FastAPI, pydantic-settings, router architecture, Repository Pattern, asyncpg connection pooling, PostgreSQL full-text search, Swagger UI.
- [x] **v3.0 — Retrieval Fundamentals + Semantic Search:** Containerised pgvector runtime, SQL migrations, Sentence Transformers embeddings, `article_embeddings` schema, idempotent backfill pipeline, semantic search endpoint, HNSW index, lexical vs semantic evaluation, integration test suite.
- [ ] **v4.0 — LLM Application:** Native LLM API, prompt template management and versioning, structured output with schema validation, error taxonomy, retry/backoff, token and cost accounting.
- [ ] **v5.0 — RAG System:** Chunking engine, hybrid search (BM25 + vector, rank fusion), context injection, citation mechanism.
- [ ] **v6.0 — Evaluation + Observability:** RAGAS metrics, Langfuse / OpenTelemetry tracing, cost, token and latency tracking, benchmark dataset.
- [ ] **v7.0 — Productionization:** Docker image and Compose stack, GitHub Actions CI/CD, environment and secret management, background workers.
- [ ] **v8.0 — Agentic Research Assistant:** Tool calling, state and workflow management, multi-step planning, automatic report generation.
- [ ] **v9.0 — Production Agent:** Human-in-the-loop, trajectory evaluation, memory management, failure recovery and fallback.