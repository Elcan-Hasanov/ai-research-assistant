# 🤖 AI Research Assistant API

A backend service for collecting, storing, and exposing ArXiv research papers through a REST API built with **FastAPI** and **PostgreSQL**.

The project follows a long-term, iterative development approach. It started as a data collection pipeline (v1.0) and is gradually evolving into an AI-powered research assistant by introducing capabilities like semantic search, LLM integration, Retrieval-Augmented Generation (RAG), and AI agents in future releases.

**Current Version:** `v2.0.0`

---

## 📖 Table of Contents
- [Overview](#-overview)
- [Features](#-features)
- [Architecture & Project Structure](#-architecture--project-structure)
- [Technology Stack](#-technology-stack)
- [Getting Started & Installation](#-getting-started--installation)
- [API Overview & Documentation](#-api-overview--documentation)
- [Development Roadmap](#-development-roadmap)

---

## 📌 Overview

The **AI Research Assistant API** is the backend foundation of a research-oriented content platform.

Version 2.0 transforms the original command-line data collection workflow into a structured REST API while keeping the architecture modular, scalable, and ready for future expansion.

---

## ✨ Features (v2.0.0)

- **FastAPI REST API:** Asynchronous HTTP endpoints with built-in request validation and automatic OpenAPI specs.
- **Asynchronous PostgreSQL Access:** High-performance database communication using `asyncpg` with connection pooling managed via FastAPI lifespan events.
- **Layered Architecture:** Clear separation of concerns across API, Repository, Schema, and Core layers.
- **Dependency Injection:** Loosely coupled architecture utilizing FastAPI's dependency system for database connection management.
- **Configuration Management:** Environment-based settings powered by `pydantic-settings` and `.env` files.
- **Health Monitoring:** Liveness (`/health`) and DB readiness (`/health/ready`) probes for container orchestration compatibility.

---

## 🏗️ Architecture & Project Structure

The project follows a layered backend architecture based on the **Separation of Concerns** principle:

```text
Client ──► FastAPI Router ──► Repository Layer ──► PostgreSQL ──► Pydantic Schemas ──► JSON Response
```

### Directory Tree

```text
arxiv-research-assistant/
│
├── app/                        # Application core layer
│   ├── api/                    # API routes and request handlers
│   │   └── routers/            # Route modules (e.g., articles)
│   ├── core/                   # Application configuration, DB pool & global exceptions
│   ├── repositories/           # Data access layer (Raw SQL queries via asyncpg)
│   ├── schemas/                # Pydantic DTOs & validation models
│   ├── scrapers/               # External data ingestion clients (ArXiv API)
│   ├── services/               # Business logic, search & reranking layer
│   └── main.py                 # FastAPI application entry point & lifespan
│
├── scripts/                    # Standalone automation & ETL scripts
│   └── ingest_arxiv.py         # Script to fetch ArXiv data and populate DB
│
├── ai-research-assistant.ipynb # Jupyter notebook for experimentation & testing
├── .env.example                # Environment variables template
├── .gitignore                  # Git ignore rules
├── CHANGELOG.md                # Project version history
└── requirements.txt            # Project dependencies
```

---

## 🛠️ Technology Stack

| Category | Technology |
| --- | --- |
| **Language** | Python 3.12+ |
| **Framework** | FastAPI |
| **ASGI Server** | Uvicorn |
| **Database** | PostgreSQL |
| **Database Driver** | asyncpg |
| **Validation** | Pydantic v2 & Pydantic-Settings |
| **Data Collection** | Requests, BeautifulSoup4 |

---

## 🚀 Getting Started & Installation

### 1. Prerequisites

* Python 3.12 or higher
* PostgreSQL instance running
* Git

### 2. Clone & Setup Virtual Environment

```bash
git clone https://github.com/Elcan-Hasanov/arxiv-research-assistant.git
cd arxiv-research-assistant

python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy `.env.example` to create your local `.env` file:

```bash
cp .env.example .env
```

Update parameters with your local PostgreSQL credentials:

```env
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=arxiv_db

APP_NAME="AI Research Assistant API"
APP_VERSION="2.0.0"
```

### 5. Run Data Ingestion Script (Optional)

To populate your local PostgreSQL database with research papers from ArXiv:

```bash
python -m scripts.ingest_arxiv
```

### 6. Start the Application

```bash
uvicorn app.main:app --reload
```

The application will run at `http://127.0.0.1:8000`.

---

## 📑 API Overview & Documentation

FastAPI automatically generates interactive documentation. Once the app is running, visit:

* [Swagger UI](http://127.0.0.1:8000/docs)
* [ReDoc](http://127.0.0.1:8000/redoc)

### Core Endpoints

| Method | Endpoint | Purpose | Status Codes |
| --- | --- | --- | --- |
| `GET` | `/health` | Liveness check | `200` |
| `GET` | `/health/ready` | DB connection readiness check | `200`, `503` |
| `GET` | `/articles` | List articles with pagination & category filter | `200`, `422` |
| `GET` | `/articles/{arxiv_id}` | Fetch specific article details by ArXiv ID | `200`, `404`, `422` |

---

## 🗺️ Development Roadmap

* [x] **V1.0 — Data Infrastructure:** Scraping, PostgreSQL integration, Data cleaning, Filtering, Modular OOP structure.
* [x] **V2.0 — Backend Fundamentals:** FastAPI integration, Pydantic BaseSettings, Router architecture, Repository Pattern, Async API, Swagger UI.
* [ ] **V3.0 — Retrieval Fundamentals + Semantic Search:** Keyword Search (TF-IDF, BM25), Embedding (Sentence Transformers), PostgreSQL pgvector integration, Vector search endpoints.
* [ ] **V4.0 — LLM Application:** Native LLM API (OpenAI/Claude SDK), Prompt Template management, Structured Output (JSON responses), Response Streaming.
* [ ] **V5.0 — RAG (Retrieval-Augmented Generation) System:** Chunking Engine, Hybrid Search (BM25 + Vector), Context Injection, Citation mechanism.
* [ ] **V6.0 — Evaluation + Observability:** RAGAS metrics (Recall, Precision, Faithfulness), Langfuse / OpenTelemetry Tracing, Cost, Token and Latency tracking, Benchmark test dataset.
* [ ] **V7.0 — Productionization:** Docker & Docker Compose configuration, GitHub Actions CI/CD pipeline, Environment/Secret Management, Background Workers (Redis + Celery / RQ).
* [ ] **V8.0 — Agentic Research Assistant:** Tool Calling infrastructure, State & Workflow management (LangGraph etc.), Multi-step planning and cycles, Automatic report generation.
* [ ] **V9.0 — Production Agent:** Human-in-the-Loop, Trajectory Evaluation, Memory Management, Failure Recovery & Fallback mechanisms.