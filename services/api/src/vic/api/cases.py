from fastapi import APIRouter, Depends, Response

from vic.api.deps import errors, get_repo
from vic.api.mock_run import create_mock_run
from vic.contracts import CaseCreated, CaseInput, RunCreate, RunCreated
from vic.errors import ApiError
from vic.storage import Repository

router = APIRouter(tags=["cases"])


@router.post("/cases", status_code=201, response_model=CaseCreated, responses=errors(422))
def create_case(body: CaseInput, repo: Repository = Depends(get_repo)) -> CaseCreated:
    return CaseCreated(case_id=repo.create_case(body))


@router.post("/cases/{case_id}/runs", status_code=202, response_model=RunCreated,
             responses=errors(404, 409, 422))
def create_run(case_id: str, body: RunCreate, response: Response,
               repo: Repository = Depends(get_repo)) -> RunCreated:
    """MOCK in R2-01: returns a run that is already completed with a synthetic report."""
    if repo.get_case(case_id) is None:
        raise ApiError(404, "not_found", f"Case '{case_id}' not found")
    run = create_mock_run(repo, case_id, body)  # MOCK: replaced by background run in R2-02
    response.headers["X-VIC-Mock"] = "true"
    return RunCreated(run_id=run.id)