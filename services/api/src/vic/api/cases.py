import asyncio

from fastapi import APIRouter, Depends, Response

from vic.api.deps import errors, get_repo
from vic.api.mock_run import create_mock_run
from vic.config import get_settings
from vic.contracts import CaseCreated, CaseInput, RunCreate, RunCreated
from vic.errors import ApiError
from vic.runner import get_manager
from vic.storage import Repository

router = APIRouter(tags=["cases"])


@router.post("/cases", status_code=201, response_model=CaseCreated, responses=errors(401, 422))
async def create_case(body: CaseInput, repo: Repository = Depends(get_repo)) -> CaseCreated:
    return CaseCreated(case_id=await asyncio.to_thread(repo.create_case, body))


@router.post("/cases/{case_id}/runs", status_code=202, response_model=RunCreated,
             responses=errors(401, 404, 409, 422, 429))
async def create_run(case_id: str, body: RunCreate, response: Response,
                     repo: Repository = Depends(get_repo)) -> RunCreated:
    """Returns 202 at once; the pipeline runs in the background. Poll GET /runs/{run_id}."""
    if await asyncio.to_thread(repo.get_case, case_id) is None:
        raise ApiError(404, "not_found", f"Case '{case_id}' not found")
    if get_settings().run_backend == "mock":  # MOCK: only for UI development, see README
        run = await asyncio.to_thread(create_mock_run, repo, case_id, body)
        response.headers["X-VIC-Mock"] = "true"
        return RunCreated(run_id=run.id)
    if body.parent_report_id:
        parent = await asyncio.to_thread(repo.get_report_by_id, body.parent_report_id)
        if parent is None:
            raise ApiError(404, "not_found", f"Report '{body.parent_report_id}' not found")
        if parent.case_id != case_id:
            raise ApiError(409, "incompatible_parent_report",
                           "parent_report_id belongs to a different case")
    elif await asyncio.to_thread(repo.get_latest_report, case_id) is not None:
        raise ApiError(409, "parent_report_required",
                       "This case already has a report; pass parent_report_id to create a new version")
    run = await get_manager().start(case_id, body)
    return RunCreated(run_id=run.id)