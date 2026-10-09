"""Exercise the shipped R4 runner with the backend adapter and falsifiable scores."""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[6] / "evals"))

from r4_evaluation_runner_stub import evaluate_family, load_adapter, score
from vic.agents.science.clinical import ClinicalPlanAnalysis
from vic.config import Settings
from vic.contracts import RunContext, RunMode
from vic.llm import ProviderResponse, StructuredLlm

from tests.vic.agents.science.test_clinical import _clinical_analysis
from tests.vic.agents.science.test_paired_behavior import (
    FAMILIES,
    PAIR_A,
    PAIR_C,
    run_pair,
)


@pytest.mark.asyncio
async def test_builtin_adapter_calls_provider_instead_of_recursing():
    settings = Settings(_env_file=None)
    adapter = load_adapter("vic.llm", settings)
    assert isinstance(adapter, StructuredLlm)
    adapter._provider.complete = AsyncMock(return_value=ProviderResponse('{"answer":"ok"}', 10, 5))

    class Answer(BaseModel):
        answer: str

    ctx = RunContext("case", "run", "snapshot", None, RunMode.EVIDENCE_ONLY, model=adapter)
    result = await adapter.generate_structured("science", {}, Answer, ctx)
    assert result.answer == "ok"
    adapter._provider.complete.assert_awaited_once()
    assert ctx.trace.usage[0]["prompt_version"]


@pytest.mark.asyncio
async def test_runner_records_error_without_raw_model_or_provider_text():
    adapter = AsyncMock()
    adapter.generate_structured.side_effect = ValueError("PRIVATE_PROVIDER_OR_EVIDENCE_TEXT")
    result = await evaluate_family(FAMILIES[PAIR_A], adapter, "test")
    assert not result["passed"]
    assert result["failures"] == ["run error: ValueError"]
    assert "PRIVATE_PROVIDER_OR_EVIDENCE_TEXT" not in json.dumps(result)
    assert set(result["versions"]["prompt_hashes"]) == {"science", "translation", "clinical"}


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["scope", "status", "missing"])
async def test_runner_rejects_unexpected_claim_drift(mutation):
    family, before, after, _, _ = await run_pair(PAIR_C)
    # A claim not explicitly listed in the manifest is still subject to zero drift.
    claim = after["science"].claims[0].model_copy(update={"id": "science.extra"})
    before["science"].claims.append(claim.model_copy())
    after["science"].claims.append(claim)
    if mutation == "scope":
        claim.scope = "program"
    elif mutation == "status":
        claim.support_status = "contradicted"
    else:
        after["science"].claims.remove(claim)
    assert score(family["expectations"], tuple(before.values()), tuple(after.values()))


@pytest.mark.parametrize("mutation", ["extra", "status", "key", "duplicate", "trial_basis"])
def test_clinical_schema_rejects_invalid_output(mutation):
    raw = _clinical_analysis().model_dump()
    if mutation == "extra":
        raw["trial_size"]["invented_field"] = True
    elif mutation == "status":
        raw["claims"][0]["support_status"] = "established"
    elif mutation == "key":
        raw["claims"][0]["key"] = "clinical.invented"
    elif mutation == "duplicate":
        raw["claims"].append(raw["claims"][0])
    else:
        raw["trial_size"]["assumptions"] = []
        raw["trial_size"]["evidence_ids"] = []
    with pytest.raises(ValidationError):
        ClinicalPlanAnalysis.model_validate(raw)
