from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from vic.agents.science.translation import (
    EXTRA_CLAIM_KEYS,
    TRANSLATION_LINKS,
    TranslationAnalysis,
    _AdditionalClaim,
    _is_animal_only_evidence,
    _LinkAssessment,
    _RiskOutput,
    _to_claims,
    analyze_translation,
)
from vic.contracts import CaseInput, Evidence, EvidencePack, Source

# CaseInput requires >= 40 characters of program_data when scope="program".
SYNTHETIC_PROGRAM_DATA = (
    "Synthetic program data used only for translation agent regression tests."
)


def _case(scope="approach"):
    if scope == "program":
        return CaseInput(
            indication="A",
            mechanism="B",
            scope=scope,
            program_data=SYNTHETIC_PROGRAM_DATA,
        )
    return CaseInput(indication="A", mechanism="B", scope=scope)

ANIMAL_BENEFIT_TEXT = (
    "Human patient benefit is unknown; animal efficacy is not evidence of clinical benefit."
)


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


def test_risk_cannot_reference_absent_optional_translation_claim():
    risk = _RiskOutput(id="risk.exposure", description="Tissue exposure is unknown.",
        priority="critical", related_claim_keys=["translation.tissue_penetration"],
        impact="Safe exposure cannot be assessed.", next_check="Obtain exposure evidence.")
    with pytest.raises(ValidationError, match="absent optional claim"):
        _analysis(risks=[risk])
    _analysis(risks=[risk], additional_claims=[_additional_claim(key="translation.tissue_penetration")])


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


def _empty_pack():
    return EvidencePack(
        sources=[],
        evidence=[],
        snapshot_id="snapshot-test",
        synthetic=True,
    )


def _pack_with_excerpt(excerpt, evidence_id="ev-test", scope="approach"):
    return EvidencePack(
        sources=[
            Source(
                id="src-test",
                title="Synthetic excerpt",
                type="peer_reviewed",
                retrieved_at="2026-01-01T00:00:00Z",
                content_hash="sha256:" + "0" * 64,
                synthetic=True,
            )
        ],
        evidence=[
            Evidence(
                id=evidence_id,
                source_id="src-test",
                excerpt=excerpt,
                scope=scope,
                locator="Results",
            )
        ],
        snapshot_id="snapshot-test",
        synthetic=True,
    )


def _patient_benefit_analysis(evidence_id):
    return _analysis(
        links=_links(
            **{
                "translation.patient_benefit": {
                    "status": "established",
                    "text": "The treatment benefits patients.",
                    "evidence_ids": [evidence_id],
                    "evidence_summary": "Treatment improved outcomes.",
                    "gaps": [],
                    "importance": "critical",
                }
            }
        )
    )


async def _run(analysis, pack, scope="approach"):
    ctx = SimpleNamespace(model=AsyncMock())
    ctx.model.generate_structured.return_value = analysis
    return await analyze_translation(_case(scope), pack, ctx)


def _claim(result, claim_id):
    return next(claim for claim in result.claims if claim.id == claim_id)


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
        for claim in _to_claims(analysis, _empty_pack())
        if claim.id == "translation.biomarker_gap"
    )

    assert claim.support_status == "unverified"
    assert claim.evidence_ids == []
    assert claim.text.startswith("This conclusion is unverified.")


def test_contradictory_additional_claim_retains_valid_evidence():
    pack = EvidencePack(
        sources=[
            Source(
                id="src-1",
                title="Negative result",
                type="peer_reviewed",
                retrieved_at="2026-01-01T00:00:00Z",
                content_hash="sha256:" + "0" * 64,
                synthetic=True,
            )
        ],
        evidence=[
            Evidence(
                id="ev-negative",
                source_id="src-1",
                excerpt="The prespecified biomarker response was not observed in participants.",
                scope="program",
                locator="Results",
            )
        ],
        snapshot_id="snapshot-test",
        synthetic=True,
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
        sources=[
            Source(
                id="src-animal",
                title="Mouse study",
                type="peer_reviewed",
                retrieved_at="2026-01-01T00:00:00Z",
                content_hash="sha256:" + "0" * 64,
                synthetic=True,
            )
        ],
        evidence=[
            Evidence(
                id="ev-mouse",
                source_id="src-animal",
                excerpt="Treatment improved disease scores in mice in a preclinical model.",
                scope="approach",
                locator="Results",
            )
        ],
        snapshot_id="snapshot-test",
        synthetic=True,
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
    assert claim.text == ANIMAL_BENEFIT_TEXT
    assert "animal or preclinical efficacy" in result.unknowns[0]
    assert result.section_content[0].structured_data["translation_links"][
        "translation.patient_benefit"
    ]["status"] == "gap"


@pytest.mark.asyncio
async def test_negated_human_markers_do_not_mask_animal_only_evidence():
    pack = _pack_with_excerpt(
        "No patients were enrolled and no clinical trial has been conducted; "
        "treatment improved disease scores in mice.",
        evidence_id="ev-negated-human",
    )

    result = await _run(_patient_benefit_analysis("ev-negated-human"), pack)
    claim = _claim(result, "translation.patient_benefit")

    assert claim.support_status == "unknown"
    assert claim.evidence_ids == ["ev-negated-human"]
    assert claim.text == ANIMAL_BENEFIT_TEXT
    assert any("animal or preclinical efficacy" in item for item in result.unknowns)
    assert result.section_content[0].structured_data["translation_links"][
        "translation.patient_benefit"
    ]["status"] == "gap"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "excerpt",
    [
        "Лікування покращило показники захворювання у мишах у доклінічній моделі.",
        "Дослідження на тваринах показало зменшення ураження у щурів.",
        "Ефективність підтверджена лише на тваринах; пацієнтів не залучали.",
    ],
)
async def test_ukrainian_animal_excerpt_is_downgraded_to_unknown(excerpt):
    pack = _pack_with_excerpt(excerpt, evidence_id="ev-ua-animal")

    result = await _run(_patient_benefit_analysis("ev-ua-animal"), pack)
    claim = _claim(result, "translation.patient_benefit")

    assert claim.support_status == "unknown"
    assert claim.evidence_ids == ["ev-ua-animal"]
    assert claim.text == ANIMAL_BENEFIT_TEXT
    assert result.section_content[0].structured_data["translation_links"][
        "translation.patient_benefit"
    ]["status"] == "gap"


