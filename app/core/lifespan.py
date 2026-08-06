import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.core.database import create_db_pool
from app.core.embedding import create_embedding_model

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Own the lifecycle of expensive, long-lived, shared resources."""

    app.state.pool = await create_db_pool()
    
    app.state.embedding_model = create_embedding_model()

    logger.info("Application startup complete.")

    try:
        yield
    finally:
        await app.state.pool.close()
        logger.info("Application shutdown complete.")