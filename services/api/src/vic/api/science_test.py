"""Isolated real-data Science diagnostic with external retrieval."""
import asyncio
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from vic.agents.science.scientific import analyze_science
from vic.config import Settings, get_settings
from vic.contracts import (
    CaseInput,
    ErrorBody,
    EvidencePack,
    RoleResult,
    RunBudget,
    RunContext,
    RunMode,
)
from vic.errors import ApiError
from vic.evidence.retrieval import build_evidence_pack
from vic.failures import RunFailure, RunTimeout
from vic.llm import build_llm
from vic.storage import new_id
from vic.tracing import scrub

router = APIRouter(tags=["diagnostics"])
_active = False


class ScienceTestResult(BaseModel):
    test_id: str
    status: Literal["completed", "failed"]
    synthetic: bool = False
    external_retrieval: bool = True
    evidence_pack: EvidencePack | None = None
    result: RoleResult | None = None
    error: ErrorBody | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    usage: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/diagnostics/science", response_model=ScienceTestResult, responses={429: {"description": "Test already running"}})
async def science_test(case: CaseInput, settings: Settings = Depends(get_settings)):
    global _active
    if _active:
        raise ApiError(429, "test_in_progress", "A Science test is already running; try again later.", True)
    _active = True
    test_id = new_id("science-test")
    ctx = RunContext(case_id=test_id, run_id=test_id, snapshot_id="science-test-snapshot",
                     as_of_date=case.as_of_date, mode=RunMode.LIVE,
                     budget=RunBudget(max_seconds=240, deadline=time.monotonic()+240,
                                      max_cost_usd=settings.max_run_cost_usd))
    output = ScienceTestResult(test_id=test_id, status="failed")
    try:
        ctx.model = build_llm(settings)
        pack = await build_evidence_pack(case, ctx)
        output.evidence_pack = pack
        if not pack.evidence:
            raise RunFailure("No real evidence was retrieved. Check the source warnings; no fictional evidence was substituted.", code="no_real_evidence")
        output.result = await asyncio.wait_for(analyze_science(case, pack, ctx), timeout=ctx.budget.remaining_seconds())
        output.status = "completed"
    except TimeoutError:
        output.error = RunTimeout("The real-data Science test timed out after 240 seconds.").to_error_body()
    except RunFailure as exc:
        output.error = exc.to_error_body()
    finally:
        _active = False
    output.events = ctx.trace.events
    output.usage = ctx.trace.usage
    return ScienceTestResult.model_validate(scrub(output.model_dump(mode="json"),
        secrets=[settings.llm_api_key, settings.api_shared_secret]))
