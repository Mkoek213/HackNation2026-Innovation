import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions import DomainError

logger = logging.getLogger(__name__)


def _error(status: int, type_: str, msg: str) -> JSONResponse:
    """Single-item error response matching FastAPI's validation format."""
    return JSONResponse(
        status_code=status,
        content={"detail": [{"type": type_, "loc": [], "msg": msg}]},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """FastAPI already formats RequestValidationError correctly — we only
    normalize the cases it doesn't cover."""

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.exception("Unexpected domain error")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": jsonable_encoder(exc.errors())},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Auth failures and routing 404s return a plain string detail —
        wrap it so clients only ever parse one shape."""
        if isinstance(exc.detail, list):
            detail = exc.detail
        else:
            detail = [{"type": "http_error", "loc": [], "msg": str(exc.detail)}]
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        """Last-resort net: races that slipped past repo-level pre-checks.
        UNIQUE/FK are the client's problem; CHECK/NOT NULL are ours."""
        orig = str(exc.orig).lower()
        if "unique constraint failed" in orig or "duplicate key" in orig:
            logger.info("Uniqueness violation: %s", exc.orig)
            return _error(409, "duplicate", "Resource with these values already exists")
        if "foreign key constraint failed" in orig:
            logger.info("FK violation: %s", exc.orig)
            return _error(409, "foreign_key_violation",
                          "Operation violates references between resources")
        logger.exception("Unexpected integrity violation")
        return _error(500, "internal_error", "Internal server error")
