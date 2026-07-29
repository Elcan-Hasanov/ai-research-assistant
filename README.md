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
├── app/
│   ├── api/                # Route handlers (health.py, articles.py)
│   ├── core/               # App configuration, DB pool, global exception handlers
│   ├── repositories/       # Data access layer & raw SQL queries (asyncpg)
│   ├── schemas/            # Pydantic DTOs & validation schemas
│   └── main.py             # FastAPI initialization & middlewares
│
├── scraper/                # V1.0 ArXiv data collection pipeline
│
├── .env.example            # Template for environment variables
├── requirements.txt        # Frozen dependency versions
├── CHANGELOG.md            # Release history
└── README.md               # Project documentation
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

### 5. Start the Application

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

* [x] **v1.0:** CLI-based ArXiv Data Scraper & Ingestion Pipeline.
* [x] **v2.0 (Current):** Async REST API Layer, PostgreSQL (`asyncpg`), Repository Pattern, DTO Validation.
* [ ] **v3.0:** Docker Containerization & Docker Compose setup.
* [ ] **v4.0:** Text Processing Foundations (TF-IDF & Classical Retrieval).
* [ ] **v5.0:** Semantic Search with Vector Embeddings.
* [ ] **v6.0:** LLM Integration & Automated Paper Summarization.
* [ ] **v7.0:** Retrieval-Augmented Generation (RAG) System.
* [ ] **v8.0:** Autonomous AI Research Agent Workflow.