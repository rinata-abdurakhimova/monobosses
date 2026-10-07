from vic.contracts import ErrorEnvelope
from vic.storage import Repository, get_repository

_DESCRIPTIONS = {
    404: "Not found", 409: "Conflict", 413: "Payload too large", 415: "Unsupported media type",
    422: "Validation error", 501: "Not implemented", 503: "Service unavailable",
}


def get_repo() -> Repository:
    return get_repository()


def errors(*codes: int) -> dict:
    """OpenAPI `responses` entries that use the shared error envelope."""
    return {c: {"model": ErrorEnvelope, "description": _DESCRIPTIONS[c]} for c in codes}