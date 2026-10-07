from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from vic.agents.science.translation import (
    EXTRA_CLAIM_KEYS,
    TRANSLATION_LINKS,
    TranslationAnalysis,
    _AdditionalClaim,
    _LinkAssessment,
    _RiskOutput,
    _to_claims,
    analyze_translation,
)
from vic.contracts import CaseInput, Evidence, EvidencePack, Source


def _link(key, **overrides):
    values = {
        "key": key,
        "status": "gap",
        "text": f"{key} is unknown.",
        "evidence_ids": [],
        "evidence_summary": "No evidence was provided.",
        "gaps": [f"Evidence is missing for {key}."],
        "limitations": [],
        "assumptions": [],
        "scope": "approach",
        "importance": "major",
    }
    values.update(overrides)
    return _LinkAssessment(**values)


def _links(**per_key_overrides):
    return [
        _link(key, **per_key_overrides.get(key, {}))
        for key in TRANSLATION_LINKS
    ]


def _analysis(**overrides):
    values = {
        "thesis": "Human translation remains uncertain.",
        "position": "insufficient_data",
        "links": _links(),
        "additional_claims": [],
        "barriers": [],
        "risks": [],
        "unknowns": [],
        "change_conditions": [],
        "data_needed": [],
        "limitations": [],
    }
    values.update(overrides)
    return TranslationAnalysis(**values)


def _additional_claim(**overrides):
    values = {
        "key": "translation.safe_exposure",
        "text": "Safe exposure is unknown.",
        "support_status": "unknown",
        "evidence_ids": [],
        "assumptions": [],
        "scope": "program",
        "importance": "critical",
    }
    values.update(overrides)
    return _AdditionalClaim(**values)


def test_translation_analysis_requires_all_five_links():
    with pytest.raises(ValidationError, match="all five distinct keys"):
        _analysis(links=[])


def test_translation_analysis_requires_expected_link_order():
    links = _links()
    links[0], links[1] = links[1], links[0]

    with pytest.raises(ValidationError, match="expected order"):
        _analysis(links=links)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("key", "translation.invalid"),
        ("status", "hallucinated_status"),
        ("scope", "global"),
        ("importance", "urgent"),
    ],
)
def test_link_schema_rejects_invalid_enums(field, value):
    with pytest.raises(ValidationError):
        if field == "key":
            _link(value)
        else:
            _link("translation.molecular_effect", **{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("key", "translation.invalid"),
        ("support_status", "probable"),
        ("scope", "global"),
        ("importance", "urgent"),
    ],
)
def test_additional_claim_schema_rejects_invalid_enums(field, value):
    with pytest.raises(ValidationError):
        _additional_claim(**{field: value})


def test_risk_schema_rejects_invalid_priority():
    with pytest.raises(ValidationError):
        _RiskOutput(
            id="translation.risk.test",
            description="Risk",
            priority="urgent",
            related_claim_keys=["translation.patient_benefit"],
            impact="Impact",
            next_check="Check",
        )


def test_contradictory_additional_claim_without_valid_evidence_is_downgraded():
    analysis = _analysis(
        additional_claims=[
            _additional_claim(
                key="translation.biomarker_gap",
                text="The biomarker disproves translation.",
                support_status="contradicted",
                evidence_ids=["invented-id"],
            )
        ]
    )

    claim = next(
        claim
        for claim in _to_claims(analysis, EvidencePack())
        if claim.id == "translation.biomarker_gap"
    )

    assert claim.support_status == "unverified"
    assert claim.evidence_ids == []
    assert claim.text.startswith("This conclusion is unverified.")


def test_contradictory_additional_claim_retains_valid_evidence():
    pack = EvidencePack(
        sources=[Source(id="src-1", title="Negative result", type="publication")],
        evidence=[
            Evidence(
                id="ev-negative",
                source_id="src-1",
                excerpt="The prespecified biomarker response was not observed in participants.",
                scope="program",
            )
        ],
    )
    analysis = _analysis(
        additional_claims=[
            _additional_claim(
                key="translation.biomarker_gap",
                text="The proposed biomarker was not responsive.",
                support_status="contradicted",
                evidence_ids=["ev-negative", "invented-id"],
            )
        ]
    )

    claim = next(
        claim
        for claim in _to_claims(analysis, pack)
        if claim.id == "translation.biomarker_gap"
    )

    assert claim.support_status == "contradicted"
    assert claim.evidence_ids == ["ev-negative"]


