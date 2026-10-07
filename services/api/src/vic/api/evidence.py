from fastapi import APIRouter, Depends, File, Form, UploadFile

from vic.api.deps import errors, get_repo
from vic.config import get_settings
from vic.contracts import EvidenceCreate, EvidenceCreated
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
             responses=errors(404, 413, 415, 422, 501))
async def upload_document(case_id: str, file: UploadFile = File(...), title: str = Form(...),
                          synthetic: bool = Form(False),
                          repo: Repository = Depends(get_repo)) -> EvidenceCreated:
    """Validates the upload (type, size). PDF extraction (R3) is not connected yet -> 501."""
    if repo.get_case(case_id) is None:
        raise ApiError(404, "not_found", f"Case '{case_id}' not found")
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
    # MOCK: R3's PDF parser is connected in R2-03.
    raise ApiError(501, "not_implemented", "PDF extraction is not connected yet (R2-03 / R3)")