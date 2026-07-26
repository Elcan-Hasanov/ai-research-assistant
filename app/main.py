import asyncpg
from fastapi import Depends, FastAPI

from app.api.routers import articles
from app.core.config import get_settings
from app.core.database import get_db_connection, lifespan

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.include_router(articles.router)

@app.get("/health", tags=["System"])
async def health_check() -> dict:
    return {"status": "ok"}

@app.get("/health/ready", tags=["System"])
async def readiness_check(
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    await conn.fetchval("SELECT 1")
    return {"status": "ready"}