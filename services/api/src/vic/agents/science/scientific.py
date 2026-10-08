from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vic.contracts import (
    CaseInput,
    Claim,
    EvidencePack,
    Risk,
    RoleResult,
    RunContext,
    SectionContent,
)

PROMPT_ID = "science"
PROMPT_VERSION = "1.0.0"

CLAIM_KEYS = [
    "science.target_validation",
    "science.genetic_evidence",
    "science.expression_relevance",
    "science.pathway_biology",
    "science.perturbation_data",
    "science.animal_model_evidence",
    "science.prior_programs",
    "science.causal_vs_correlative",
]

ScientificClaimKey = Literal[
    "science.target_validation",
    "science.genetic_evidence",
    "science.expression_relevance",
    "science.pathway_biology",
    "science.perturbation_data",
    "science.animal_model_evidence",
    "science.prior_programs",
    "science.causal_vs_correlative",
]
ClaimStatus = Literal["supported", "contradicted", "mixed", "unverified", "unknown"]
Scope = Literal["approach", "program"]
Importance = Literal["critical", "major", "minor"]
Priority = Literal["critical", "major", "minor"]
ScientificPosition = Literal["strong", "moderate", "weak", "insufficient_data"]


class _ClaimOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    key: ScientificClaimKey
    text: str = Field(min_length=1)
    support_status: ClaimStatus
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    scope: Scope
    importance: Importance
    reasoning: str = Field(min_length=1)


class _RiskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: Priority
    related_claim_keys: list[ScientificClaimKey] = Field(default_factory=list)
    impact: str = Field(min_length=1)
    next_check: str = Field(min_length=1)


class ScientificAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    thesis: str = Field(min_length=1)
    position: ScientificPosition
    claims: list[_ClaimOutput]
    supporting_arguments: list[str]
    opposing_arguments: list[str]
    risks: list[_RiskOutput]
    unknowns: list[str]
    change_conditions: list[str]
    limitations: list[str]

    @model_validator(mode="after")
    def reject_duplicate_claim_keys(self) -> ScientificAnalysis:
        keys = [claim.key for claim in self.claims]
        if len(keys) != len(set(keys)):
            raise ValueError("scientific claim keys must be unique")
        return self


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


def _build_payload(case: CaseInput, pack: EvidencePack) -> dict:
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
        "claim_keys": CLAIM_KEYS,
    }


def _valid_evidence_ids(ids: list[str], pack: EvidencePack) -> list[str]:
    known = {ev.id for ev in pack.evidence}
    return list(dict.fromkeys(eid for eid in ids if eid in known))


def _missing_evidence_message(claim_key: str) -> str:
    return f"{claim_key}: no valid evidence references remain after evidence-pack filtering."


def _to_claims(analysis: ScientificAnalysis, pack: EvidencePack) -> list[Claim]:
    claims: list[Claim] = []
    evidence_dependent_statuses = {"supported", "contradicted", "mixed"}
    for output in analysis.claims:
        valid_ids = _valid_evidence_ids(output.evidence_ids, pack)
        status = output.support_status
        assumptions = list(output.assumptions)
        text = output.text
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


def _to_risks(analysis: ScientificAnalysis) -> list[Risk]:
    return [
        Risk(
            id=risk.id,
            description=risk.description,
            priority=risk.priority,
            claim_ids=risk.related_claim_keys,
            impact=risk.impact,
            next_check=risk.next_check,
        )
        for risk in analysis.risks
    ]


def _validate_analysis(value: object) -> ScientificAnalysis:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    return ScientificAnalysis.model_validate(value)


async def analyze_science(
    case: CaseInput,
    pack: EvidencePack,
    ctx: RunContext,
) -> RoleResult:
    payload = _build_payload(case, pack)
    raw_analysis = await ctx.model.generate_structured(
        PROMPT_ID, payload, ScientificAnalysis, ctx
    )
    analysis = _validate_analysis(raw_analysis)
    claims = _to_claims(analysis, pack)
    risks = _to_risks(analysis)

    unknowns = list(analysis.unknowns)
    unknowns.extend(
        assumption
        for claim in claims
        for assumption in claim.assumptions
        if "no valid evidence references remain" in assumption
    )
    if not claims:
        unknowns.append("No scientific claims were returned; the scientific thesis remains unverified.")
    unknowns = list(dict.fromkeys(unknowns))

    section = SectionContent(
        key="scientific_thesis",
        summary=analysis.thesis,
        claim_ids=[claim.id for claim in claims],
        limitations=analysis.limitations,
        structured_data={
            "supporting_arguments": analysis.supporting_arguments,
            "opposing_arguments": analysis.opposing_arguments,
        },
    )

    return RoleResult(
        role_id="science",
        summary=analysis.thesis,
        position=analysis.position,
        claims=claims,
        risks=risks,
        unknowns=unknowns,
        change_conditions=analysis.change_conditions,
        section_content= [section],
    )
