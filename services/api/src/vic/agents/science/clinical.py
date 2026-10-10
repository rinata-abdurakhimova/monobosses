from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, create_model, model_validator

from vic.contracts import (
    CaseInput,
    Claim,
    EvidencePack,
    Risk,
    RoleResult,
    RunContext,
    RunStage,
    SectionContent,
)

PROMPT_ID = "clinical"
PROMPT_VERSION = "1.3.0"

ClinicalClaimKey = Literal[
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
CLAIM_KEYS: list[str] = list(get_args(ClinicalClaimKey))

ClaimStatus = Literal["supported", "contradicted", "mixed", "unverified", "unknown"]
Scope = Literal["approach", "program"]
Importance = Literal["critical", "major", "minor"]
Priority = Literal["critical", "major", "minor"]
ClinicalPosition = Literal["feasible", "conditionally_feasible", "challenging", "insufficient_data"]

_TRIAL_SIZE_DEFAULT_GAP = (
    "Insufficient data to determine trial size; statistical design consultation needed"
)


class _TrialSizeEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

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

    @model_validator(mode="after")
    def enforce_trial_size_basis(self) -> _TrialSizeEstimate:
        if self.has_basis:
            if not (self.estimate and self.estimate.strip()):
                raise ValueError("trial_size: has_basis=True requires a non-empty estimate")
            if not self.assumptions and not self.evidence_ids:
                raise ValueError(
                    "trial_size: has_basis=True requires assumptions or evidence_ids; "
                    "an ungrounded trial size is not allowed"
                )
        else:
            self.estimate = None
            if not self.statistical_design_gap:
                self.statistical_design_gap = _TRIAL_SIZE_DEFAULT_GAP
        return self


class _StudyPhase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    phase: str = Field(min_length=1, description="e.g. 'Phase 1', 'Phase 1b/2', 'Phase 2', 'Phase 3'")
    objective: str = Field(min_length=1)
    population: str = Field(min_length=1)
    primary_endpoint: str = Field(min_length=1)
    duration_estimate: str | None = None
    key_assumptions: list[str] = Field(default_factory=list)


class _HistoricalAnalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    relevance: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    lessons: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class _ClaimOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    key: ClinicalClaimKey
    text: str = Field(min_length=1)
    support_status: ClaimStatus
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    scope: Scope
    importance: Importance
    reasoning: str = Field(min_length=1)


class _RiskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1, description="Stable risk identifier, e.g. 'clinical.risk.endpoint_miss'")
    description: str = Field(min_length=1)
    priority: Priority
    related_claim_keys: list[ClinicalClaimKey] = Field(default_factory=list)
    impact: str = Field(min_length=1)
    next_check: str = Field(min_length=1)


class _DiligenceQuestionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    question: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    evidence_needed: str = Field(min_length=1)
    decision_if_positive: str = Field(min_length=1)
    decision_if_negative: str = Field(min_length=1)


class ClinicalPlanAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    thesis: str = Field(min_length=1, description="One-paragraph clinical development thesis")
    position: ClinicalPosition
    target_population: str = Field(min_length=1)
    clinically_meaningful_outcome: str = Field(min_length=1)
    primary_endpoint: str = Field(min_length=1)
    secondary_endpoints: list[str] = Field(default_factory=list)
    comparator: str = Field(min_length=1)
    biomarker_strategy: str = Field(min_length=1)
    trial_size: _TrialSizeEstimate
    study_sequence: list[_StudyPhase]
    regulatory_context: str = Field(
        min_length=1,
        description="Relevant precedents and regulatory considerations; mark as context, not guarantee",
    )
    historical_analogues: list[_HistoricalAnalogue] = Field(default_factory=list)
    next_milestone: str = Field(
        min_length=1,
        description="The next value-creating milestone and evidence needed to reach it",
    )
    standard_of_care: str = Field(min_length=1)
    unmet_need: str = Field(min_length=1)
    claims: list[_ClaimOutput]
    risks: list[_RiskOutput]
    unknowns: list[str]
    change_conditions: list[str]
    diligence_questions: list[_DiligenceQuestionOutput] = Field(default_factory=list)
    limitations: list[str]
    science_gaps_carried_forward: list[str] = Field(
        description="Unresolved gaps from scientific/translation analysis that affect the clinical plan"
    )

    @model_validator(mode="after")
    def reject_duplicate_claim_keys(self) -> ClinicalPlanAnalysis:
        keys = [claim.key for claim in self.claims]
        if len(keys) != len(set(keys)):
            raise ValueError("clinical claim keys must be unique")
        return self


_COMMON_FIELDS = {"claims", "risks", "unknowns", "change_conditions", "limitations",
                  "science_gaps_carried_forward"}
_DESIGN_FIELDS = {"target_population", "clinically_meaningful_outcome", "primary_endpoint",
                  "secondary_endpoints", "comparator", "biomarker_strategy", "trial_size",
                  "standard_of_care", "unmet_need"}
