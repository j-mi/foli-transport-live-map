"""One consistent JSON error shape for every failure the API can return.

    {"error": {"code": "STOP_NOT_FOUND", "message": "Stop 1234 does not exist ..."}}

Clients can switch on `code` (stable, machine readable) and show `message` (human readable).
Stack traces are logged on the server and never sent to the client.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def not_found(code: str, message: str) -> ApiError:
    return ApiError(404, code, message)


def gtfs_not_ready() -> ApiError:
    return ApiError(
        503,
        "GTFS_NOT_READY",
        "Static timetable data has not been loaded from Föli yet. Try again shortly.",
    )


def upstream_unavailable(message: str = "Föli is not responding right now.") -> ApiError:
    return ApiError(503, "UPSTREAM_UNAVAILABLE", message)


def _error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


_HTTP_CODES = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    429: "TOO_MANY_REQUESTS",
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(_error_body(exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"location": ".".join(str(p) for p in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            _error_body("VALIDATION_ERROR", "The request parameters are invalid.", details),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            _error_body(code, message), status_code=exc.status_code, headers=exc.headers
        )

    # The database being unreachable is an outage, not a bug: 503 with a clear code. asyncpg
    # raises plain OSError / TimeoutError while connecting; SQLAlchemy wraps the rest.
    async def _database_unavailable(request: Request, exc: Exception) -> JSONResponse:
        logger.warning("Database unavailable on %s: %s", request.url.path, exc)
        return JSONResponse(
            _error_body("DATABASE_UNAVAILABLE", "Saved data is temporarily unavailable."),
            status_code=503,
        )

    for exc_type in (OperationalError, InterfaceError, OSError, TimeoutError):
        app.add_exception_handler(exc_type, _database_unavailable)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            _error_body("INTERNAL_ERROR", "Something went wrong on our side."), status_code=500
        )
