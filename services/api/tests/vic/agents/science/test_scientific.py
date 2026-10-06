import pytest
from unittest.mock import AsyncMock

from vic.contracts import CaseInput, EvidencePack, Evidence, RunContext
from vic.agents.science.scientific import (
    ScientificAnalysis,
    _ClaimOutput,
    _format_evidence,
    _build_payload,
    _to_claims,
    analyze_science,
)

def test_format_evidence_missing_source_and_empty_fields():
    pack = EvidencePack(
        evidence=[Evidence(id="ev-1", source_id="missing-src", excerpt="Text", scope="program")],
        sources=[]
    )
    formatted = _format_evidence(pack)
    assert "[ev-1]" in formatted
    assert "missing-src" not in formatted
    assert "Locator:" not in formatted

def test_build_payload_with_nones():
    case = CaseInput(indication="A", mechanism="B", scope="approach", modality=None)
    pack = EvidencePack(retrieval_warnings=[])
    payload = _build_payload(case, pack)
    assert payload["modality"] == "not specified"
    assert payload["program_data"] == "none provided"
    assert payload["retrieval_warnings"] == "none"

def test_to_claims_unsupported_status_without_evidence():
    pack = EvidencePack()
    analysis = ScientificAnalysis(
        thesis="T", position="weak",
        claims=[
            _ClaimOutput(
                key="science.target_validation", text="Claim",
                support_status="contradicted",
                evidence_ids=["fake-id"],
                assumptions=[], scope="approach", importance="major", reasoning="R"
            )
        ],
        supporting_arguments=[], opposing_arguments=[], risks=[], unknowns=[], change_conditions=[], limitations=[]
    )
    claims = _to_claims(analysis, pack)
    assert claims[0].support_status == "contradicted"
    assert claims[0].evidence_ids == []

@pytest.mark.asyncio
async def test_analyze_science_empty_arrays():
    case = CaseInput(indication="A", mechanism="B", scope="approach")
    pack = EvidencePack()
    
    class MockModel:
        generate_structured = AsyncMock()
    
    ctx = RunContext(model=MockModel())
    empty_analysis = ScientificAnalysis(
        thesis="T", position="insufficient_data", claims=[],
        supporting_arguments=[], opposing_arguments=[], risks=[], unknowns=[], change_conditions=[], limitations=[]
    )
    ctx.model.generate_structured.return_value = empty_analysis
    
    result = await analyze_science(case, pack, ctx)
    assert result.claims == []
    assert result.risks == []
    assert result.section_content.claim_ids == []