_DEVELOPMENT_FIELDS = set(ClinicalPlanAnalysis.model_fields) - _COMMON_FIELDS - _DESIGN_FIELDS
CLINICAL_REQUEST_SPLIT_BYTES = 14000
_DESIGN_CLAIMS = {"clinical.target_population", "clinical.primary_endpoint",
                  "clinical.secondary_endpoints", "clinical.comparator_choice",
                  "clinical.biomarker_strategy", "clinical.trial_size_basis",
                  "clinical.standard_of_care", "clinical.unmet_need"}


def _pass_model(name: str, fields: set[str], keys: set[str]) -> type[BaseModel]:
    claim_model = create_model(name + "Claim", __base__=_ClaimOutput,
                               key=(Literal[tuple(sorted(keys))], ...))
    return create_model(name, __config__=ConfigDict(extra="forbid", strict=True), **{
        key: (list[claim_model] if key == "claims" else field.annotation, field)
        for key, field in ClinicalPlanAnalysis.model_fields.items()
        if key in fields | _COMMON_FIELDS
    })


ClinicalDesignAnalysis = _pass_model("ClinicalDesignAnalysis", _DESIGN_FIELDS, _DESIGN_CLAIMS)
ClinicalDevelopmentAnalysis = _pass_model("ClinicalDevelopmentAnalysis", _DEVELOPMENT_FIELDS,
                                         set(CLAIM_KEYS) - _DESIGN_CLAIMS)


async def _split_analysis(payload: dict, ctx: RunContext) -> ClinicalPlanAnalysis:
    parts = []
    for prompt_id, model, keys in (
        ("clinical_design", ClinicalDesignAnalysis, _DESIGN_CLAIMS),
        ("clinical_development", ClinicalDevelopmentAnalysis, set(CLAIM_KEYS) - _DESIGN_CLAIMS),
    ):
        part_payload = {**payload, "claim_keys": sorted(keys)}
        sizes = ctx.model.structured_request_size(prompt_id, part_payload, model, ctx)
        ctx.trace.log(RunStage.ANALYZE, f"{prompt_id} request sizes {sizes}")
        raw = await ctx.model.generate_structured(prompt_id, part_payload, model, ctx)
        part = model.model_validate(raw.model_dump() if isinstance(raw, BaseModel) else raw)
        if any(claim.key not in keys for claim in part.claims):
            raise ValueError(f"{prompt_id}: claim outside assigned clinical task")
        parts.append(part.model_dump())
    return ClinicalPlanAnalysis.model_validate(_merge_parts(parts))


def _merge_parts(parts: list[dict]) -> dict:
    merged = {key: value for part in parts for key, value in part.items()
              if key not in _COMMON_FIELDS}
    for key in _COMMON_FIELDS:
        merged[key] = []
        for part in parts:
            for item in part[key]:
                if key == "risks":
                    prior = next((r for r in merged[key] if r["id"] == item["id"]), None)
                    if prior:
                        # Preserve both assessments under the existing stable risk id.
                        for text_key in ("description", "impact", "next_check"):
                            if item[text_key] != prior[text_key]:
                                prior[text_key] += "; " + item[text_key]
                        prior["related_claim_keys"] = list(dict.fromkeys(
                            prior["related_claim_keys"] + item["related_claim_keys"]))
                        priorities = ["critical", "major", "minor"]
                        prior["priority"] = min(prior["priority"], item["priority"],
                                                key=priorities.index)
                        continue
                if item not in merged[key]:
                    merged[key].append(item)
    return merged


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
    for title, result in (
        ("SCIENTIFIC ANALYSIS", scientific_result),
        ("TRANSLATION ANALYSIS", translation_result),
    ):
        if sections:
            sections.append("")
        sections.append(f"=== {title} ===")
        sections.append(f"Position: {result.position}")
        sections.append(f"Thesis: {result.summary}")
        if result.claims:
            sections.append("Claims:")
            for c in result.claims:
                sections.append(f"  [{c.id}] ({_val(c.support_status)}, {_val(c.importance)}) {c.text}")
        if result.risks:
            sections.append("Risks:")
            for r in result.risks:
                sections.append(f"  [{r.id}] ({_val(r.priority)}) {r.description}")
        if result.unknowns:
            sections.append("Unknowns: " + "; ".join(result.unknowns))
        if result.change_conditions:
            sections.append("Change conditions: " + "; ".join(result.change_conditions))
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
    return list(dict.fromkeys(eid for eid in ids if eid in known))


def _dropped_evidence_ids(ids: list[str], pack: EvidencePack) -> list[str]:
    known = {ev.id for ev in pack.evidence}
    return list(dict.fromkeys(eid for eid in ids if eid not in known))


def _missing_evidence_message(claim_key: str) -> str:
    return f"{claim_key}: no valid evidence references remain after evidence-pack filtering."


