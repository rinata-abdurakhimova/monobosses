import asyncio
from datetime import date

from fastapi import APIRouter, Depends, File, Form, UploadFile

from vic.api.deps import errors, get_repo
from vic.config import get_settings
from vic.contracts import EvidenceCreate, EvidenceCreated, Scope, UploadedDocument
from vic.evidence.errors import DocumentImportError
from vic.evidence.importer import import_document_detailed
from vic.errors import ApiError
from vic.storage import Repository

router = APIRouter(tags=["evidence"])

_CHUNK = 1024 * 1024


@router.post("/cases/{case_id}/evidence", status_code=201, response_model=EvidenceCreated,
             responses=errors(404, 422))
def add_evidence(case_id: str, body: EvidenceCreate,
                 repo: Repository = Depends(get_repo)) -> EvidenceCreated:
    if repo.get_case(case_id) is None:
        raise ApiError(404, "not_found", f"Case '{case_id}' not found")
    return repo.add_evidence(case_id, body)


@router.post("/cases/{case_id}/documents", status_code=201, response_model=EvidenceCreated,
             responses=errors(404, 413, 415, 422))
async def upload_document(case_id: str, file: UploadFile = File(...), title: str = Form(...),
                          synthetic: bool = Form(False),
                          published_at: date | None = Form(None),
                          scope: Scope = Form(Scope.APPROACH),
                          repo: Repository = Depends(get_repo)) -> EvidenceCreated:
    """Parse and persist PDF evidence without automatically starting an analysis."""
    case = repo.get_case(case_id)
    if case is None:
        raise ApiError(404, "not_found", f"Case '{case_id}' not found")
    if scope == Scope.PROGRAM and case.scope != Scope.PROGRAM:
        raise ApiError(422, "incompatible_scope", "Program evidence requires a program assessment")
    name = (file.filename or "").lower()
    if not name.endswith(".pdf") or file.content_type not in ("application/pdf",
                                                              "application/x-pdf"):
        raise ApiError(415, "unsupported_media_type", "Only PDF files are supported")
    limit = get_settings().max_upload_bytes
    data = bytearray()
    while chunk := await file.read(_CHUNK):
        data.extend(chunk)
        if len(data) > limit:
            raise ApiError(413, "payload_too_large", f"File is larger than {limit} bytes")
    if not data.startswith(b"%PDF-"):
        raise ApiError(415, "unsupported_media_type", "File content is not a PDF")
    try:
        result = await import_document_detailed(UploadedDocument(filename=file.filename,
            content_type=file.content_type, content=bytes(data), title=title, synthetic=synthetic))
        if published_at:
            for doc in result.documents:
                doc.published_at = published_at
            result.pack.sources = [source.model_copy(update={"published_at": published_at})
                                   for source in result.pack.sources]
        if scope == Scope.PROGRAM:
            from vic.evidence.importer import DEFAULT_LIMITATION
            result.pack.evidence = [item.model_copy(update={"scope": scope,
                "limitations": [note for note in item.limitations if note != DEFAULT_LIMITATION] +
                    ["User identified this document as program evidence; candidate applicability requires audit."]})
                for item in result.pack.evidence]
        return await asyncio.to_thread(repo.add_import, case_id, result)
    except DocumentImportError as exc:
        raise ApiError(422, exc.code, exc.message) from None
    except ValueError:
        raise ApiError(422, "document_conflict", "Document content conflicts with an existing import") from None
