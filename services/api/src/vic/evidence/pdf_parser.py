from __future__ import annotations

import io
from dataclasses import dataclass

from .errors import UnreadableDocument

MAX_PAGES = 300


@dataclass
class PdfPage:
    number: int  # 1-based, as in a PDF viewer
    text: str


def extract_pages(content: bytes) -> tuple[list[PdfPage], list[str]]:
    """Return (pages with text, warnings). Raises UnreadableDocument if nothing is readable."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    if not content.lstrip().startswith(b"%PDF"):
        raise UnreadableDocument("File is not a valid PDF.")
    pages: list[PdfPage] = []
    warnings: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            try:
                ok = reader.decrypt("")
            except Exception:
                ok = 0
            if not ok:
                raise UnreadableDocument("PDF is password-protected.")
        total = len(reader.pages)
        if total > MAX_PAGES:
            raise UnreadableDocument(f"PDF has {total} pages; limit is {MAX_PAGES}.")
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception:
                warnings.append(f"Page {i}: text extraction failed.")
                continue
            if text:
                pages.append(PdfPage(number=i, text=text))
            else:
                warnings.append(f"Page {i}: no extractable text (possibly a scanned image).")
    except UnreadableDocument:
        raise
    except (PyPdfError, ValueError, KeyError, OSError, RecursionError) as exc:
        raise UnreadableDocument(f"PDF could not be read: {type(exc).__name__}.") from exc

    if not pages:
        raise UnreadableDocument(
            "No text could be extracted from the PDF (likely scanned; OCR is not supported)."
        )
    return pages, warnings