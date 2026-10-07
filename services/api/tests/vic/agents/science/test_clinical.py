from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from vic.agents.science.clinical import ClinicalPlanAnalysis, analyze_clinical
from vic.contracts import (
    CaseInput,
    Claim,
    Evidence,
    EvidencePack,
    Risk,
    RoleResult,
    RunContext,
    SectionContent,
)


def _case() -> CaseInput:
    return CaseInput(
        indication="Severe asthma",
        mechanism="IL-4 receptor inhibition",
        scope="program",
        modality="monoclonal antibody",
        development_stage="phase 1",
        program_data="Candidate-specific PK data are available.",
    )


def _pack() -> EvidencePack:
    return EvidencePack(
        evidence=[
            Evidence(
                id="ev-clinical-1",
                source_id="src-clinical-1",
                excerpt="A validated symptom score improved versus active comparator.",
                scope="program",
                locator="Results",
            )
        ]
    )


def _role_result(role_id: str, summary: str, claim_id: str) -> RoleResult:
    claim = Claim(
        id=claim_id,
        text=f"{summary} claim",
        provenance="ai",
        support_status="mixed",
        evidence_ids=["ev-clinical-1"],
        assumptions=[],
        scope="program",
        importance="critical",
    )
    risk = Risk(
        id=f"{role_id}.risk.data_gap",
        description=f"{summary} data remain incomplete.",
        priority="critical",
        claim_ids=[claim_id],
        impact="The clinical plan may need revision.",
        next_check="Obtain candidate-specific human data.",
    )
    return RoleResult(
        role_id=role_id,
        summary=summary,
        position="moderate",
        claims=[claim],
        risks=[risk],
        unknowns=[f"{summary} unknown"],
        change_conditions=[f"New {summary.lower()} evidence"],
        section_content=SectionContent(
            key=f"{role_id}_section",
            summary=summary,
            claim_ids=[claim_id],
            limitations=[f"{summary} limitation"],
            structured_data={},
        ),
    )


def _scientific_result() -> RoleResult:
    return _role_result(
        role_id="scientific",
        summary="Scientific rationale is moderately supported.",
        claim_id="science.target_validation",
    )


def _translation_result() -> RoleResult:
    return _role_result(
        role_id="translation",
        summary="Human translation remains conditional.",
        claim_id="translation.human_exposure",
    )


def _clinical_analysis(**overrides) -> ClinicalPlanAnalysis:
    values = {
        "thesis": "A biomarker-guided clinical path is feasible with safety monitoring.",
        "position": "conditionally_feasible",
        "target_population": "Adults with severe asthma uncontrolled by standard therapy.",
        "clinically_meaningful_outcome": "Reduced exacerbation frequency.",
        "primary_endpoint": "Annualized severe exacerbation rate.",
        "secondary_endpoints": ["Symptom score", "Rescue medication use"],
        "comparator": "Active standard-of-care comparator.",
        "biomarker_strategy": "Measure target engagement and stratify by baseline biomarker.",
        "trial_size": {
            "has_basis": True,
            "estimate": "120-160 participants",
            "assumptions": ["Effect-size estimate is supported by ev-clinical-1."],
            "statistical_design_gap": None,
            "evidence_ids": ["ev-clinical-1"],
        },
        "study_sequence": [
            {
                "phase": "Phase 1b",
                "objective": "Confirm safety, exposure, and target engagement.",
                "population": "Adults with severe asthma.",
                "primary_endpoint": "Treatment-emergent adverse events.",
                "duration_estimate": "16 weeks",
                "key_assumptions": ["Human exposure reaches the target tissue."],
            },
            {
                "phase": "Phase 2",
                "objective": "Estimate clinical efficacy and dose response.",
                "population": "Biomarker-selected adults with severe asthma.",
                "primary_endpoint": "Annualized severe exacerbation rate.",
                "duration_estimate": "52 weeks",
                "key_assumptions": ["The biomarker enriches for responders."],
            },
        ],
        "regulatory_context": "Precedent is informative but does not guarantee approval.",
        "historical_analogues": [
            {
                "name": "Class analogue",
                "relevance": "Same pathway and indication.",
                "outcome": "Demonstrated clinical activity.",
                "lessons": "Require prospectively defined biomarker analysis.",
                "evidence_ids": ["ev-clinical-1"],
            }
        ],
        "next_milestone": "Demonstrate safe exposure, target engagement, and efficacy signal.",
        "standard_of_care": "High-dose inhaled therapy plus biologic treatment.",
        "unmet_need": "Some patients remain uncontrolled despite available therapy.",
        "claims": [
            {
                "key": "clinical.target_population",
                "text": "The initial target population is adults with uncontrolled severe asthma.",
                "support_status": "supported",
                "evidence_ids": ["ev-clinical-1"],
                "assumptions": [],
                "scope": "program",
                "importance": "critical",
                "reasoning": "The evidence addresses the intended clinical population.",
            },
            {
                "key": "clinical.next_milestone",
                "text": "The next milestone is proof of safe exposure and clinical activity.",
                "support_status": "mixed",
                "evidence_ids": ["ev-clinical-1"],
                "assumptions": ["Target engagement is measurable."],
                "scope": "program",
                "importance": "critical",
                "reasoning": "Translation gaps must be resolved before pivotal development.",
            },
        ],
        "risks": [
            {
                "id": "clinical.risk.safety",
                "description": "Required exposure may not be tolerable.",
                "priority": "critical",
                "related_claim_keys": ["clinical.next_milestone"],
                "impact": "Development could stop before proof of concept.",
                "next_check": "Review dose-escalation safety and PK/PD data.",
            }
        ],
        "unknowns": ["Durability of clinical benefit is unknown."],
        "change_conditions": ["A negative human target-engagement result would change the plan."],
        "diligence_questions": [
            {
                "question": "Is target engagement achieved at tolerated exposure?",
                "why_it_matters": "It tests the central translation assumption.",
                "evidence_needed": "Human PK/PD and safety data.",
                "decision_if_positive": "Proceed to proof-of-concept testing.",
                "decision_if_negative": "Reassess dose, modality, or program viability.",
            }
        ],
        "limitations": ["Long-term safety evidence is unavailable."],
        "science_gaps_carried_forward": ["Safe human exposure is not yet established."],
    }
    values.update(overrides)
    return ClinicalPlanAnalysis(**values)


