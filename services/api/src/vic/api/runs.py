from fastapi import APIRouter, Depends

from vic.api.deps import errors, get_repo
from vic.contracts import Run
from vic.errors import ApiError
from vic.storage import Repository

router = APIRouter(tags=["runs"])


@router.get("/runs/{run_id}", response_model=Run, responses=errors(404))
def get_run(run_id: str, repo: Repository = Depends(get_repo)) -> Run:
    run = repo.get_run(run_id)
    if run is None:
        raise ApiError(404, "not_found", f"Run '{run_id}' not found")
    return run