def _to_claims(analysis: ClinicalPlanAnalysis, pack: EvidencePack) -> list[Claim]:
    claims: list[Claim] = []
    evidence_dependent_statuses = {"supported", "contradicted", "mixed"}
    for output in analysis.claims:
        valid_ids = _valid_evidence_ids(output.evidence_ids, pack)
        dropped_ids = _dropped_evidence_ids(output.evidence_ids, pack)
        status = output.support_status
        assumptions = list(output.assumptions)
        text = output.text
        if dropped_ids:
            assumptions.append(f"claim {output.key}: dropped unknown evidence ids {dropped_ids}")
        if status in evidence_dependent_statuses and not valid_ids:
            status = "unverified"
            message = _missing_evidence_message(output.key)
            assumptions.append(message)
            text = f"This conclusion is unverified. {message}"
        elif status in {"unknown", "unverified"} and not valid_ids:
            assumptions.append(_missing_evidence_message(output.key))
        claims.append(
            Claim(
                id=output.key,
                text=text,
                provenance="ai",
                support_status=status,
                evidence_ids=valid_ids,
                assumptions=list(dict.fromkeys(assumptions)),
                scope=output.scope,
                importance=output.importance,
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


def _normalise_trial_size(
    trial_size: _TrialSizeEstimate, pack: EvidencePack
) -> tuple[dict[str, object], list[str]]:
    valid_ids = _valid_evidence_ids(trial_size.evidence_ids, pack)
    dropped_ids = _dropped_evidence_ids(trial_size.evidence_ids, pack)
    notes: list[str] = []
    if dropped_ids:
        notes.append(f"trial_size: dropped unknown evidence ids {dropped_ids}")

    has_basis = trial_size.has_basis
    estimate = trial_size.estimate
    gap = trial_size.statistical_design_gap
    if has_basis and not valid_ids and not trial_size.assumptions:
        has_basis = False
        notes.append(
            "trial_size: estimate discarded because no valid evidence or stated assumptions "
            "remain after evidence-pack filtering."
        )
    if not has_basis:
        estimate = None
        gap = gap or _TRIAL_SIZE_DEFAULT_GAP

    return (
        {
            "has_basis": has_basis,
            "estimate": estimate,
            "assumptions": list(trial_size.assumptions),
            "statistical_design_gap": gap,
            "evidence_ids": valid_ids,
        },
        notes,
    )


def _normalise_analogues(
    analysis: ClinicalPlanAnalysis, pack: EvidencePack
) -> tuple[list[dict[str, object]], list[str]]:
    analogues: list[dict[str, object]] = []
    notes: list[str] = []
    for a in analysis.historical_analogues:
        valid_ids = _valid_evidence_ids(a.evidence_ids, pack)
        dropped_ids = _dropped_evidence_ids(a.evidence_ids, pack)
        if dropped_ids:
            notes.append(f"historical analogue '{a.name}': dropped unknown evidence ids {dropped_ids}")
        if not valid_ids:
            notes.append(
                f"historical analogue '{a.name}': no valid evidence reference; treat as unverified context."
            )
        analogues.append(
            {
                "name": a.name,
                "relevance": a.relevance,
                "outcome": a.outcome,
                "lessons": a.lessons,
                "evidence_ids": valid_ids,
            }
        )
    return analogues, notes


def _validate_analysis(value: object) -> ClinicalPlanAnalysis:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    return ClinicalPlanAnalysis.model_validate(value)


async def analyze_clinical(
    case: CaseInput,
    pack: EvidencePack,
    scientific_result: RoleResult,
    translation_result: RoleResult,
    ctx: RunContext,
) -> RoleResult:
    subtask_generator = getattr(ctx.model, "generate_clinical_subtasks", None)
    if callable(subtask_generator):
        raw_analysis = await subtask_generator(case, pack, scientific_result, translation_result, ctx)
    else:
        raw_analysis = await _legacy_analysis(case, pack, scientific_result, translation_result, ctx)
    analysis = _validate_analysis(raw_analysis)
    claims = _to_claims(analysis, pack)
    risks = _to_risks(analysis)
    trial_size_data, trial_size_notes = _normalise_trial_size(analysis.trial_size, pack)
    analogues_data, analogue_notes = _normalise_analogues(analysis, pack)

    study_sequence_data = [sp.model_dump() for sp in analysis.study_sequence]
    diligence_data = [dq.model_dump() for dq in analysis.diligence_questions]

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
        if "no valid evidence references remain" in assumption
        or "dropped unknown evidence ids" in assumption
    )
    unknowns.extend(trial_size_notes)
    unknowns.extend(analogue_notes)
    if not claims:
        unknowns.append("No clinical claims were returned; the clinical plan remains unverified.")
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


async def _legacy_analysis(case, pack, scientific_result, translation_result, ctx):
    """Compatibility for custom adapters; production uses measured subtasks."""
    payload = _build_payload(case, pack, scientific_result, translation_result)
    split = False
    measure = getattr(ctx.model, "structured_request_size", None)
    if callable(measure):
        sizes = measure(PROMPT_ID, payload, ClinicalPlanAnalysis, ctx)
        if isinstance(sizes, dict):
            ctx.trace.log(RunStage.ANALYZE, f"clinical request sizes {sizes}")
            split = sizes["request_bytes"] > CLINICAL_REQUEST_SPLIT_BYTES
    if split:
        raw_analysis = await _split_analysis(payload, ctx)
    else:
        raw_analysis = await ctx.model.generate_structured(
            PROMPT_ID, payload, ClinicalPlanAnalysis, ctx
        )
    return raw_analysis
