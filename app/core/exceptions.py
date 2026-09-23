import logging
import asyncpg

from typing import NamedTuple
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.core.errors import FailureCategory, AppError

logger = logging.getLogger(__name__)


async def handle_database_error(request: Request, exc: asyncpg.PostgresError) -> JSONResponse:
    logger.exception("Database error occurred: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Database service is currently unavailable. Please try again later."}
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled server error occurred: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred."}
    )


class CategoryConfig(NamedTuple):
    status_code: int
    log_level: int


_CATEGORY_CONFIG: dict[FailureCategory, CategoryConfig] = {
    FailureCategory.NOT_FOUND: CategoryConfig(
        status_code=404, log_level=logging.INFO
    ),
    FailureCategory.UNUSABLE_SOURCE: CategoryConfig(
        status_code=422, log_level=logging.WARNING
    ),
    FailureCategory.UPSTREAM_UNAVAILABLE: CategoryConfig(
        status_code=503, log_level=logging.ERROR
    ),
    FailureCategory.INTERNAL: CategoryConfig(
        status_code=500, log_level=logging.ERROR
    ),
}

def _format_context(exc: AppError) -> str:
    context = exc.log_context()
    if not context:
        return ""
    return " " + " ".join(f"{key}={value}" for key, value in context.items())

async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)

    config = _CATEGORY_CONFIG[exc.category]
    client_detail = exc.public_message

    logger.log(
        config.log_level,
        "[%s] %s%s",
        exc.category.value,
        exc,
        _format_context(exc),
    )

    return JSONResponse(
        status_code=config.status_code,
        content={"detail": client_detail}
    )

def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(asyncpg.PostgresError, handle_database_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
    app.add_exception_handler(AppError, app_error_handler)