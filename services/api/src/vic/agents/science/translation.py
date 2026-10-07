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

TranslationLinkKey = Literal[
    "translation.molecular_effect",
    "translation.human_exposure",
    "translation.target_engagement",
    "translation.biological_response",
    "translation.patient_benefit",
]
ExtraClaimKey = Literal[
    "translation.safe_exposure",
    "translation.therapeutic_window",
    "translation.biomarker_gap",
    "translation.pk_pd_adequacy",
    "translation.tissue_penetration",
]
TranslationClaimKey = Literal[
    "translation.molecular_effect",
    "translation.human_exposure",
    "translation.target_engagement",
    "translation.biological_response",
    "translation.patient_benefit",
    "translation.safe_exposure",
    "translation.therapeutic_window",
    "translation.biomarker_gap",
    "translation.pk_pd_adequacy",
    "translation.tissue_penetration",
]
LinkStatus = Literal["established", "partially_established", "gap", "unknown"]
ClaimStatus = Literal["supported", "contradicted", "mixed", "unverified", "unknown"]
Scope = Literal["approach", "program"]
Importance = Literal["critical", "major", "minor"]
Priority = Literal["critical", "major", "minor"]
TranslationPosition = Literal["strong", "moderate", "weak", "insufficient_data"]


class _LinkAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    key: TranslationLinkKey
    status: LinkStatus
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_summary: str = Field(min_length=1)
    gaps: list[str]
    limitations: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    scope: Scope
    importance: Importance


class _AdditionalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    key: ExtraClaimKey
    text: str = Field(min_length=1)
    support_status: ClaimStatus
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    scope: Scope
    importance: Importance


class _RiskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    priority: Priority
    related_claim_keys: list[TranslationClaimKey] = Field(default_factory=list)
    impact: str = Field(min_length=1)
    next_check: str = Field(min_length=1)


class TranslationAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    thesis: str = Field(min_length=1)
    position: TranslationPosition
    links: list[_LinkAssessment]
    additional_claims: list[_AdditionalClaim] = Field(default_factory=list)
    barriers: list[str]
    risks: list[_RiskOutput]
    unknowns: list[str]
    change_conditions: list[str]
    data_needed: list[str]
    limitations: list[str]

    @model_validator(mode="after")
    def enforce_complete_ordered_chain(self) -> TranslationAnalysis:
        keys = [link.key for link in self.links]
        if keys != TRANSLATION_LINKS:
            raise ValueError(
                "translation links must contain all five distinct keys in the expected order: "
                + ", ".join(TRANSLATION_LINKS)
            )
        additional_keys = [claim.key for claim in self.additional_claims]
        if len(additional_keys) != len(set(additional_keys)):
            raise ValueError("additional translation claim keys must be unique")
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
        "translation_link_keys": TRANSLATION_LINKS,
        "extra_claim_keys": EXTRA_CLAIM_KEYS,
    }


def _valid_evidence_ids(ids: list[str], pack: EvidencePack) -> list[str]:
    known = {ev.id for ev in pack.evidence}
    return list(dict.fromkeys(eid for eid in ids if eid in known))


def _missing_evidence_message(claim_key: str) -> str:
    return f"{claim_key}: no valid evidence references remain after evidence-pack filtering."


def _is_animal_only_evidence(evidence_id: str, pack: EvidencePack) -> bool:
    evidence = next((item for item in pack.evidence if item.id == evidence_id), None)
    if evidence is None:
        return False
    text = evidence.excerpt.casefold()
    animal_markers = (
        "animal",
        "mouse",
        "mice",
        "murine",
        "rat ",
        "rats",
        "rodent",
        "monkey",
        "non-human primate",
        "preclinical",
        "in vivo model",
    )
    human_benefit_markers = (
        "patient",
        "participants",
        "clinical trial",
        "randomized",
        "placebo",
        "phase 1",
        "phase i",
        "phase 2",
        "phase ii",
        "phase 3",
        "phase iii",
        "quality of life",
        "hospitalization",
        "mortality",
    )
    return any(marker in text for marker in animal_markers) and not any(
        marker in text for marker in human_benefit_markers
    )


