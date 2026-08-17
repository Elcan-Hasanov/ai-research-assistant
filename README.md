# 🤖 AI Research Assistant API

A backend service for collecting, storing, and retrieving ArXiv research papers through a REST API built with **FastAPI**, **PostgreSQL**, and **pgvector**.

The project follows a long-term, iterative development approach. It started as a data collection pipeline (v1.0), became a structured asynchronous API (v2.0), and now provides both lexical and semantic retrieval over a vector-indexed corpus (v3.0). It is gradually evolving into an AI-powered research assistant through LLM integration, Retrieval-Augmented Generation (RAG), and agentic workflows in future releases.

**Current Version:** `v3.0.0`

---

## 📖 Table of Contents
- [Overview](#-overview)
- [Features](#-features-v300)
- [Architecture & Project Structure](#️-architecture--project-structure)
- [Technology Stack](#️-technology-stack)
- [Getting Started & Installation](#-getting-started--installation)
- [API Overview & Documentation](#-api-overview--documentation)
- [Testing](#-testing)
- [Evaluation & Measurement](#-evaluation--measurement)
- [Development Roadmap](#️-development-roadmap)

---

## 📌 Overview

The **AI Research Assistant API** is the backend foundation of a research-oriented content platform.

Version 3.0 adds the project's first real retrieval capability. Alongside the existing PostgreSQL full-text search, articles are now embedded into a 384-dimensional vector space with Sentence Transformers, stored in a dedicated `article_embeddings` table via `pgvector`, and searched by cosine distance with an HNSW index available for scale.

Both retrieval paths return the same shape — a shared `RetrievalResult` contract of document id, score, and the method that produced it — so a future hybrid ranker can combine them without either side leaking its internals upward.

The release also introduces schema versioning through numbered SQL migrations, a containerised database runtime, an idempotent embedding backfill pipeline, an integration test suite, and a hand-built evaluation set comparing the two retrieval strategies.

---

## ✨ Features (v3.0.0)

### Retrieval

- **Semantic Search:** `/articles/semantic-search` ranks articles by pgvector cosine distance (`<=>`) against a target model's stored embeddings. Query encoding runs on a worker thread (`asyncio.to_thread`) so the event loop is never blocked by CPU-bound inference.
- **Lexical Search:** `/articles/search` uses PostgreSQL native full-text search — a generated `tsvector` column with weighted title and abstract, a GIN index, `websearch_to_tsquery`, and `ts_rank_cd` relevance scoring.
- **Shared Retrieval Contract:** Both paths map onto `RetrievalResult` (`document_id`, `score`, `method`). Retrieval returns identifiers and scores; documents are hydrated separately from the source-of-truth table, keeping the contract stable when chunk-level retrieval arrives in V5.
- **Batch Hydration:** `ArticleRepository.get_by_ids()` fetches documents for a set of retrieval results in a single round-trip. Row order is deliberately unspecified — ranking belongs to the caller that produced it.

### Embedding Infrastructure

- **Local Inference:** Sentence Transformers (`BAAI/bge-small-en-v1.5`) loaded once per process at application startup, injected through the composition root rather than constructed inside the service.
- **Vector Storage:** Dedicated `article_embeddings` table with a `vector(384)` column and a composite primary key (`arxiv_id`, `model_name`), so vectors from different models never share a ranking. `content_hash` records the exact text that produced each vector.
- **Idempotent Backfill:** `scripts/backfill_embeddings.py` embeds only articles missing a vector, and re-embeds those whose `content_hash` no longer matches the current embedding text. Safe to re-run at any time.
- **Startup Dimension Check:** The application verifies at startup that the loaded model's output dimension matches the configured schema dimension, failing fast instead of writing vectors the column will reject.
- **HNSW Index:** `vector_cosine_ops` with explicitly pinned build parameters (`m=16`, `ef_construction=64`) rather than extension defaults, since the server image tag is mutable.

### Database & Runtime

- **Containerised Database:** `pgvector/pgvector:pg16` with a named volume for durable data and a healthcheck for orchestration.
- **Schema Versioning:** Numbered SQL migrations applied by an async runner (`scripts/migrate.py`) that records applied versions in a `schema_migrations` table.
- **Connection Pooling:** Managed through FastAPI lifespan events. The repository accepts either a `Pool` or a `Connection`, which allows transactional writes and makes the data layer testable in isolation.

### Foundations (from v2.0)

- Fully asynchronous FastAPI endpoints with automatic OpenAPI specs.
- Layered architecture: Routers → Services → Repositories (raw SQL via `asyncpg`) → Schemas.
- Environment-based configuration via `pydantic-settings` with `SecretStr` credential handling.
- Liveness (`/health`) and readiness (`/health/ready`) probes; readiness also verifies the embedding model was loaded.

---

## 🏗️ Architecture & Project Structure

The project follows a layered backend architecture based on the **Separation of Concerns** principle. Each layer owns exactly one kind of decision:

```text
Client
  │
  ▼
FastAPI Router          HTTP concerns only — params, status codes
  │
  ▼
Service Layer           Retrieval orchestration, query encoding,
  │                     distance → score conversion, contract mapping
  ▼
Repository Layer        Raw SQL only — no ranking policy, no HTTP
  │
  ▼
PostgreSQL + pgvector   Lexical index (GIN) and vector index (HNSW)
```

### Directory Tree

```text
arxiv-research-assistant/
│
├── app/                          # Application core
│   ├── api/
│   │   ├── routers/              # Endpoint modules (articles.py)
│   │   └── dependencies.py       # Composition root for request-scoped wiring
│   ├── core/
│   │   ├── config.py             # pydantic-settings configuration
│   │   ├── database.py           # asyncpg pool factory + pgvector codec registration
│   │   ├── embedding.py          # Sentence Transformers inference wrapper
│   │   ├── lifespan.py           # Startup/shutdown: pool, model, dimension check
│   │   └── exceptions.py         # Global error handlers
│   ├── repositories/             # Data access layer (raw SQL via asyncpg)
│   ├── schemas/                  # Pydantic DTOs (article.py, retrieval.py)
│   ├── scrapers/                 # ArXiv ingestion client
│   ├── services/                 # Retrieval orchestration and contract mapping
│   └── main.py                   # Application entry point
│
├── migrations/                   # Numbered, forward-only SQL migrations
│   ├── 001_baseline_articles.sql
│   ├── 002_enable_pgvector.sql
│   ├── 003_categories_array_and_published_at_index.sql
│   ├── 004_lexical_search.sql
│   ├── 005_create_article_embeddings.sql
│   ├── 006_add_embedding_updated_at.sql
│   ├── 007_hnsw_index.sql
│   └── 008_set_hnsw_defaults.sql
│
├── scripts/                      # Standalone operational and measurement scripts
│   ├── migrate.py                # Migration runner
│   ├── ingest_arxiv.py           # Batch ArXiv ingestion (paginated, category-scoped)
│   ├── backfill_embeddings.py    # Idempotent embedding pipeline
│   ├── measure_embeddings.py     # Token-length and model characterisation
│   ├── measure_query_prefix.py   # Query-prefix impact on ranking
│   ├── measure_ann_index.py      # HNSW recall/latency characterisation
│   └── compare_retrieval.py      # Lexical vs semantic comparison harness
│
├── tests/                        # Integration and unit tests
│   ├── conftest.py               # Fixtures: test database, isolation, fake model
│   ├── factories.py              # Test data helpers
│   ├── test_schemas.py
│   ├── test_repository_get_by_ids.py
│   ├── test_repository_retrieval.py
│   └── test_service_retrieval.py
│
├── evaluation/                   # Retrieval evaluation artefacts
│   ├── queries_v1.json           # 18-query stratified evaluation set
│   └── findings_step12.md        # Lexical vs semantic comparison findings
│
├── docker-compose.yml            # pgvector-enabled PostgreSQL runtime
├── pyproject.toml                # pytest configuration
├── requirements.in / .txt        # Application dependencies
├── requirements-dev.in / .txt    # Test dependencies (never installed in production)
├── CHANGELOG.md
└── README.md
```

---

## 🛠️ Technology Stack

| Category | Technology |
| --- | --- |
| **Language** | Python 3.12+ |
| **Framework** | FastAPI |
| **ASGI Server** | Uvicorn |
| **Database** | PostgreSQL 16 + pgvector (GIN and HNSW indexes) |
| **Database Driver** | asyncpg |
| **Embeddings** | Sentence Transformers (`BAAI/bge-small-en-v1.5`, 384-dim) |
| **Validation** | Pydantic v2 & pydantic-settings |
| **Testing** | pytest, pytest-asyncio |
| **Data Collection** | Requests, BeautifulSoup4 |
| **Runtime** | Docker Compose |

---

## 🚀 Getting Started & Installation

### 1. Prerequisites

- Python 3.12 or higher
- Docker (for the pgvector-enabled PostgreSQL container)
- Git

### 2. Clone & Set Up the Virtual Environment

```bash
git clone https://github.com/Elcan-Hasanov/arxiv-research-assistant.git
cd arxiv-research-assistant

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

Test dependencies are kept in a separate manifest so they are never installed into a production image:

```bash
pip install -r requirements-dev.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
DB_NAME=arxiv_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

APP_NAME="AI Research Assistant API"
APP_VERSION="3.0.0"

EMBEDDING_MODEL_NAME="BAAI/bge-small-en-v1.5"
EMBEDDING_DEVICE="cpu"
EMBEDDING_DIMENSION=384
EMBEDDING_BATCH_SIZE=32
HNSW_EF_SEARCH=100
```

`EMBEDDING_DIMENSION` must match the vector column width defined in migration `005`. The application verifies this at startup and refuses to serve if the loaded model disagrees.

### 5. Start the Database

```bash
docker compose up -d
```

This launches PostgreSQL 16 with the pgvector extension available, backed by a named volume so data survives container restarts.

### 6. Apply Migrations

```bash
python -m scripts.migrate
```

Migrations are forward-only, numbered, and idempotent — already-applied versions are skipped. Run this from the repository root.

### 7. Ingest Articles

```bash
python -m scripts.ingest_arxiv --categories cs.AI cs.CL cs.LG --target 5000
```

Ingestion is idempotent (`ON CONFLICT DO UPDATE`), so cross-listed papers and repeated runs are handled without duplication.

### 8. Generate Embeddings

```bash
python -m scripts.backfill_embeddings
```

Only articles without a current vector are processed. Preview a run without writing:

```bash
python -m scripts.backfill_embeddings --dry-run
```

The first run downloads the embedding model and may take several minutes.

### 9. Start the Application

```bash
uvicorn app.main:app --reload
```

The application runs at `http://127.0.0.1:8000`.

---

## 📑 API Overview & Documentation

FastAPI generates interactive documentation automatically. With the app running:

- [Swagger UI](http://127.0.0.1:8000/docs)
- [ReDoc](http://127.0.0.1:8000/redoc)

### Core Endpoints

| Method | Endpoint | Purpose | Status Codes |
| --- | --- | --- | --- |
| `GET` | `/health` | Application liveness check | `200` |
| `GET` | `/health/ready` | Database and embedding model readiness | `200`, `503` |
| `GET` | `/articles` | Paginated article listing with category filter | `200`, `422` |
| `GET` | `/articles/search` | Lexical full-text search with relevance ranking | `200`, `422` |
| `GET` | `/articles/semantic-search` | Vector similarity search by cosine distance | `200`, `422` |
| `GET` | `/articles/{arxiv_id}` | Fetch a single article by ArXiv ID | `200`, `404`, `422` |

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

## 🧪 Testing

The suite targets the surfaces where a wrong answer is **silent** — a swapped `ORDER BY` direction, a dropped `WHERE` clause, a transposed `LIMIT`/`OFFSET` pair. Paths that fail loudly, and lab scripts whose output a human already reads, are deliberately out of scope. This is not a coverage-driven suite.

### Setup

Create a dedicated test database once:

```sql
CREATE DATABASE arxiv_test;
```

Apply the schema to it:

```bash
DB_NAME=arxiv_test python -m scripts.migrate
```

```powershell
# Windows PowerShell
$env:DB_NAME = "arxiv_test"
python -m scripts.migrate
Remove-Item Env:\DB_NAME
```

### Running

```bash
pytest                    # full suite
pytest -m "not db"        # schema tests only, no database required
pytest --collect-only -q  # verify every test is actually collected
```

### Design

- **Isolation:** Each test runs inside an open transaction that is always rolled back, including when the test raises. Cleanup is a property of the transaction, not code at the end of the test, so it cannot be skipped by an early failure.
- **Separate database:** Tests never touch the working corpus. A behavioural guard refuses to run if the target database holds more articles than a test database plausibly would.
- **One test double:** Only the embedding model is replaced, by a hand-written deterministic stand-in. The database is real — the behaviour under test (`= ANY` semantics, `websearch_to_tsquery` conjunction, cosine distance) lives inside PostgreSQL, and mocking it would verify nothing.
- **Mutation-calibrated:** Every test was validated by deliberately breaking the decision it claims to protect and confirming the test fails. A green suite is evidence only after this step.

---

## 📊 Evaluation & Measurement

The `evaluation/` directory holds a hand-built comparison of the two retrieval strategies, stratified by query type (exact term, acronym, named entity, paraphrase, conceptual, out-of-corpus) before any query was written.

Selected findings:

- **Failure modes differ more than success rates.** Lexical search fails honestly — zero results means "not found". Semantic search fails silently, returning full, high-scoring, topically plausible lists that do not contain the target.
- **Score is not a reliability signal.** The single highest semantic score observed across the whole evaluation sat on a wrong result.
- **Out-of-corpus queries expose the asymmetry.** Lexical returns nothing; semantic returns its nearest neighbours at scores indistinguishable from genuine matches.
- **The two scales are incomparable.** Lexical and semantic top scores differ by nearly an order of magnitude on the same corpus.

These artefacts form the first version of the benchmark dataset that V6's evaluation harness will build on.

The `scripts/measure_*.py` family characterises the system rather than testing it: token-length distributions against the model's sequence limit, query-prefix impact on ranking, and HNSW recall versus latency across `ef_search` settings.

---

## 🗺️ Development Roadmap

- [x] **V1.0 — Data Infrastructure:** Scraping, PostgreSQL integration, data cleaning, filtering, modular OOP structure.
- [x] **V2.0 — Backend Fundamentals & Lexical Search:** FastAPI, Pydantic BaseSettings, router architecture, Repository Pattern, asyncpg connection pooling, PostgreSQL full-text search, Swagger UI.
- [x] **V3.0 — Retrieval Fundamentals + Semantic Search:** Containerised pgvector runtime, SQL migrations, Sentence Transformers embeddings, `article_embeddings` schema, idempotent backfill pipeline, semantic search endpoint, HNSW index, lexical vs semantic evaluation, integration test suite.
- [ ] **V4.0 — LLM Application:** Native LLM API (OpenAI/Claude SDK), prompt template management, structured output, response streaming.
- [ ] **V5.0 — RAG System:** Chunking engine, hybrid search (BM25 + vector, rank fusion), context injection, citation mechanism.
- [ ] **V6.0 — Evaluation + Observability:** RAGAS metrics, Langfuse / OpenTelemetry tracing, cost, token and latency tracking, benchmark dataset.
- [ ] **V7.0 — Productionization:** Docker image and Compose stack, GitHub Actions CI/CD, environment and secret management, background workers.
- [ ] **V8.0 — Agentic Research Assistant:** Tool calling, state and workflow management, multi-step planning, automatic report generation.
- [ ] **V9.0 — Production Agent:** Human-in-the-loop, trajectory evaluation, memory management, failure recovery and fallback.