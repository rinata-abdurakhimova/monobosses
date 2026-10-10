import asyncio

from fastapi import APIRouter, Depends

from vic.api.deps import errors, get_repo
from vic.config import get_settings
from vic.contracts import Run, RunCreated, RunOutputs
from vic.errors import ApiError
from vic.storage import Repository
from vic.config import get_settings
from vic.tracing import scrub

router = APIRouter(tags=["runs"])


@router.get("/runs", response_model=list[Run], responses=errors(401))
async def list_runs(repo: Repository = Depends(get_repo)) -> list[Run]:
    """Latest 200 runs, including unknown costs and synthetic runs."""
    return await asyncio.to_thread(repo.list_runs, 200)


@router.get("/runs/{run_id}/trace", responses=errors(401, 404))
async def get_run_trace(run_id: str, repo: Repository = Depends(get_repo)) -> dict:
    run = await asyncio.to_thread(repo.get_run, run_id)
    if run is None:
        raise ApiError(404, "not_found", f"Run '{run_id}' not found")
    trace = await asyncio.to_thread(repo.get_trace, run_id)
    if trace is None:
        return {"run_id": run_id, "trace_id": run.trace_id, "available": False,
                "usage": [], "events": [], "pricing": {}}
    # Only expose operational trace fields; never return the full stored config.
    keys = {"run_id", "trace_id", "status", "mode", "model", "prompt_versions",
            "config_version", "stage_durations_ms", "usage", "events", "warnings",
            "error", "cost_usd", "cost_note"}
    result = {key: value for key, value in trace.items() if key in keys}
    config = trace.get("config") or {}
    result["pricing"] = {key: config.get(key) for key in (
        "llm_price_input_per_mtok", "llm_price_output_per_mtok", "llm_price_date")}
    result["available"] = True
    settings = get_settings()
    return scrub(result, secrets=[settings.llm_api_key, settings.api_shared_secret])


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
    if get_settings().short_committee:
        nodes = [node for node in nodes if node.role_id.value not in
            {'investment_threshold', 'failure_miner', 'audit'}]
    if run.status.value == "failed":
        nodes = [node.model_copy(update={"status": "interrupted", "error": run.error})
                 if node.status == "running" else node for node in nodes]
    nodes = [node.model_copy(update={"result": node.result.model_copy(update={
        "section_content": [section.model_copy(update={
            "structured_data": _node_analysis(section.structured_data)})
            for section in node.result.section_content]})}) if node.result is not None else node
        for node in nodes]
    return RunOutputs(run_id=run.id, case_id=run.case_id, status=run.status, nodes=nodes)


@router.post("/runs/{run_id}/resume", status_code=202, response_model=RunCreated, responses=errors(401, 404, 409, 429))
async def resume_run(run_id: str):
    from vic.config import get_settings
    from vic.runner import get_manager
    if get_settings().run_backend != 'pipeline':
        raise ApiError(409, 'resume_unavailable', 'Resume requires the pipeline backend')
    run = await get_manager().resume(run_id)
    return RunCreated(run_id=run.id)
