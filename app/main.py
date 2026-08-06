import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, status

from app.api.dependencies import get_db_pool
from app.api.routers import articles
from app.core.config import get_settings
from app.core.lifespan import lifespan
from app.core.exceptions import register_exception_handlers

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

register_exception_handlers(app)

app.include_router(articles.router)


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    return {"status": "ok"}


@app.get("/health/ready", tags=["System"])
async def readiness_check(
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> dict:
    """It checks the database connection and whether the system is ready to use."""
    try:
        await pool.fetchval("SELECT 1")
        return {"status": "ready"}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is not ready",
        )