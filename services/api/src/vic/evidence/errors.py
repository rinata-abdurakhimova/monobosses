from __future__ import annotations


class DocumentImportError(Exception):
    """Base error. `code` is stable and safe to show through the API."""

    code = "document_import_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class UnreadableDocument(DocumentImportError):
    """No text could be extracted (scanned PDF, corrupt or protected file)."""

    code = "unreadable_document"


class UnsupportedDocument(DocumentImportError):
    code = "unsupported_document"


class InvalidDocument(DocumentImportError):
    """Empty/malformed text or JSON, or an annotated excerpt that is not in the text."""

    code = "invalid_document"