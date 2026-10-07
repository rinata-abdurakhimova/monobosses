from unittest.mock import AsyncMock

import pytest

from vic.agents.science.scientific import (
    ScientificAnalysis,
    _build_payload,
    _ClaimOutput,
    _format_evidence,
    _to_claims,
    analyze_science,
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


def test_format_evidence_missing_source_and_empty_fields():
    pack = EvidencePack(
        evidence=[
            Evidence(
                id="ev-1",
                source_id="missing-src",
                excerpt="Text",
                scope="program",
                locator="results",
            )
        ],
        sources=[],
        snapshot_id="snapshot-test",
        synthetic=True,
    )
    formatted = _format_evidence(pack)
    assert "[ev-1]" in formatted
    assert "missing-src" not in formatted
    assert "Locator: results" in formatted


def test_build_payload_with_nones():
    case = CaseInput(indication="A", mechanism="B", scope="approach", modality=None)
    pack = empty_pack()
    payload = _build_payload(case, pack)
    assert payload["modality"] == "not specified"
    assert payload["program_data"] == "none provided"
    assert payload["retrieval_warnings"] == "none"


@pytest.mark.parametrize("status", ["supported", "contradicted", "mixed"])
def test_to_claims_unsupported_status_without_evidence(status):
    pack = empty_pack()
    analysis = ScientificAnalysis(
        thesis="T",
        position="weak",
        claims=[
            _ClaimOutput(
                key="science.target_validation",
                text="Claim",
                support_status=status,
                evidence_ids=["fake-id"],
                assumptions=[],
                scope="approach",
                importance="major",
                reasoning="R",
            )
        ],
        supporting_arguments=[],
        opposing_arguments=[],
        risks=[],
        unknowns=[],
        change_conditions=[],
        limitations=[],
    )
    claims = _to_claims(analysis, pack)
    assert claims[0].support_status == "unverified"
    assert claims[0].evidence_ids == []


@pytest.mark.asyncio
async def test_analyze_science_empty_arrays():
    case = CaseInput(indication="A", mechanism="B", scope="approach")
    pack = empty_pack()

    class MockModel:
        generate_structured = AsyncMock()

    ctx = run_context(MockModel())
    empty_analysis = ScientificAnalysis(
        thesis="T",
        position="insufficient_data",
        claims=[],
        supporting_arguments=[],
        opposing_arguments=[],
        risks=[],
        unknowns=[],
        change_conditions=[],
        limitations=[],
    )
    ctx.model.generate_structured.return_value = empty_analysis

    result = await analyze_science(case, pack, ctx)
    ctx.model.generate_structured.assert_awaited_once()
    assert result.role_id == "science"
    assert result.section_content[0].key == "scientific_thesis"
    assert result.claims == []
    assert result.risks == []
    assert result.section_content[0].claim_ids == []
