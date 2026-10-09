"""Uniform error envelope.

Every failure -- validation, business rule or unexpected -- is returned as::

    {"error": {"code": "...", "message": "...", "details": {...} | null}}

``details`` is always present and is ``null`` when the failure carries nothing
extra, so a client can read the key unconditionally.  The client never has to
special-case FastAPI's default ``{"detail": ...}``.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("pdp.errors")


class ApiError(Exception):
    """Expected, client-facing failure."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    # `details` is emitted even when empty so the shape never changes; this
    # matches ErrorBody in schemas.py, where details is Optional.
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Keep the useful part of pydantic's report, drop the internals.
        problems = [
            {"field": ".".join(str(part) for part in err.get("loc", ()) if part != "body"),
             "issue": err.get("msg", "invalid value")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body("validation_error", "Request body failed validation", {"problems": problems}),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Log the detail server-side, return an opaque message to the caller.
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", "Unexpected server error"),
        )