@pytest.mark.asyncio
async def test_animal_efficacy_is_not_presented_as_human_benefit():
    pack = EvidencePack(
        sources=[Source(id="src-animal", title="Mouse study", type="publication")],
        evidence=[
            Evidence(
                id="ev-mouse",
                source_id="src-animal",
                excerpt="Treatment improved disease scores in mice in a preclinical model.",
                scope="approach",
            )
        ],
    )
    analysis = _analysis(
        links=_links(
            **{
                "translation.patient_benefit": {
                    "status": "established",
                    "text": "The treatment benefits patients.",
                    "evidence_ids": ["ev-mouse"],
                    "evidence_summary": "Mice improved after treatment.",
                    "gaps": [],
                    "importance": "critical",
                }
            }
        )
    )
    ctx = SimpleNamespace(model=AsyncMock())
    ctx.model.generate_structured.return_value = analysis

    result = await analyze_translation(
        CaseInput(indication="A", mechanism="B", scope="approach"), pack, ctx
    )
    claim = next(
        claim for claim in result.claims if claim.id == "translation.patient_benefit"
    )

    assert claim.support_status == "unknown"
    assert claim.evidence_ids == ["ev-mouse"]
    assert claim.text == (
        "Human patient benefit is unknown; animal efficacy is not evidence of clinical benefit."
    )
    assert "animal or preclinical efficacy" in result.unknowns[0]
    assert result.section_content.structured_data["translation_links"][
        "translation.patient_benefit"
    ]["status"] == "gap"


@pytest.mark.asyncio
async def test_missing_safe_human_exposure_is_explicitly_unknown():
    analysis = _analysis()
    ctx = SimpleNamespace(model=AsyncMock())
    ctx.model.generate_structured.return_value = analysis

    result = await analyze_translation(
        CaseInput(indication="A", mechanism="B", scope="approach"),
        EvidencePack(),
        ctx,
    )
    safe_exposure = next(
        claim for claim in result.claims if claim.id == "translation.safe_exposure"
    )

    assert safe_exposure.support_status == "unknown"
    assert safe_exposure.evidence_ids == []
    assert "human safety data are missing" in safe_exposure.text
    assert any("does not establish safety" in unknown for unknown in result.unknowns)


@pytest.mark.asyncio
async def test_supported_link_without_valid_evidence_becomes_explicit_gap():
    analysis = _analysis(
        links=_links(
            **{
                "translation.human_exposure": {
                    "status": "established",
                    "text": "Human exposure is sufficient.",
                    "evidence_ids": ["invented-id"],
                    "gaps": [],
                }
            }
        )
    )
    ctx = SimpleNamespace(model=AsyncMock())
    ctx.model.generate_structured.return_value = analysis

    result = await analyze_translation(
        CaseInput(indication="A", mechanism="B", scope="approach"),
        EvidencePack(),
        ctx,
    )
    exposure = next(
        claim for claim in result.claims if claim.id == "translation.human_exposure"
    )
    summary = result.section_content.structured_data["translation_links"][
        "translation.human_exposure"
    ]

    assert exposure.support_status == "unknown"
    assert exposure.evidence_ids == []
    assert summary["status"] == "gap"
    assert "no valid evidence references remain" in summary["gaps"][0]


@pytest.mark.asyncio
async def test_analyze_translation_revalidates_incomplete_model_construct_output():
    invalid_analysis = TranslationAnalysis.model_construct(
        thesis="Invalid response",
        position="strong",
        links=[],
        additional_claims=[],
        barriers=[],
        risks=[],
        unknowns=[],
        change_conditions=[],
        data_needed=[],
        limitations=[],
    )
    ctx = SimpleNamespace(model=AsyncMock())
    ctx.model.generate_structured.return_value = invalid_analysis

    with pytest.raises(ValidationError, match="all five distinct keys"):
        await analyze_translation(
            CaseInput(indication="A", mechanism="B", scope="approach"),
            EvidencePack(),
            ctx,
        )


def test_declared_claim_key_lists_remain_distinct():
    assert len(TRANSLATION_LINKS) == 5
    assert len(set(TRANSLATION_LINKS)) == 5
    assert set(TRANSLATION_LINKS).isdisjoint(EXTRA_CLAIM_KEYS)
