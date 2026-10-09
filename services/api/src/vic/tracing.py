"""Trace helpers: secret scrubbing and a config version hash. Traces must never hold secrets."""
import hashlib
import json
from typing import Any, Iterable

_SECRET_KEY_PARTS = ("api_key", "secret", "password", "authorization")


def scrub(obj: Any, secrets: Iterable[str] = ()) -> Any:
    """Redact secret-looking keys and any literal secret value found inside strings."""
    values = [s for s in secrets if s and len(s) >= 6]

    def walk(x: Any) -> Any:
        if isinstance(x, dict):
            out = {}
            for key, value in x.items():
                lowered = str(key).lower()
                if lowered == "token" or any(p in lowered for p in _SECRET_KEY_PARTS):
                    out[key] = "[redacted]"
                else:
                    out[key] = walk(value)
            return out
        if isinstance(x, (list, tuple)):
            return [walk(i) for i in x]
        if isinstance(x, str):
            for secret in values:
                x = x.replace(secret, "[redacted]")
        return x

    return walk(obj)


def config_version(config: dict) -> str:
    raw = json.dumps(config, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]