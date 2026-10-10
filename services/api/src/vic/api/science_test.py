"""Isolated, live Science diagnostic. No retrieval, report, or parallel nodes."""
import asyncio
import hashlib
import time
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from vic.agents.science.scientific import analyze_science
from vic.config import Settings, get_settings
from vic.contracts import (
    CaseInput,
    ErrorBody,
    Evidence,
    EvidencePack,
    RoleResult,
    RunBudget,
    RunContext,
    RunMode,
    Source,
)
from vic.errors import ApiError
from vic.failures import RunFailure, RunTimeout
from vic.llm import build_llm
from vic.storage import new_id
from vic.tracing import scrub

router = APIRouter(tags=["diagnostics"])
_active = False
EXCERPT = "Fictional test: target Y inhibition reduced a disease-X marker in one mouse experiment. No human data or independent replication is available."


class ScienceTestResult(BaseModel):
    test_id: str
    status: Literal["completed", "failed"]
    synthetic: bool = True
    external_retrieval: bool = False
    evidence_excerpt: str
    result: RoleResult | None = None
    error: ErrorBody | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    usage: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/diagnostics/science", response_model=ScienceTestResult, responses={429: {"description": "Test already running"}})
async def science_test(settings: Settings = Depends(get_settings)):
    global _active
    if _active:
        raise ApiError(429, "test_in_progress", "A Science test is already running; try again later.", True)
    _active = True
    test_id = new_id("science-test")
    ctx = RunContext(case_id=test_id, run_id=test_id, snapshot_id="science-test-snapshot",
                     as_of_date=None, mode=RunMode.EVIDENCE_ONLY,
                     budget=RunBudget(max_seconds=120, deadline=time.monotonic()+120,
                                      max_cost_usd=settings.max_run_cost_usd))
    output = ScienceTestResult(test_id=test_id, status="failed", evidence_excerpt=EXCERPT)
    try:
        ctx.model = build_llm(settings)
        case = CaseInput(indication="Synthetic disease X", mechanism="Inhibition of synthetic target Y",
                         scope="approach", modality="Small molecule", development_stage="Preclinical")
        pack = EvidencePack(snapshot_id=ctx.snapshot_id, synthetic=True,
            sources=[Source(id="science-test-source", title="Fictional gateway test evidence", type="company",
                            retrieved_at=datetime.now(UTC), synthetic=True,
                            content_hash="sha256:"+hashlib.sha256(EXCERPT.encode()).hexdigest())],
            evidence=[Evidence(id="science-test-evidence", source_id="science-test-source", excerpt=EXCERPT,
                               locator="Diagnostic fixture", scope="approach",
                               limitations=["Fictional evidence for connection testing only."])])
        output.result = await asyncio.wait_for(analyze_science(case, pack, ctx), timeout=120)
        output.status = "completed"
    except TimeoutError:
        output.error = RunTimeout("The Science test timed out after 120 seconds.").to_error_body()
    except RunFailure as exc:
        output.error = exc.to_error_body()
    finally:
        _active = False
    output.events = ctx.trace.events
    output.usage = ctx.trace.usage
    return ScienceTestResult.model_validate(scrub(output.model_dump(mode="json"),
        secrets=[settings.llm_api_key, settings.api_shared_secret]))
