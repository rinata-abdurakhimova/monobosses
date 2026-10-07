from fastapi import APIRouter, Depends

from vic.api.deps import errors, get_repo
from vic.contracts import Report
from vic.errors import ApiError
from vic.storage import Repository

router = APIRouter(tags=["reports"])


@router.get("/cases/{case_id}/reports/{version}", response_model=Report,
            responses=errors(404, 422))
def get_report(case_id: str, version: int, repo: Repository = Depends(get_repo)) -> Report:
    if repo.get_case(case_id) is None:
        raise ApiError(404, "not_found", f"Case '{case_id}' not found")
    report = repo.get_report(case_id, version)
    if report is None:
        raise ApiError(404, "not_found", f"Report version {version} not found for case '{case_id}'")
    return report