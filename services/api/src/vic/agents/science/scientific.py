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


class _ClaimOutput(BaseModel):
    key: str = Field(description="Stable claim key, one of: " + ", ".join(CLAIM_KEYS))
    text: str = Field(description="Concise scientific claim statement")
    support_status: str = Field(
        description="One of: supported, contradicted, mixed, unverified, unknown"
    )
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="IDs from the evidence pack that support or inform this claim",
    )
    assumptions: list[str] = Field(default_factory=list)
    scope: str = Field(
        description="'approach' if about the mechanism generally, 'program' if about a specific candidate"
    )
    importance: str = Field(description="One of: critical, major, minor")
    reasoning: str = Field(
        description="How evidence was evaluated; explicitly state whether link is causal or correlative"
    )


class _RiskOutput(BaseModel):
    id: str = Field(description="Stable risk identifier, e.g. 'science.risk.off_target'")
    description: str
    priority: str = Field(description="One of: critical, major, minor")
    related_claim_keys: list[str] = Field(default_factory=list)
    impact: str = Field(description="What happens if this risk materialises")
    next_check: str = Field(description="What data or experiment would clarify this risk")


class ScientificAnalysis(BaseModel):
    thesis: str = Field(
        description="One-paragraph scientific thesis for the mechanism in this indication"
    )
    position: str = Field(
        description="Overall strength: strong, moderate, weak, or insufficient_data"
    )
    claims: list[_ClaimOutput] = Field(
        description="One claim per predefined key that is relevant; omit keys with no information at all"
    )
    supporting_arguments: list[str]
    opposing_arguments: list[str]
    risks: list[_RiskOutput]
    unknowns: list[str] = Field(
        description="Critical facts not known and not inferable from the evidence pack"
    )
    change_conditions: list[str] = Field(
        description="Specific future evidence or results that would materially change the assessment"
    )
    limitations: list[str] = Field(description="Limitations of the available evidence base")


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
    return [eid for eid in ids if eid in known]


def _to_claims(analysis: ScientificAnalysis, pack: EvidencePack) -> list[Claim]:
    claims: list[Claim] = []
    for c in analysis.claims:
        valid_ids = _valid_evidence_ids(c.evidence_ids, pack)
        status = c.support_status
        if status in ("supported", "contradicted", "mixed") and not valid_ids:
            status = "unverified"
        claims.append(
            Claim(
                id=c.key,
                text=c.text,
                provenance="ai",
                support_status=status,
                evidence_ids=valid_ids,
                assumptions=c.assumptions,
                scope=c.scope,
                importance=c.importance,
            )
        )
    return claims


def _to_risks(analysis: ScientificAnalysis) -> list[Risk]:
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


async def analyze_science(
    case: CaseInput,
    pack: EvidencePack,
    ctx: RunContext,
) -> RoleResult:
    payload = _build_payload(case, pack)

    analysis: ScientificAnalysis = await ctx.model.generate_structured(
        PROMPT_ID, payload, ScientificAnalysis, ctx,
    )

    claims = _to_claims(analysis, pack)
    risks = _to_risks(analysis)

    section = SectionContent(
        key="scientific_thesis",
        summary=analysis.thesis,
        claim_ids=[c.id for c in claims],
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
        unknowns=analysis.unknowns,
        change_conditions=analysis.change_conditions,
        section_content=[section],
    )
