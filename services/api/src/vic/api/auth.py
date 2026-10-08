"""Server-side API authentication: Next.js sends X-API-Key from the server, never the browser."""
import secrets

from fastapi import Security
from fastapi.security import APIKeyHeader

from vic.config import get_settings
from vic.errors import ApiError

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str | None = Security(_header)) -> None:
    secret = get_settings().api_shared_secret
    if not secret:
        return  # allowed only in development: production start-up refuses an empty secret
    if not key or not secrets.compare_digest(key.encode("utf-8"), secret.encode("utf-8")):
        raise ApiError(401, "unauthorized", "Missing or invalid API key")