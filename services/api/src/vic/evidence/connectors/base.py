"""Shared helpers for live-source connectors (R3-02).

Principles:
- "no results" and "source did not respond" are DIFFERENT outcomes with different warnings;
- bounded retries with backoff; one failing source/query never kills the others;
- warnings never contain URLs or API keys.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Awaitable, Callable

import httpx

from vic.contracts import Scope

from ..importer import Annotation, ParsedDocument, parse_text

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
Sleep = Callable[[float], Awaitable[None]]


class SourceUnavailable(Exception):
    """The source did not give a usable answer. `detail` is safe to show (no URL, no key)."""

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(f"{source}: {detail}")
        self.source = source
        self.detail = detail


@dataclass
class ConnectorResult:
    source: str
    documents: list[ParsedDocument] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: str = "ok"  # ok | partial | empty | unavailable


class RateLimiter:
    """Keeps at least `min_interval` seconds between requests."""

    def __init__(self, min_interval: float, *, sleep: Sleep = asyncio.sleep, clock=time.monotonic) -> None:
        self.min_interval = min_interval
        self._sleep = sleep
        self._clock = clock
        self._last = float("-inf")
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + self.min_interval - self._clock()
            if delay > 0:
                await self._sleep(delay)
            self._last = self._clock()


async def get_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict,
    source: str,
    limiter: RateLimiter | None = None,
    max_attempts: int = 3,
    backoff: float = 1.0,
    sleep: Sleep = asyncio.sleep,
    timeout: float = 20.0,
) -> httpx.Response:
    last = "no attempt made"
    for attempt in range(1, max_attempts + 1):
        if limiter:
            await limiter.wait()
        try:
            resp = await client.get(url, params=params, timeout=timeout)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = type(exc).__name__  # class name only: exception text may contain the URL/key
        else:
            if resp.status_code < 400:
                return resp
            last = f"HTTP {resp.status_code}"
            if resp.status_code not in RETRYABLE_STATUS:
                raise SourceUnavailable(source, last)
        if attempt < max_attempts:
            await sleep(backoff * 2 ** (attempt - 1))
    raise SourceUnavailable(source, f"{last} after {max_attempts} attempts")


def make_record_document(
    title: str,
    sections: list[tuple[str | None, str]],
    *,
    source_type: str,
    url: str | None,
    identifier: str | None,
    published_at: date | str | None,
    scope: Scope,
    limitations: list[str],
) -> ParsedDocument:
    """Turn a retrieved record into a ParsedDocument whose evidence = its paragraphs.

    Text is stored as retrieved; only leading '#' characters at line starts are removed
    because '#' is our heading marker.
    """
    parts: list[str] = []
    for heading, body in sections:
        if heading:
            parts.append(f"# {heading}")
        parts.append(re.sub(r"(?m)^\s*#+\s*", "", body))
    doc = parse_text(title, "\n\n".join(parts), published_at=published_at, identifier=identifier)
    doc.source_type = source_type
    doc.url = url
    doc.synthetic = False
    doc.annotations = [
        Annotation(excerpt=u.text, locator=u.locator, scope=scope, limitations=list(limitations))
        for u in doc.units
    ]
    return doc
