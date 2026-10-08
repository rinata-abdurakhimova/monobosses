"""Open Targets Platform connector: target IDENTITY check only (no evidence is created).

Endpoint (official docs): POST https://api.platform.opentargets.org/api/v4/graphql, no auth.
Gene-symbol-like terms are extracted from the mechanism text and searched as targets.
A term is resolved only on an exact symbol match with exactly one target; otherwise the
candidates are returned for clarification and nothing is chosen automatically.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

import httpx

from .base import RateLimiter, Sleep, SourceUnavailable, get_with_retries

GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"
QUERY = (
    "query($q: String!) { search(queryString: $q, entityNames: [\"target\"], "
    "page: {index: 0, size: 5}) { hits { id name entity description } } }"
)
_CHUNK = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")
_STOP = {"DNA", "RNA", "MRNA", "SIRNA", "ASO", "ADC", "CAR", "CAR-T", "TKI", "FDA", "EMA",
         "NSAID", "GPCR", "AAV", "CRISPR", "PROTAC", "BITE", "NOT", "AND", "THE"}


@dataclass
class TargetCandidate:
    id: str
    name: str
    description: str | None = None


@dataclass
class TargetResolution:
    status: str = "not_found"  # resolved | ambiguous | not_found | unavailable
    resolved: list[TargetCandidate] = field(default_factory=list)
    ambiguous: dict[str, list[TargetCandidate]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def extract_symbol_tokens(text: str, limit: int = 3) -> list[str]:
    """Gene-symbol-like words: contain a digit (JAK1, PD-1) or are ALL CAPS with 3+ chars (TNF).
    Lowercase prefixes like 'anti-' are dropped ('anti-PD-1' -> 'PD-1')."""
    out: list[str] = []
    for m in _CHUNK.finditer(text):
        parts = m.group(0).strip("-").split("-")
        while parts and parts[0].isalpha() and parts[0].islower():
            parts.pop(0)
        tok = "-".join(parts)
        if not (2 <= len(tok) <= 10) or not tok[0].isalpha():
            continue
        if tok.upper() in _STOP or tok.upper() in {t.upper() for t in out}:
            continue
        if any(c.isdigit() for c in tok) or (tok.isupper() and len(tok) >= 3):
            out.append(tok)
    return out[:limit]


def _fmt(cands: list[TargetCandidate]) -> str:
    return ", ".join(f"{c.name} ({c.id})" for c in cands)


class OpenTargetsConnector:
    name = "Open Targets"

    def __init__(self, client: httpx.AsyncClient, *, sleep: Sleep = asyncio.sleep,
                 min_interval: float = 0.2, max_attempts: int = 3, backoff: float = 1.0) -> None:
        self.client = client
        self._sleep, self._max_attempts, self._backoff = sleep, max_attempts, backoff
        self.limiter = RateLimiter(min_interval, sleep=sleep)

    async def _search(self, token: str) -> list[TargetCandidate]:
        resp = await get_with_retries(
            self.client, GRAPHQL, params={}, method="POST",
            json={"query": QUERY, "variables": {"q": token}},
            source=self.name, limiter=self.limiter, max_attempts=self._max_attempts,
            backoff=self._backoff, sleep=self._sleep,
        )
        try:
            body = resp.json()
            if body.get("errors"):
                raise ValueError
            hits = body["data"]["search"]["hits"]
            return [
                TargetCandidate(id=h["id"], name=h["name"], description=h.get("description"))
                for h in hits if h.get("entity") == "target"
            ]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise SourceUnavailable(self.name, "unexpected response format") from exc

    async def resolve(self, mechanism: str) -> TargetResolution:
        res = TargetResolution()
        tokens = extract_symbol_tokens(mechanism)
        if not tokens:
            res.warnings.append(
                "Open Targets: no gene-symbol-like term found in the mechanism text; "
                "target identity was not verified."
            )
            return res
        failed = 0
        for tok in tokens:
            try:
                cands = await self._search(tok)
            except SourceUnavailable as exc:
                failed += 1
                res.warnings.append(
                    f"Open Targets [{tok}]: source did not respond ({exc.detail}); target identity was "
                    "not verified. This is NOT evidence that the target name is unambiguous."
                )
                continue
            exact = list({c.id: c for c in cands if c.name.upper() == tok.upper()}.values())
            if len(exact) == 1:
                res.resolved.append(exact[0])
            elif len(exact) > 1:
                res.ambiguous[tok] = exact
                res.warnings.append(
                    f"Target identity is ambiguous: '{tok}' matches several targets ({_fmt(exact)}). "
                    "Searches used the literal text; please clarify which target is meant."
                )
            elif cands:
                res.ambiguous[tok] = cands
                res.warnings.append(
                    f"Target identity not confirmed: no exact symbol match for '{tok}'. Closest candidates: "
                    f"{_fmt(cands)}. Nothing was chosen automatically; please clarify."
                )
            else:
                res.warnings.append(f"Open Targets [{tok}]: no target found for this term.")
        if failed == len(tokens):
            res.status = "unavailable"
        elif res.ambiguous:
            res.status = "ambiguous"
        elif res.resolved:
            res.status = "resolved"
        return res
    