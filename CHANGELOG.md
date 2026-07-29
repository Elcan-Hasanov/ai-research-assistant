# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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