def _normalise_translation(
    analysis: TranslationAnalysis,
    pack: EvidencePack,
) -> tuple[list[Claim], dict[str, dict[str, object]], list[str]]:
    claims: list[Claim] = []
    summaries: dict[str, dict[str, object]] = {}
    missing_data: list[str] = []

    for link in analysis.links:
        valid_ids = _valid_evidence_ids(link.evidence_ids, pack)
        gaps = list(link.gaps)
        assumptions = list(link.assumptions)
        text = link.text
        effective_link_status = link.status
        support_status: ClaimStatus

        unsupported_positive = link.status in {"established", "partially_established"} and not valid_ids
        animal_only_benefit = (
            link.key == "translation.patient_benefit"
            and bool(valid_ids)
            and all(_is_animal_only_evidence(evidence_id, pack) for evidence_id in valid_ids)
        )

        if unsupported_positive:
            message = _missing_evidence_message(link.key)
            effective_link_status = "gap"
            support_status = "unknown"
            text = f"{link.key} is unknown because no valid evidence supports this translation link."
            gaps.append(message)
            assumptions.append(message)
            missing_data.append(message)
        elif animal_only_benefit:
            message = (
                "translation.patient_benefit: available evidence is limited to animal or "
                "preclinical efficacy and cannot establish human patient benefit."
            )
            effective_link_status = "gap"
            support_status = "unknown"
            text = "Human patient benefit is unknown; animal efficacy is not evidence of clinical benefit."
            gaps.append(message)
            assumptions.append(message)
            missing_data.append(message)
        elif link.status == "established":
            support_status = "supported"
        elif link.status == "partially_established":
            support_status = "mixed"
        else:
            support_status = "unknown"
            if not gaps:
                message = f"{link.key}: evidence is missing or insufficient to assess this link."
                gaps.append(message)
                assumptions.append(message)
                missing_data.append(message)

        claims.append(
            Claim(
                id=link.key,
                text=text,
                provenance="ai",
                support_status=support_status,
                evidence_ids=valid_ids,
                assumptions=list(dict.fromkeys(assumptions)),
                scope=link.scope,
                importance=link.importance,
            )
        )
        summaries[link.key] = {
            "status": effective_link_status,
            "support_status": support_status,
            "gaps": list(dict.fromkeys(gaps)),
            "evidence_summary": link.evidence_summary,
            "evidence_ids": valid_ids,
        }

    additional_keys: set[str] = set()
    for output in analysis.additional_claims:
        additional_keys.add(output.key)
        valid_ids = _valid_evidence_ids(output.evidence_ids, pack)
        status = output.support_status
        assumptions = list(output.assumptions)
        text = output.text

        if not valid_ids and status in {"supported", "contradicted", "mixed"}:
            message = _missing_evidence_message(output.key)
            if output.key == "translation.safe_exposure" and status != "contradicted":
                status = "unknown"
                text = "Safe human exposure is unknown because no valid human safety evidence was provided."
            else:
                status = "unverified"
                text = f"This conclusion is unverified. {message}"
            assumptions.append(message)
            missing_data.append(message)
        elif not valid_ids and status in {"unknown", "unverified"}:
            message = _missing_evidence_message(output.key)
            assumptions.append(message)
            missing_data.append(message)

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

    if "translation.safe_exposure" not in additional_keys:
        message = (
            "translation.safe_exposure: no valid human safety evidence was provided; "
            "absence of reported safety data does not establish safety."
        )
        claims.append(
            Claim(
                id="translation.safe_exposure",
                text="Safe human exposure is unknown because human safety data are missing.",
                provenance="ai",
                support_status="unknown",
                evidence_ids=[],
                assumptions=[message],
                scope="program",
                importance="critical",
            )
        )
        missing_data.append(message)

    return claims, summaries, list(dict.fromkeys(missing_data))


def _to_claims(analysis: TranslationAnalysis, pack: EvidencePack) -> list[Claim]:
    claims, _, _ = _normalise_translation(analysis, pack)
    return claims


def _to_risks(analysis: TranslationAnalysis) -> list[Risk]:
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


def _validate_analysis(value: object) -> TranslationAnalysis:
    if isinstance(value, BaseModel):
        value = value.model_dump()
    return TranslationAnalysis.model_validate(value)


async def analyze_translation(
    case: CaseInput,
    pack: EvidencePack,
    ctx: RunContext,
) -> RoleResult:
    payload = _build_payload(case, pack)
    raw_analysis = await ctx.model.generate_structured(
        PROMPT_ID, payload, TranslationAnalysis, ctx
    )
    analysis = _validate_analysis(raw_analysis)
    claims, link_summary, missing_data = _normalise_translation(analysis, pack)
    risks = _to_risks(analysis)
    unknowns = list(dict.fromkeys([*analysis.unknowns, *missing_data]))
    data_needed = list(dict.fromkeys([*analysis.data_needed, *missing_data]))

    section = SectionContent(
        key="human_translation_thesis",
        summary=analysis.thesis,
        claim_ids=[claim.id for claim in claims],
        limitations=analysis.limitations,
        structured_data={
            "translation_links": link_summary,
            "barriers": analysis.barriers,
            "data_needed": data_needed,
        },
    )

    return RoleResult(
        role_id="translation",
        summary=analysis.thesis,
        position=analysis.position,
        claims=claims,
        risks=risks,
        unknowns=unknowns,
        change_conditions=analysis.change_conditions,
        section_content=section,
    )
