import asyncio

from fastapi import APIRouter, Depends

from vic.api.deps import errors, get_repo
from vic.contracts import Run, RunOutputs
from vic.errors import ApiError
from vic.storage import Repository

router = APIRouter(tags=["runs"])


def _node_analysis(value):
    """Ancestor outputs have their own cards; avoid repeating them recursively."""
    if isinstance(value, dict):
        return {key: _node_analysis(child) for key, child in value.items()
                if key != "upstream_context"}
    if isinstance(value, list):
        return [_node_analysis(child) for child in value]
    return value


@router.get("/runs/{run_id}", response_model=Run, responses=errors(401, 404))
async def get_run(run_id: str, repo: Repository = Depends(get_repo)) -> Run:
    run = await asyncio.to_thread(repo.get_run, run_id)
    if run is None:
        raise ApiError(404, "not_found", f"Run '{run_id}' not found")
    return run


@router.get("/runs/{run_id}/outputs", response_model=RunOutputs, responses=errors(401, 404))
async def get_run_outputs(run_id: str, repo: Repository = Depends(get_repo)) -> RunOutputs:
    run = await asyncio.to_thread(repo.get_run, run_id)
    if run is None:
        raise ApiError(404, "not_found", f"Run '{run_id}' not found")
    nodes = await asyncio.to_thread(repo.get_nodes, run_id)
    if run.status.value == "failed":
        nodes = [node.model_copy(update={"status": "interrupted", "error": run.error})
                 if node.status == "running" else node for node in nodes]
    nodes = [node.model_copy(update={"result": node.result.model_copy(update={
        "section_content": [section.model_copy(update={
            "structured_data": _node_analysis(section.structured_data)})
            for section in node.result.section_content]})}) if node.result is not None else node
        for node in nodes]
    return RunOutputs(run_id=run.id, case_id=run.case_id, status=run.status, nodes=nodes)
