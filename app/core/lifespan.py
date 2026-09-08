import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import create_db_pool
from app.core.embedding import EmbeddingModel, create_embedding_model
from app.core.llm import create_llm_client

logger = logging.getLogger(__name__)


def _verify_embedding_dimension(model: EmbeddingModel) -> None:
    """Fail fast if the loaded model disagrees with the vector schema."""
    settings = get_settings()
    actual = model.dimension

    if actual is None:
        raise RuntimeError(
            f"Embedding model '{model.model_name}' did not report an output dimension."
        )

    if actual != settings.embedding_dimension:
        raise RuntimeError(
            f"Embedding dimension mismatch: model '{model.model_name}' produces "
            f"{actual}-d vectors, but the schema expects "
            f"{settings.embedding_dimension}-d. "
            f"Change EMBEDDING_DIMENSION and add a migration before starting."
        )

    logger.info("Embedding dimension verified: %d", actual)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Own the lifecycle of expensive, long-lived, shared resources.

    Acquisition happens inside try/finally, and release runs in reverse
    order. With two closeable resources, acquiring the second one is a
    step that can fail after the first one is already open.
    """
    pool = None
    llm_client = None

    try:
        pool = await create_db_pool()
        app.state.pool = pool

        model = create_embedding_model()
        _verify_embedding_dimension(model)
        app.state.embedding_model = model

        llm_client = create_llm_client()
        app.state.llm_client = llm_client

        logger.info("Application startup complete.")

        yield
    finally:
        if llm_client is not None:
            await llm_client.aclose()
        if pool is not None:
            await pool.close()
        logger.info("Application shutdown complete.")