def _context(analysis: ClinicalPlanAnalysis) -> tuple[RunContext, AsyncMock]:
    generate_structured = AsyncMock(return_value=analysis)
    ctx = RunContext(model=SimpleNamespace(generate_structured=generate_structured))
    return ctx, generate_structured


@pytest.mark.asyncio
async def test_analyze_clinical_happy_path():
    analysis = _clinical_analysis()
    ctx, generate_structured = _context(analysis)

    result = await analyze_clinical(
        _case(),
        _pack(),
        _scientific_result(),
        _translation_result(),
        ctx,
    )

    assert result.role_id == "clinical"
    assert result.summary == analysis.thesis
    assert result.position == "conditionally_feasible"
    assert [claim.id for claim in result.claims] == [
        "clinical.target_population",
        "clinical.next_milestone",
    ]
    assert result.risks[0].id == "clinical.risk.safety"
    assert result.unknowns == ["Durability of clinical benefit is unknown."]
    assert result.section_content.key == "clinical_development_plan"
    assert result.section_content.structured_data["target_population"] == analysis.target_population
    assert result.section_content.structured_data["study_sequence"][1]["phase"] == "Phase 2"
    assert result.section_content.structured_data["next_milestone"] == analysis.next_milestone

    generate_structured.assert_awaited_once()
    prompt_id, payload, response_model, call_ctx = generate_structured.await_args.args
    assert prompt_id == "clinical"
    assert payload["indication"] == "Severe asthma"
    assert response_model is ClinicalPlanAnalysis
    assert call_ctx is ctx


@pytest.mark.asyncio
async def test_trial_size_without_basis_forces_fallback():
    analysis = _clinical_analysis(
        trial_size={
            "has_basis": False,
            "estimate": "240 participants",
            "assumptions": [],
            "statistical_design_gap": None,
            "evidence_ids": [],
        }
    )
    ctx, _ = _context(analysis)

    result = await analyze_clinical(
        _case(),
        _pack(),
        _scientific_result(),
        _translation_result(),
        ctx,
    )

    trial_size = result.section_content.structured_data["trial_size"]
    assert trial_size["has_basis"] is False
    assert trial_size["estimate"] is None
    assert trial_size["statistical_design_gap"] == (
        "Insufficient data to determine trial size; statistical design consultation needed"
    )
    assert analysis.trial_size.estimate is None
    assert analysis.trial_size.statistical_design_gap == trial_size["statistical_design_gap"]


@pytest.mark.asyncio
async def test_prior_results_are_serialized_into_llm_payload():
    analysis = _clinical_analysis()
    ctx, generate_structured = _context(analysis)
    scientific_result = _scientific_result()
    translation_result = _translation_result()

    await analyze_clinical(
        _case(),
        _pack(),
        scientific_result,
        translation_result,
        ctx,
    )

    payload = generate_structured.await_args.args[1]
    prior_analysis = payload["prior_analysis"]
    assert "=== SCIENTIFIC ANALYSIS ===" in prior_analysis
    assert scientific_result.summary in prior_analysis
    assert "[science.target_validation] (mixed, critical)" in prior_analysis
    assert "scientific.risk.data_gap" in prior_analysis
    assert "Scientific rationale is moderately supported. unknown" in prior_analysis
    assert "=== TRANSLATION ANALYSIS ===" in prior_analysis
    assert translation_result.summary in prior_analysis
    assert "[translation.human_exposure] (mixed, critical)" in prior_analysis
    assert "translation.risk.data_gap" in prior_analysis
    assert "Human translation remains conditional. unknown" in prior_analysis


@pytest.mark.asyncio
async def test_claim_evidence_ids_are_filtered_against_evidence_pack():
    analysis = _clinical_analysis(
        claims=[
            {
                "key": "clinical.primary_endpoint",
                "text": "Annualized severe exacerbation rate is the primary endpoint.",
                "support_status": "supported",
                "evidence_ids": ["ev-clinical-1", "ev-invented"],
                "assumptions": [],
                "scope": "program",
                "importance": "critical",
                "reasoning": "The valid evidence supports this endpoint.",
            },
            {
                "key": "clinical.biomarker_strategy",
                "text": "The biomarker is validated for patient selection.",
                "support_status": "supported",
                "evidence_ids": ["ev-invented"],
                "assumptions": [],
                "scope": "program",
                "importance": "major",
                "reasoning": "The cited evidence is not present in the pack.",
            },
        ]
    )
    ctx, _ = _context(analysis)

    result = await analyze_clinical(
        _case(),
        _pack(),
        _scientific_result(),
        _translation_result(),
        ctx,
    )

    endpoint_claim, biomarker_claim = result.claims
    assert endpoint_claim.support_status == "supported"
    assert endpoint_claim.evidence_ids == ["ev-clinical-1"]
    assert biomarker_claim.support_status == "unverified"
    assert biomarker_claim.evidence_ids == []
