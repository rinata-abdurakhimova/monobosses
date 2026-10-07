"""R3-01: import text / JSON / PDF into a contract EvidencePack.

bytes/text -> ParsedDocument (canonical text, hash, citeable units, annotations)
           -> build_pack() (dedup, stable IDs, contract objects) -> ImportResult
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from vic.contracts import Evidence, EvidencePack, RunContext, Scope, Source, UploadedDocument

from .errors import InvalidDocument, UnreadableDocument, UnsupportedDocument
from .normalization import (
    Unit,
    content_hash,
    evidence_id_for,
    excerpt_in_text,
    normalize_text,
    parse_date,
    source_id_for,
    split_units,
    squash,
)
from .pdf_parser import extract_pages

MAX_TEXT_CHARS = 2_000_000
DEFAULT_SCOPE = Scope.APPROACH  # safer default: never credit an unspecified document to a specific program
DEFAULT_LIMITATION = (
    "Scope was not specified; treated as approach-level evidence, not as proof about a specific program."
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass
class Annotation:
    excerpt: str
    locator: str
    scope: Scope
    limitations: list[str]


@dataclass
class ParsedDocument:
    title: str
    source_type: str              # "user_upload" or "synthetic" (contract SourceType)
    text: str                     # canonical full text
    units: list[Unit]
    content_hash: str             # "sha256:<hex>"
    source_id: str
    published_at: date | None = None
    synthetic: bool = False
    identifier: str | None = None  # DOI/PMID/NCT... if known
    annotations: list[Annotation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def unit_by_locator(self, locator: str) -> Unit | None:
        return next((u for u in self.units if u.locator == locator), None)


@dataclass
class ImportResult:
    pack: EvidencePack
    documents: list[ParsedDocument]
    retrieved_at: datetime

    def merge(self, other: "ImportResult") -> "ImportResult":
        return build_pack(self.documents + other.documents, retrieved_at=other.retrieved_at)


# ------------------------------------------------------------------ parsing

def _canon(text: Any, title: str) -> str:
    if not isinstance(text, str):
        raise InvalidDocument(f"{title}: 'text' must be a string.", code="invalid_document")
    canon = normalize_text(text)
    if not canon:
        raise InvalidDocument(f"{title}: document has no text.", code="empty_document")
    if len(canon) > MAX_TEXT_CHARS:
        raise InvalidDocument(f"{title}: text is too long.", code="document_too_large")
    return canon


def _make_doc(title, canon, units, *, published_at, synthetic, identifier, warnings=None) -> ParsedDocument:
    try:
        pub = parse_date(published_at)
    except ValueError as exc:
        raise InvalidDocument(str(exc), code="invalid_date") from exc
    h = content_hash(canon)
    return ParsedDocument(
        title=title,
        source_type="synthetic" if synthetic else "user_upload",
        text=canon,
        units=units,
        content_hash=h,
        source_id=source_id_for(h),
        published_at=pub,
        synthetic=bool(synthetic),
        identifier=identifier or None,
        warnings=warnings or [],
    )


def parse_text(
    title: str,
    text: str,
    *,
    published_at: str | date | None = None,
    synthetic: bool = False,
    identifier: str | None = None,
    annotations: list[dict[str, Any]] | None = None,
) -> ParsedDocument:
    title = (title or "").strip()
    if not title:
        raise InvalidDocument("Document title is required.", code="missing_title")
    canon = _canon(text, title)
    doc = _make_doc(
        title, canon, split_units(canon),
        published_at=published_at, synthetic=synthetic, identifier=identifier,
    )
    doc.annotations = _resolve_annotations(doc, annotations or [])
    return doc


def _resolve_annotations(doc: ParsedDocument, raw: list[dict[str, Any]]) -> list[Annotation]:
    out: list[Annotation] = []
    for i, item in enumerate(raw, start=1):
        excerpt = squash(str(item.get("excerpt", "")))
        if not excerpt:
            raise InvalidDocument(f"{doc.title}: evidence #{i} has an empty excerpt.", code="empty_excerpt")
        locator = item.get("locator")
        if locator:
            unit = doc.unit_by_locator(locator)
            if unit is None:
                raise InvalidDocument(
                    f"{doc.title}: locator {locator!r} (evidence #{i}) does not exist.", code="invalid_locator"
                )
            if not excerpt_in_text(excerpt, unit.text):
                raise InvalidDocument(
                    f"{doc.title}: excerpt of evidence #{i} is not at locator {locator!r}.",
                    code="excerpt_not_found",
                )
        else:
            matches = [u for u in doc.units if excerpt_in_text(excerpt, u.text)]
            if not matches:
                raise InvalidDocument(
                    f"{doc.title}: excerpt of evidence #{i} is not in the document "
                    "(or spans several paragraphs).",
                    code="excerpt_not_found",
                )
            locator = matches[0].locator
        limitations = item.get("limitations") or []
        if isinstance(limitations, str):
            limitations = [limitations]
        limitations = [str(x) for x in limitations]
        raw_scope = item.get("scope")
        if raw_scope:
            try:
                scope = Scope(raw_scope)
            except ValueError as exc:
                raise InvalidDocument(
                    f"{doc.title}: evidence #{i} scope must be 'approach' or 'program'.", code="invalid_scope"
                ) from exc
        else:
            scope = DEFAULT_SCOPE
            limitations.append(DEFAULT_LIMITATION)
        out.append(Annotation(excerpt=excerpt, locator=locator, scope=scope, limitations=limitations))
    return out


def parse_json(data: str | bytes | dict[str, Any], *, default_synthetic: bool = False) -> ParsedDocument:
    """JSON document: {title, text | sections:[{heading,text}], published_at?, synthetic?,
    identifier?, evidence?:[{excerpt, locator?, scope?, limitations?}]}."""
    if isinstance(data, (str, bytes)):
        try:
            data = json.loads(data)
        except (ValueError, UnicodeDecodeError) as exc:
            raise InvalidDocument("Invalid JSON.", code="invalid_json") from exc
    if not isinstance(data, dict):
        raise InvalidDocument("JSON document must be an object.", code="invalid_json")
    secs = data.get("sections")
    if secs is not None:
        if not isinstance(secs, list) or not all(isinstance(s, dict) for s in secs):
            raise InvalidDocument("'sections' must be a list of objects.", code="invalid_json")
        parts = []
        for s in secs:
            if s.get("heading"):
                parts.append(f"# {s['heading']}")
            parts.append(str(s.get("text", "")))
        text = "\n\n".join(parts)
    else:
        text = data.get("text", "")
    return parse_text(
        data.get("title", ""),
        text,
        published_at=data.get("published_at"),
        synthetic=bool(data.get("synthetic", default_synthetic)),
        identifier=data.get("identifier"),
        annotations=data.get("evidence") or [],
    )


def parse_pdf(content: bytes, title: str, *, synthetic: bool = False) -> ParsedDocument:
    title = (title or "").strip()
    if not title:
        raise InvalidDocument("Document title is required.", code="missing_title")
    pages, warnings = extract_pages(content)  # raises UnreadableDocument
    units: list[Unit] = []
    canon_pages: list[str] = []
    for p in pages:
        canon = normalize_text(p.text)
        canon_pages.append(canon)
        units.extend(split_units(canon, page=p.number))
    if not units:
        raise UnreadableDocument("No text could be extracted from the PDF.")
    return _make_doc(
        title, "\n\n".join(canon_pages), units,
        published_at=None, synthetic=synthetic, identifier=None, warnings=warnings,
    )


def parse_document(document: UploadedDocument) -> ParsedDocument:
    name = (document.filename or "").lower()
    ctype = (document.content_type or "").lower()
    content = document.content
    title = (document.title or "").strip() or name.rsplit(".", 1)[0]
    if name.endswith(".pdf") or ctype == "application/pdf" or content.lstrip().startswith(b"%PDF"):
        return parse_pdf(content, title, synthetic=document.synthetic)
    if name.endswith(".json") or ctype == "application/json":
        return parse_json(content, default_synthetic=document.synthetic)
    if name.endswith((".txt", ".md")) or ctype.startswith("text/"):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InvalidDocument("Text file must be UTF-8.", code="invalid_encoding") from exc
        return parse_text(title, text, synthetic=document.synthetic)
    raise UnsupportedDocument("Supported formats: PDF, JSON, plain text (.txt/.md).")


# ------------------------------------------------------------------ pack building

def build_pack(
    documents: list[ParsedDocument],
    *,
    retrieved_at: datetime | None = None,
    snapshot_id: str | None = None,
    retrieval_warnings: list[str] | None = None,
) -> ImportResult:
    """Deduplicate by content hash, assign stable IDs, build contract objects.

    Same hash = same document (kept once + warning). Same title or identifier with
    different content = separate sources (identifier clash gets a warning).
    """
    if not documents:
        raise InvalidDocument("No documents to build an evidence pack from.", code="empty_pack")
    retrieved_at = retrieved_at or datetime.now(timezone.utc).replace(microsecond=0)
    warnings = list(retrieval_warnings or [])
    kept: list[ParsedDocument] = []
    by_hash: dict[str, ParsedDocument] = {}
    by_identifier: dict[str, ParsedDocument] = {}

    for doc in documents:
        for w in doc.warnings:
            msg = f"{doc.title}: {w}"
            if msg not in warnings:
                warnings.append(msg)
        if doc.content_hash in by_hash:
            first = by_hash[doc.content_hash]
            warnings.append(
                f"Duplicate document skipped: '{doc.title}' has identical content to "
                f"'{first.title}' ({first.source_id}); not counted as independent evidence."
            )
            continue
        if doc.identifier and doc.identifier in by_identifier:
            warnings.append(
                f"Identifier {doc.identifier!r} is shared by '{doc.title}' and "
                f"'{by_identifier[doc.identifier].title}' with different content; kept as separate "
                "sources. Check whether one is a revised version."
            )
        by_hash[doc.content_hash] = doc
        if doc.identifier:
            by_identifier.setdefault(doc.identifier, doc)
        kept.append(doc)

    sources: list[Source] = []
    evidence: list[Evidence] = []
    for doc in kept:
        doc_id = doc.identifier if doc.identifier and _ID_RE.match(doc.identifier) and len(doc.identifier) <= 128 else None
        if doc.identifier and doc_id is None:
            warnings.append(
                f"{doc.title}: identifier {doc.identifier!r} cannot be used as document_id "
                "(allowed: letters, digits, '.', '_', '-'); stored without it."
            )
        sources.append(
            Source(
                id=doc.source_id,
                title=doc.title,
                url=None,
                type=doc.source_type,
                published_at=doc.published_at,
                retrieved_at=retrieved_at,
                content_hash=doc.content_hash,
                synthetic=doc.synthetic,
                document_id=doc_id,
            )
        )
        if doc.annotations:
            items = [(a.excerpt, a.locator, a.scope, a.limitations) for a in doc.annotations]
        else:
            items = [(u.text, u.locator, DEFAULT_SCOPE, [DEFAULT_LIMITATION]) for u in doc.units]
        seen: set[tuple[str, str]] = set()
        n = 0
        for excerpt, locator, scope, limitations in items:
            if (locator, excerpt) in seen:
                continue
            seen.add((locator, excerpt))
            n += 1
            evidence.append(
                Evidence(
                    id=evidence_id_for(doc.source_id, n),
                    source_id=doc.source_id,
                    excerpt=excerpt,
                    locator=locator,
                    scope=scope,
                    limitations=limitations,
                )
            )
    if snapshot_id is None:
        digest = hashlib.sha256("|".join(sorted(d.content_hash for d in kept)).encode()).hexdigest()
        snapshot_id = f"snap-{digest[:12]}"
    pack = EvidencePack(
        sources=sources,
        evidence=evidence,
        retrieval_warnings=warnings,
        snapshot_id=snapshot_id,
        synthetic=all(d.synthetic for d in kept),
    )
    return ImportResult(pack=pack, documents=kept, retrieved_at=retrieved_at)


def verify_pack(result: ImportResult) -> list[str]:
    """Self-check. Returns problems (empty list = OK): every evidence has an existing source,
    an existing locator, and its excerpt literally occurs in the document at that locator."""
    problems: list[str] = []
    docs = {d.source_id: d for d in result.documents}
    for ev in result.pack.evidence:
        doc = docs.get(ev.source_id)
        if doc is None:
            problems.append(f"{ev.id}: unknown source_id {ev.source_id}")
            continue
        unit = doc.unit_by_locator(ev.locator)
        if unit is None:
            problems.append(f"{ev.id}: locator {ev.locator!r} not found in {doc.source_id}")
        elif not excerpt_in_text(ev.excerpt, unit.text):
            problems.append(f"{ev.id}: excerpt not found at {ev.locator!r}")
    return problems


# ------------------------------------------------------------------ contract entry points

async def import_document_detailed(
    document: UploadedDocument, ctx: RunContext | None = None, *, retrieved_at: datetime | None = None
) -> ImportResult:
    parsed = await asyncio.to_thread(parse_document, document)
    return build_pack(
        [parsed], retrieved_at=retrieved_at, snapshot_id=getattr(ctx, "snapshot_id", None)
    )


async def import_document(document: UploadedDocument, ctx: RunContext | None = None) -> EvidencePack:
    """Contract signature: import_document(document, ctx) -> EvidencePack."""
    return (await import_document_detailed(document, ctx)).pack