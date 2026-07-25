from app.core.config import get_settings
from app.core.database import lifespan, get_db_connection
from fastapi import FastAPI, Depends
import asyncpg

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

@app.get("/health", tags=["System"])
async def health_check() -> dict:
    return {"status": "ok"}

@app.get("/health/ready", tags=["System"])
async def readiness_check(
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    await conn.fetchval("SELECT 1")
    return {"status": "ready"}