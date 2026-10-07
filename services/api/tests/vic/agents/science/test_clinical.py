from unittest.mock import AsyncMock

import pytest

from vic.agents.science import analyze_clinical
from vic.agents.science.clinical import ClinicalPlanAnalysis, _ClaimOutput, _to_claims
from vic.contracts import RunContext
from vic.synthetic import build_all


@pytest.mark.asyncio
async def test_clinical_uses_shared_contracts_and_prior_results():
    built = build_all()
    science, translation = built["report-v1"].roles[:2]
    analysis = ClinicalPlanAnalysis(
        thesis="Synthetic clinical plan",
        position="insufficient_data",
        target_population="Not established",
        clinically_meaningful_outcome="Not established",
        primary_endpoint="Requires clinical validation",
        comparator="Not established",
        biomarker_strategy="Requires evidence",
        trial_size={"has_basis": False, "estimate": "100"},
        study_sequence=[],
        regulatory_context="Requires review",
        next_milestone="Resolve safety",
        standard_of_care="Not established",
        unmet_need="Not established",
        claims=[],
        risks=[],
        unknowns=["Safe human exposure"],
        change_conditions=["Obtain safety evidence"],
        limitations=["Synthetic example"],
        science_gaps_carried_forward=["Safe human exposure"],
    )
    adapter = type("Adapter", (), {})()
    adapter.generate_structured = AsyncMock(return_value=analysis)
    ctx = RunContext(
        case_id="case-test",
        run_id="run-test",
        snapshot_id=built["evidence-pack"].snapshot_id,
        as_of_date=None,
        mode="evidence_only",
        model=adapter,
    )

    result = await analyze_clinical(
        built["case"], built["evidence-pack"], science, translation, ctx
    )

    adapter.generate_structured.assert_awaited_once()
    assert adapter.generate_structured.call_args.args[0] == "clinical"
    assert result.role_id == "clinical"
    assert len(result.section_content) == 1
    section = result.section_content[0]
    assert section.key == "clinical_development_plan"
    assert section.structured_data["trial_size"]["estimate"] is None
    assert section.structured_data["trial_size"]["statistical_design_gap"]
    assert section.structured_data["science_gaps_carried_forward"] == ["Safe human exposure"]


@pytest.mark.parametrize("status", ["supported", "contradicted", "mixed"])
def test_clinical_claim_without_valid_evidence_is_unverified(status):
    from types import SimpleNamespace

    claim = _ClaimOutput(
        key="clinical.safety_requirements",
        text="Synthetic safety claim",
        support_status=status,
        evidence_ids=["ev-missing"],
        assumptions=[],
        scope="program",
        importance="critical",
        reasoning="Synthetic test",
    )
    result = _to_claims(SimpleNamespace(claims=[claim]), build_all()["evidence-pack"])
    assert result[0].support_status == "unverified"
    assert result[0].evidence_ids == []
