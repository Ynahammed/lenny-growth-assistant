"""
Global Exception Handlers and Resilience Middleware.
"""
import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("lenny_growth.middleware.errors")


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Request validation error on {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error_type": "ValidationError",
            "message": "The request payload failed validation.",
            "details": exc.errors(),
            "path": request.url.path
        }
    )


async def database_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"Database operational error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error_type": "DatabaseError",
            "message": "Database connection or transaction error. Local data remains safe.",
            "details": str(exc),
            "suggestion": "Check your DATABASE_URL configuration or verify the local SQLite database."
        }
    )


async def connection_exception_handler(request: Request, exc: ConnectionError):
    logger.error(f"External service connection error on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={
            "error_type": "ProviderConnectionError",
            "message": str(exc),
            "suggestion": "If using Ollama, ensure 'ollama serve' is running. If using Anthropic, verify internet connectivity."
        }
    )


async def general_exception_handler(request: Request, exc: Exception):
    logger.critical(f"Unhandled exception on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_type": "InternalServerError",
            "message": "An unexpected error occurred while processing your request.",
            "details": str(exc)
        }
    )
