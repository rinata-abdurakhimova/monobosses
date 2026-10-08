from __future__ import annotations

from pydantic import BaseModel, Field

from vic.contracts import (
    CaseInput,
    Claim,
    EvidencePack,
    Risk,
    RoleResult,
    RunContext,
    SectionContent,
)

PROMPT_ID = "clinical"
PROMPT_VERSION = "1.0.0"

CLAIM_KEYS = [
    "clinical.target_population",
    "clinical.primary_endpoint",
    "clinical.secondary_endpoints",
    "clinical.comparator_choice",
    "clinical.biomarker_strategy",
    "clinical.trial_size_basis",
    "clinical.study_sequence",
    "clinical.regulatory_precedent",
    "clinical.next_milestone",
    "clinical.standard_of_care",
    "clinical.unmet_need",
    "clinical.safety_requirements",
]


class _TrialSizeEstimate(BaseModel):
    has_basis: bool = Field(
        description="True only if there is a quantitative or evidence-based rationale for estimating trial size"
    )
    estimate: str | None = Field(
        default=None,
        description="Approximate trial size range with units; null if has_basis is False",
    )
    assumptions: list[str] = Field(default_factory=list)
    statistical_design_gap: str | None = Field(
        default=None,
        description="If has_basis is False, describe what data or analysis is needed to determine trial size",
    )
    evidence_ids: list[str] = Field(default_factory=list)


class _StudyPhase(BaseModel):
    phase: str = Field(description="e.g. 'Phase 1', 'Phase 1b/2', 'Phase 2', 'Phase 3'")
    objective: str
    population: str
    primary_endpoint: str
    duration_estimate: str | None = None
    key_assumptions: list[str] = Field(default_factory=list)


class _HistoricalAnalogue(BaseModel):
    name: str
    relevance: str
    outcome: str
    lessons: str
    evidence_ids: list[str] = Field(default_factory=list)


class _ClaimOutput(BaseModel):
    key: str = Field(description="Stable claim key from the predefined clinical set")
    text: str
    support_status: str = Field(
        description="One of: supported, contradicted, mixed, unverified, unknown"
    )
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    scope: str
    importance: str = Field(description="One of: critical, major, minor")
    reasoning: str


class _RiskOutput(BaseModel):
    id: str = Field(description="Stable risk identifier, e.g. 'clinical.risk.endpoint_miss'")
    description: str
    priority: str = Field(description="One of: critical, major, minor")
    related_claim_keys: list[str] = Field(default_factory=list)
    impact: str
    next_check: str


class _DiligenceQuestionOutput(BaseModel):
    question: str
    why_it_matters: str
    evidence_needed: str
    decision_if_positive: str
    decision_if_negative: str


class ClinicalPlanAnalysis(BaseModel):
    thesis: str = Field(description="One-paragraph clinical development thesis")
    position: str = Field(
        description="Feasibility: feasible, conditionally_feasible, challenging, or insufficient_data"
    )
    target_population: str
    clinically_meaningful_outcome: str
    primary_endpoint: str
    secondary_endpoints: list[str] = Field(default_factory=list)
    comparator: str
    biomarker_strategy: str
    trial_size: _TrialSizeEstimate
    study_sequence: list[_StudyPhase]
    regulatory_context: str = Field(
        description="Relevant precedents and regulatory considerations; mark as context, not guarantee"
    )
    historical_analogues: list[_HistoricalAnalogue] = Field(default_factory=list)
    next_milestone: str = Field(
        description="The next value-creating milestone and evidence needed to reach it"
    )
    standard_of_care: str
    unmet_need: str
    claims: list[_ClaimOutput]
    risks: list[_RiskOutput]
    unknowns: list[str]
    change_conditions: list[str]
    diligence_questions: list[_DiligenceQuestionOutput] = Field(default_factory=list)
    limitations: list[str]
    science_gaps_carried_forward: list[str] = Field(
        description="Unresolved gaps from scientific/translation analysis that affect the clinical plan"
    )


