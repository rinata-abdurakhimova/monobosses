from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

MAX_EXCERPT_CHARS = 1200
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = text.replace("\x00", "")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def squash(text: str) -> str:
    """Collapse all whitespace; used for excerpt comparison and display."""
    return " ".join(text.split())


def content_hash(text: str) -> str:
    """Contract format: 'sha256:<64 hex>' of the normalized text."""
    return "sha256:" + hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def source_id_for(hash_value: str) -> str:
    return f"src-{hash_value.removeprefix('sha256:')[:12]}"


def evidence_id_for(source_id: str, n: int) -> str:
    return f"ev-{source_id.removeprefix('src-')}-{n:03d}"


def excerpt_in_text(excerpt: str, text: str) -> bool:
    e = squash(excerpt)
    return bool(e) and e in squash(text)


def parse_date(value) -> date | None:
    """ISO date (YYYY-MM-DD) or None. Invalid dates are rejected, never guessed."""
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ValueError(f"published_at must be an ISO date (YYYY-MM-DD), got {value!r}")


@dataclass
class Unit:
    """Smallest citeable piece of a document: one paragraph."""

    locator: str
    text: str


def _split_long(text: str, limit: int = MAX_EXCERPT_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for sentence in _SENTENCE_END.split(text):
        if cur and len(cur) + 1 + len(sentence) > limit:
            parts.append(cur)
            cur = sentence
        else:
            cur = f"{cur} {sentence}".strip()
    if cur:
        parts.append(cur)
    return parts


def split_units(text: str, *, page: int | None = None) -> list[Unit]:
    """Split text into paragraphs with locators.

    '# Heading' lines become `section: Heading, paragraph N`; PDFs get a `page P, ` prefix.
    """
    units: list[Unit] = []
    heading: str | None = None
    para_no = 0
    prefix = f"page {page}, " if page is not None else ""
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        while lines and lines[0].lstrip().startswith("#"):
            heading = lines.pop(0).lstrip("# ").strip() or None
            para_no = 0
        body = squash(" ".join(lines))
        if not body:
            continue
        for piece in _split_long(body):
            para_no += 1
            where = f"section: {heading}, paragraph {para_no}" if heading else f"paragraph {para_no}"
            units.append(Unit(locator=prefix + where, text=piece))
    return units