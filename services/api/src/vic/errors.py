"""Single error envelope: {"error": {"code", "message", "retryable"}} (contract section 3)."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("vic")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable


def envelope(code: str, message: str, retryable: bool = False) -> dict:
    return {"error": {"code": code, "message": message, "retryable": retryable}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status,
                            content=envelope(exc.code, exc.message, exc.retryable))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        parts: list[str] = []
        for err in exc.errors()[:5]:
            loc = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path"))
            msg = str(err.get("msg", "invalid value")).removeprefix("Value error, ")
            parts.append(f"{loc}: {msg}" if loc else msg)
        # Never echo the request body back (it may contain private program data).
        return JSONResponse(status_code=422,
                            content=envelope("validation_error", "; ".join(parts) or "Invalid request"))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(status_code=exc.status_code,
                            content=envelope(code, str(exc.detail), exc.status_code >= 500))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error")  # traceback stays in server logs only
        return JSONResponse(status_code=500,
                            content=envelope("internal_error", "Internal server error"))