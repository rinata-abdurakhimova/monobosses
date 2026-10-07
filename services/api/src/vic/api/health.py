from fastapi import APIRouter, Depends

from vic.api.deps import errors, get_repo
from vic.contracts import HealthStatus
from vic.errors import ApiError
from vic.storage import Repository

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthStatus, responses=errors(503))
def health(repo: Repository = Depends(get_repo)) -> HealthStatus:
    """Readiness: checks that the storage is reachable."""
    try:
        repo.ping()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(503, "storage_unavailable", "Storage is not available", True) from exc
    return HealthStatus(status="ok")