import logging
import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


async def handle_database_error(request: Request, exc: asyncpg.PostgresError) -> JSONResponse:
    logging.exception("Database error occurred: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Database service is currently unavailable. Please try again later."}
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logging.exception("Unhandled server error occurred: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected server error occurred."}
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(asyncpg.PostgresError, handle_database_error)
    app.add_exception_handler(Exception, handle_unexpected_error)