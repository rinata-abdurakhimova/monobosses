import pytest
from unittest.mock import AsyncMock

from vic.contracts import CaseInput, EvidencePack, Evidence, RunContext
from vic.agents.science.translation import (
    TranslationAnalysis,
    _LinkAssessment,
    _AdditionalClaim,
    _to_claims,
    analyze_translation,
)

def test_translation_link_bizarre_status():
    pack = EvidencePack(evidence=[Evidence(id="ev-1", source_id="s1", excerpt="E", scope="S")])
    analysis = TranslationAnalysis(
        thesis="T", position="weak",
        links=[
            _LinkAssessment(
                key="translation.molecular_effect", 
                status="hallucinated_status", 
                text="Text", evidence_ids=["ev-1"], evidence_summary="Sum",
                gaps=[], limitations=[], assumptions=[], scope="approach", importance="major"
            )
        ],
        additional_claims=[], barriers=[], risks=[], unknowns=[], change_conditions=[], data_needed=[], limitations=[]
    )
    claims = _to_claims(analysis, pack)
    assert claims[0].support_status == "unverified"
    assert claims[0].evidence_ids == ["ev-1"]

def test_additional_claims_mixed_without_evidence():
    pack = EvidencePack()
    analysis = TranslationAnalysis(
        thesis="T", position="weak", links=[],
        additional_claims=[
            _AdditionalClaim(
                key="translation.safe_exposure", text="Bad safety", 
                support_status="contradicted", evidence_ids=["fake"], 
                assumptions=[], scope="approach", importance="critical"
            )
        ],
        barriers=[], risks=[], unknowns=[], change_conditions=[], data_needed=[], limitations=[]
    )
    claims = _to_claims(analysis, pack)
    assert claims[0].support_status == "contradicted" 
    assert claims[0].evidence_ids == []

@pytest.mark.asyncio
async def test_translation_missing_links():
    case = CaseInput(indication="A", mechanism="B", scope="approach")
    pack = EvidencePack()
    
    class MockModel:
        generate_structured = AsyncMock()
        
    ctx = RunContext(model=MockModel())
    analysis = TranslationAnalysis(
        thesis="T", position="weak", links=[], 
        additional_claims=[], barriers=[], risks=[], unknowns=[], change_conditions=[], data_needed=[], limitations=[]
    )
    ctx.model.generate_structured.return_value = analysis
    
    result = await analyze_translation(case, pack, ctx)
    assert result.claims == []
    assert result.section_content.structured_data["translation_links"] == {}