def _format_evidence(pack: EvidencePack) -> str:
    source_map = {s.id: s for s in pack.sources}
    blocks: list[str] = []
    for ev in pack.evidence:
        src = source_map.get(ev.source_id)
        lines = [f"[{ev.id}]"]
        if src:
            meta = f"  Source: {src.title} | type={src.type}"
            if src.published_at:
                meta += f" | published={src.published_at}"
            if src.synthetic:
                meta += " | SYNTHETIC"
            lines.append(meta)
        lines.append(f"  Excerpt: {ev.excerpt}")
        if ev.locator:
            lines.append(f"  Locator: {ev.locator}")
        lines.append(f"  Scope: {ev.scope}")
        if ev.limitations:
            lines.append(f"  Limitations: {ev.limitations}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "(no evidence provided)"


def _val(x) -> str:
    return str(getattr(x, "value", x))

def _format_prior_results(
    scientific_result: RoleResult,
    translation_result: RoleResult,
) -> str:
    sections: list[str] = []

    sections.append("=== SCIENTIFIC ANALYSIS ===")
    sections.append(f"Position: {scientific_result.position}")
    sections.append(f"Thesis: {scientific_result.summary}")
    if scientific_result.claims:
        sections.append("Claims:")
        for c in scientific_result.claims:
            sections.append(
                f"  [{c.id}] ({_val(c.support_status)}, {_val(c.importance)}) {c.text}"
            )
    if scientific_result.risks:
        sections.append("Risks:")
        for r in scientific_result.risks:
            sections.append(f"  [{r.id}] ({r.priority}) {r.description}")
    if scientific_result.unknowns:
        sections.append("Unknowns: " + "; ".join(scientific_result.unknowns))
    if scientific_result.change_conditions:
        sections.append(
            "Change conditions: " + "; ".join(scientific_result.change_conditions)
        )

    sections.append("")
    sections.append("=== TRANSLATION ANALYSIS ===")
    sections.append(f"Position: {translation_result.position}")
    sections.append(f"Thesis: {translation_result.summary}")
    if translation_result.claims:
        sections.append("Claims:")
        for c in translation_result.claims:
            sections.append(
                f"  [{c.id}] ({_val(c.support_status)}, {_val(c.importance)}) {c.text}"
            )
    if translation_result.risks:
        sections.append("Risks:")
        for r in translation_result.risks:
            sections.append(f"  [{r.id}] ({r.priority}) {r.description}")
    if translation_result.unknowns:
        sections.append("Unknowns: " + "; ".join(translation_result.unknowns))
    if translation_result.change_conditions:
        sections.append(
            "Change conditions: " + "; ".join(translation_result.change_conditions)
        )

    return "\n".join(sections)


def _build_payload(
    case: CaseInput,
    pack: EvidencePack,
    scientific_result: RoleResult,
    translation_result: RoleResult,
) -> dict:
    return {
        "indication": case.indication,
        "mechanism": case.mechanism,
        "modality": case.modality or "not specified",
        "development_stage": case.development_stage or "not specified",
        "scope": case.scope,
        "program_data": case.program_data or "none provided",
        "evidence_items": _format_evidence(pack),
        "evidence_count": len(pack.evidence),
        "retrieval_warnings": "; ".join(pack.retrieval_warnings) if pack.retrieval_warnings else "none",
        "prior_analysis": _format_prior_results(scientific_result, translation_result),
        "claim_keys": CLAIM_KEYS,
    }


def _valid_evidence_ids(ids: list[str], pack: EvidencePack) -> list[str]:
    known = {ev.id for ev in pack.evidence}
    return [eid for eid in ids if eid in known]


def _to_claims(analysis: ClinicalPlanAnalysis, pack: EvidencePack) -> list[Claim]:
    claims: list[Claim] = []
    known = {ev.id for ev in pack.evidence}
    for c in analysis.claims:
        valid_ids = _valid_evidence_ids(c.evidence_ids, pack)
        dropped_ids = list(dict.fromkeys(eid for eid in c.evidence_ids if eid not in known))
        status = c.support_status
        assumptions = list(c.assumptions)
        if dropped_ids:
            assumptions.append(f"claim {c.key}: dropped unknown evidence ids {dropped_ids}")
        if status in ("supported", "contradicted", "mixed") and not valid_ids:
            status = "unverified"
        claims.append(
            Claim(
                id=c.key,
                text=c.text,
                provenance="ai",
                support_status=status,
                evidence_ids=valid_ids,
                assumptions=assumptions,
                scope=c.scope,
                importance=c.importance,
            )
        )
    return claims


def _to_risks(analysis: ClinicalPlanAnalysis) -> list[Risk]:
    return [
        Risk(
            id=r.id,
            description=r.description,
            priority=r.priority,
            claim_ids=r.related_claim_keys,
            impact=r.impact,
            next_check=r.next_check,
        )
        for r in analysis.risks
    ]


async def analyze_clinical(
    case: CaseInput,
    pack: EvidencePack,
    scientific_result: RoleResult,
    translation_result: RoleResult,
    ctx: RunContext,
) -> RoleResult:
    payload = _build_payload(case, pack, scientific_result, translation_result)

    analysis: ClinicalPlanAnalysis = await ctx.model.generate_structured(
        PROMPT_ID, payload, ClinicalPlanAnalysis, ctx,
    )

    if not analysis.trial_size.has_basis:
        analysis.trial_size.estimate = None
        if not analysis.trial_size.statistical_design_gap:
            analysis.trial_size.statistical_design_gap = (
                "Insufficient data to determine trial size; "
                "statistical design consultation needed"
            )

    claims = _to_claims(analysis, pack)
    risks = _to_risks(analysis)

    trial_size_data = {
        "has_basis": analysis.trial_size.has_basis,
        "estimate": analysis.trial_size.estimate,
        "assumptions": analysis.trial_size.assumptions,
        "statistical_design_gap": analysis.trial_size.statistical_design_gap,
    }

    study_sequence_data = [
        {
            "phase": sp.phase,
            "objective": sp.objective,
            "population": sp.population,
            "primary_endpoint": sp.primary_endpoint,
            "duration_estimate": sp.duration_estimate,
            "key_assumptions": sp.key_assumptions,
        }
        for sp in analysis.study_sequence
    ]

    analogues_data = [
        {
            "name": a.name,
            "relevance": a.relevance,
            "outcome": a.outcome,
            "lessons": a.lessons,
        }
        for a in analysis.historical_analogues
    ]

    diligence_data = [
        {
            "question": dq.question,
            "why_it_matters": dq.why_it_matters,
            "evidence_needed": dq.evidence_needed,
            "decision_if_positive": dq.decision_if_positive,
            "decision_if_negative": dq.decision_if_negative,
        }
        for dq in analysis.diligence_questions
    ]

    section = SectionContent(
        key="clinical_development_plan",
        summary=analysis.thesis,
        claim_ids=[c.id for c in claims],
        limitations=analysis.limitations,
        structured_data={
            "target_population": analysis.target_population,
            "clinically_meaningful_outcome": analysis.clinically_meaningful_outcome,
            "primary_endpoint": analysis.primary_endpoint,
            "secondary_endpoints": analysis.secondary_endpoints,
            "comparator": analysis.comparator,
            "biomarker_strategy": analysis.biomarker_strategy,
            "trial_size": trial_size_data,
            "study_sequence": study_sequence_data,
            "regulatory_context": analysis.regulatory_context,
            "historical_analogues": analogues_data,
            "next_milestone": analysis.next_milestone,
            "standard_of_care": analysis.standard_of_care,
            "unmet_need": analysis.unmet_need,
            "diligence_questions": diligence_data,
            "science_gaps_carried_forward": analysis.science_gaps_carried_forward,
        },
    )

    unknowns = list(analysis.unknowns)
    unknowns.extend(
        assumption
        for claim in claims
        for assumption in claim.assumptions
        if "dropped unknown evidence ids" in assumption
    )
    unknowns = list(dict.fromkeys(unknowns))

    return RoleResult(
        role_id="clinical",
        summary=analysis.thesis,
        position=analysis.position,
        claims=claims,
        risks=risks,
        unknowns=unknowns,
        change_conditions=analysis.change_conditions,
        section_content=[section],
    )