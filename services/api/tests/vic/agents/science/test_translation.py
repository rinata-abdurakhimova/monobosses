from unittest.mock import AsyncMock

import pytest

from vic.agents.science.translation import (
    TranslationAnalysis,
    _AdditionalClaim,
    _LinkAssessment,
    _to_claims,
    analyze_translation,
)
from vic.contracts import CaseInput, Evidence, EvidencePack, RunContext


def run_context(model=None):
    return RunContext(
        case_id="case-test",
        run_id="run-test",
        snapshot_id="snapshot-test",
        as_of_date=None,
        mode="evidence_only",
        model=model,
    )


def empty_pack():
    return EvidencePack(sources=[], evidence=[], snapshot_id="snapshot-test", synthetic=True)


def test_translation_link_bizarre_status():
    pack = EvidencePack(
        evidence=[
            Evidence(id="ev-1", source_id="s1", excerpt="E", scope="approach", locator="results")
        ],
        sources=[],
        snapshot_id="snapshot-test",
        synthetic=True,
    )
    analysis = TranslationAnalysis(
        thesis="T",
        position="weak",
        links=[
            _LinkAssessment(
                key="translation.molecular_effect",
                status="hallucinated_status",
                text="Text",
                evidence_ids=["ev-1"],
                evidence_summary="Sum",
                gaps=[],
                limitations=[],
                assumptions=[],
                scope="approach",
                importance="major",
            )
        ],
        additional_claims=[],
        barriers=[],
        risks=[],
        unknowns=[],
        change_conditions=[],
        data_needed=[],
        limitations=[],
    )
    claims = _to_claims(analysis, pack)
    assert claims[0].support_status == "unverified"
    assert claims[0].evidence_ids == ["ev-1"]


@pytest.mark.parametrize("status", ["supported", "contradicted", "mixed"])
def test_additional_claims_without_valid_evidence(status):
    pack = empty_pack()
    analysis = TranslationAnalysis(
        thesis="T",
        position="weak",
        links=[],
        additional_claims=[
            _AdditionalClaim(
                key="translation.safe_exposure",
                text="Bad safety",
                support_status=status,
                evidence_ids=["fake"],
                assumptions=[],
                scope="approach",
                importance="critical",
            )
        ],
        barriers=[],
        risks=[],
        unknowns=[],
        change_conditions=[],
        data_needed=[],
        limitations=[],
    )
    claims = _to_claims(analysis, pack)
    assert claims[0].support_status == "unverified"
    assert claims[0].evidence_ids == []


@pytest.mark.asyncio
async def test_translation_missing_links():
    case = CaseInput(indication="A", mechanism="B", scope="approach")
    pack = empty_pack()

    class MockModel:
        generate_structured = AsyncMock()

    ctx = run_context(MockModel())
    analysis = TranslationAnalysis(
        thesis="T",
        position="weak",
        links=[],
        additional_claims=[],
        barriers=[],
        risks=[],
        unknowns=[],
        change_conditions=[],
        data_needed=[],
        limitations=[],
    )
    ctx.model.generate_structured.return_value = analysis

    result = await analyze_translation(case, pack, ctx)
    ctx.model.generate_structured.assert_awaited_once()
    assert result.role_id == "translation"
    assert result.section_content[0].key == "human_translation_thesis"
    assert result.claims == []
    assert result.section_content[0].structured_data["translation_links"] == {}
