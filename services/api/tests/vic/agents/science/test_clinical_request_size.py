"""Budget regression with full upstream context and contradictory evidence intact."""
import json
from unittest.mock import AsyncMock

import pytest
from vic.agents.science.clinical import (
    ClinicalDesignAnalysis,
    ClinicalDevelopmentAnalysis,
    ClinicalPlanAnalysis,
    _build_payload,
    analyze_clinical,
)
from vic.config import Settings
from vic.contracts import RunContext, RunMode
from vic.llm import ProviderResponse, StructuredLlm, request_sizes, structured_request

from tests.vic.agents.science.test_clinical import (
    _case,
    _clinical_analysis,
    _pack,
    _scientific_result,
    _translation_result,
)


def test_clinical_request_fits_small_context_without_truncating_input():
    pack = _pack()
    pack.evidence[0].excerpt = (
        "Candidate-specific liver toxicity contradicts safe exposure; "
        "another chemotype has no comparable safety data."
    )
    science, translation = _scientific_result(), _translation_result()
    translation.unknowns.append("No demonstrated safe human exposure or patient benefit.")
    payload = _build_payload(_case(), pack, science, translation)
    ctx = RunContext("case", "run", pack.snapshot_id, None, RunMode.EVIDENCE_ONLY)
    _, system, messages = structured_request("clinical", payload, ClinicalPlanAnalysis, ctx)
    sizes = request_sizes(system, messages, model="gpt-6-luna", max_tokens=4096)
    # An application regression bound, not an asserted provider token limit.
    assert sizes["request_bytes"] < 14000
    assert sizes["prompt_bytes"] < 3500
    assert pack.evidence[0].excerpt in payload["evidence_items"]
    assert pack.evidence[0].id in payload["evidence_items"]
    for prior in (science, translation):
        for claim in prior.claims:
            assert claim.id in payload["prior_analysis"]
            assert claim.text in payload["prior_analysis"]
        for risk in prior.risks:
            assert risk.id in payload["prior_analysis"]
            assert risk.description in payload["prior_analysis"]
        for text in prior.unknowns + prior.change_conditions:
            assert text in payload["prior_analysis"]


@pytest.mark.asyncio
async def test_large_request_splits_without_losing_context_or_plan_fields():
    raw = _clinical_analysis().model_dump(mode="json")
    design = {key: value for key, value in raw.items() if key in ClinicalDesignAnalysis.model_fields}
    development = {key: value for key, value in raw.items()
                   if key in ClinicalDevelopmentAnalysis.model_fields}
    design["claims"] = [raw["claims"][0]]
    development["claims"] = [raw["claims"][1]]
    development["risks"] = [{**raw["risks"][0], "priority": "minor",
                              "description": "Long-term pulmonary safety is also unknown."}]
    provider = type("Provider", (), {"name": "test", "complete": AsyncMock(side_effect=[
        ProviderResponse(json.dumps(design), 100, 100),
        ProviderResponse(json.dumps(development), 100, 100),
    ])})()
    adapter = StructuredLlm(provider, Settings(_env_file=None))
    science, translation = _scientific_result(), _translation_result()
    science.summary = "All upstream context must survive. " * 150
    ctx = RunContext("case", "run", "snapshot", None, RunMode.EVIDENCE_ONLY, model=adapter)
    ctx.feedback["clinical"] = [{"reason": "Carry forward the negative safety result."}]
    result = await analyze_clinical(_case(), _pack(), science, translation, ctx)
    assert provider.complete.await_count == 2
    assert [u["prompt_id"] for u in ctx.trace.usage] == ["clinical_design", "clinical_development"]
    for call in provider.complete.await_args_list:
        payload = json.loads(call.kwargs["messages"][0]["content"])
        assert science.summary in payload["prior_analysis"]
        assert translation.unknowns[0] in payload["prior_analysis"]
        assert _pack().evidence[0].excerpt in payload["evidence_items"]
        assert "negative safety result" in call.kwargs["messages"][1]["content"]
    assert {c.id for c in result.claims} == {c["key"] for c in raw["claims"]}
    section = result.section_content[0].structured_data
    for key in ("target_population", "primary_endpoint", "next_milestone", "study_sequence",
                "regulatory_context", "diligence_questions"):
        assert section[key] == raw[key]
    assert result.unknowns == raw["unknowns"]
    assert len(result.risks) == 1
    assert result.risks[0].priority == "critical"
    assert raw["risks"][0]["description"] in result.risks[0].description
    assert "pulmonary safety" in result.risks[0].description
