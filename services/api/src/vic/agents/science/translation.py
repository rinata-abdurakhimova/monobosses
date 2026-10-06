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

PROMPT_ID = "translation"
PROMPT_VERSION = "1.0.0"

TRANSLATION_LINKS = [
    "translation.molecular_effect",
    "translation.human_exposure",
    "translation.target_engagement",
    "translation.biological_response",
    "translation.patient_benefit",
]

EXTRA_CLAIM_KEYS = [
    "translation.safe_exposure",
    "translation.therapeutic_window",
    "translation.biomarker_gap",
    "translation.pk_pd_adequacy",
    "translation.tissue_penetration",
]


class _LinkAssessment(BaseModel):
    key: str = Field(description="Stable claim key for this translation link")
    status: str = Field(
        description="One of: established, partially_established, gap, unknown"
    )
    text: str = Field(description="Assessment of this translation link")
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_summary: str = Field(description="What evidence shows for this link")
    gaps: list[str] = Field(description="What is missing or unknown for this link")
    limitations: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    scope: str = Field(description="'approach' or 'program'")
    importance: str = Field(description="One of: critical, major, minor")


class _AdditionalClaim(BaseModel):
    key: str = Field(
        description="Stable claim key from: " + ", ".join(EXTRA_CLAIM_KEYS)
    )
    text: str
    support_status: str = Field(
        description="One of: supported, contradicted, mixed, unverified, unknown"
    )
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    scope: str
    importance: str


class _RiskOutput(BaseModel):
    id: str
    description: str
    priority: str = Field(description="One of: critical, major, minor")
    related_claim_keys: list[str] = Field(default_factory=list)
    impact: str
    next_check: str


class TranslationAnalysis(BaseModel):
    thesis: str = Field(description="One-paragraph human translation thesis")
    position: str = Field(
        description="Overall translatability: strong, moderate, weak, or insufficient_data"
    )
    links: list[_LinkAssessment] = Field(
        description="Assessment of each of the 5 translation links in order"
    )
    additional_claims: list[_AdditionalClaim] = Field(
        default_factory=list,
        description="Additional translation-related claims beyond the 5 links",
    )
    barriers: list[str] = Field(description="Major barriers to successful translation")
    risks: list[_RiskOutput]
    unknowns: list[str]
    change_conditions: list[str]
    data_needed: list[str] = Field(
        description="Specific data or experiments needed to resolve gaps"
    )
    limitations: list[str]


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
        "translation_link_keys": TRANSLATION_LINKS,
        "extra_claim_keys": EXTRA_CLAIM_KEYS,
    }


def _valid_evidence_ids(ids: list[str], pack: EvidencePack) -> list[str]:
    known = {ev.id for ev in pack.evidence}
    return [eid for eid in ids if eid in known]


_LINK_STATUS_TO_SUPPORT = {
    "established": "supported",
    "partially_established": "mixed",
    "gap": "unknown",
    "unknown": "unknown",
}


def _to_claims(analysis: TranslationAnalysis, pack: EvidencePack) -> list[Claim]:
    claims: list[Claim] = []
    for link in analysis.links:
        valid_ids = _valid_evidence_ids(link.evidence_ids, pack)
        raw_status = _LINK_STATUS_TO_SUPPORT.get(link.status, "unverified")
        status = raw_status if raw_status != "supported" or valid_ids else "unverified"
        claims.append(
            Claim(
                id=link.key,
                text=link.text,
                provenance="ai",
                support_status=status,
                evidence_ids=valid_ids,
                assumptions=link.assumptions,
                scope=link.scope,
                importance=link.importance,
            )
        )
    for ac in analysis.additional_claims:
        valid_ids = _valid_evidence_ids(ac.evidence_ids, pack)
        status = ac.support_status
        if status == "supported" and not valid_ids:
            status = "unverified"
        claims.append(
            Claim(
                id=ac.key,
                text=ac.text,
                provenance="ai",
                support_status=status,
                evidence_ids=valid_ids,
                assumptions=ac.assumptions,
                scope=ac.scope,
                importance=ac.importance,
            )
        )
    return claims


def _to_risks(analysis: TranslationAnalysis) -> list[Risk]:
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


async def analyze_translation(
    case: CaseInput,
    pack: EvidencePack,
    ctx: RunContext,
) -> RoleResult:
    payload = _build_payload(case, pack)

    analysis: TranslationAnalysis = await ctx.model.generate_structured(
        PROMPT_ID, payload, TranslationAnalysis, ctx,
    )

    claims = _to_claims(analysis, pack)
    risks = _to_risks(analysis)

    link_summary = {
        link.key: {
            "status": link.status,
            "gaps": link.gaps,
            "evidence_summary": link.evidence_summary,
        }
        for link in analysis.links
    }

    section = SectionContent(
        key="human_translation_thesis",
        summary=analysis.thesis,
        claim_ids=[c.id for c in claims],
        limitations=analysis.limitations,
        structured_data={
            "translation_links": link_summary,
            "barriers": analysis.barriers,
            "data_needed": analysis.data_needed,
        },
    )

    return RoleResult(
        role_id="translation",
        summary=analysis.thesis,
        position=analysis.position,
        claims=claims,
        risks=risks,
        unknowns=analysis.unknowns,
        change_conditions=analysis.change_conditions,
        section_content=section,
    )