@pytest.mark.asyncio
async def test_affirmed_human_evidence_is_not_downgraded_alongside_animal_data():
    pack = _pack_with_excerpt(
        "Disease scores improved in mice, and in a randomized placebo-controlled "
        "trial patients reported better quality of life.",
        evidence_id="ev-human",
    )

    result = await _run(_patient_benefit_analysis("ev-human"), pack)
    claim = _claim(result, "translation.patient_benefit")

    assert claim.support_status == "supported"
    assert claim.text == "The treatment benefits patients."
    assert result.section_content[0].structured_data["translation_links"][
        "translation.patient_benefit"
    ]["status"] == "established"


@pytest.mark.parametrize(
    ("excerpt", "expected"),
    [
        (
            ("No patients were enrolled and no clinical trial has been conducted; "
             "treatment improved disease scores in mice."),
            True,
        ),
        ("Efficacy was observed in mice; there is a lack of clinical data in patients.", True),
        ("Mice improved; patients were not enrolled.", True),
        ("Ефект спостерігали у мишах; пацієнтів не залучали, клінічних досліджень не проводилось.", True),
        ("Немає клінічних випробувань; ефект підтверджено у щурів.", True),
        ("Treatment improved disease scores in mice and in patients in a phase 2 trial.", False),
        ("Mice improved, but patients in the clinical trial had no benefit.", False),
        ("Ефект у мишах; клінічне випробування проведено на пацієнтах.", False),
        ("Доклінічні дані та дані клінічного випробування на пацієнтах збігаються.", False),
        ("Treatment was well tolerated.", False),
    ],
)
def test_animal_only_detector_handles_negation_and_ukrainian(excerpt, expected):
    pack = _pack_with_excerpt(excerpt, evidence_id="ev-detector")

    assert _is_animal_only_evidence("ev-detector", pack) is expected


def test_animal_only_detector_returns_false_for_unknown_evidence_id():
    assert _is_animal_only_evidence("missing", _empty_pack()) is False


@pytest.mark.asyncio
async def test_missing_safe_human_exposure_is_explicitly_unknown():
    result = await _run(_analysis(), _empty_pack())
    safe_exposure = _claim(result, "translation.safe_exposure")

    assert safe_exposure.support_status == "unknown"
    assert safe_exposure.evidence_ids == []
    assert safe_exposure.scope == "approach"
    assert "human safety data are missing" in safe_exposure.text
    assert any("does not establish safety" in unknown for unknown in result.unknowns)


@pytest.mark.asyncio
@pytest.mark.parametrize("case_scope", ["approach", "program"])
async def test_missing_safe_exposure_claim_inherits_case_scope(case_scope):
    result = await _run(_analysis(), _empty_pack(), scope=case_scope)
    safe_exposure = _claim(result, "translation.safe_exposure")

    assert safe_exposure.scope == case_scope
    assert safe_exposure.support_status == "unknown"
    assert safe_exposure.importance == "critical"


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

    result = await _run(analysis, _empty_pack())
    exposure = _claim(result, "translation.human_exposure")
    summary = result.section_content[0].structured_data["translation_links"][
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

    with pytest.raises(ValidationError, match="all five distinct keys"):
        await _run(invalid_analysis, _empty_pack())


def test_declared_claim_key_lists_remain_distinct():
    assert len(TRANSLATION_LINKS) == 5
    assert len(set(TRANSLATION_LINKS)) == 5
    assert set(TRANSLATION_LINKS).isdisjoint(EXTRA_CLAIM_KEYS)
