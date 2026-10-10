"""Evidence-only IP screening. No retrieval, deal valuation or legal clearance."""
import hashlib
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from vic.contracts import (
    CaseInput, Claim, EvidencePack, Risk, RoleResult, RunContext, RunStage, SectionContent,
)
from vic.integrity import assert_pack

PROMPT_ID = "ip_licensing"
PROMPT_VERSION = "1.0.0"
PROMPT_PATH = Path(__file__).parent / "prompts" / "ip_licensing.md"
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
CoverageArea = Literal[
    "patents", "protected_subjects", "territories_and_term", "rights_and_licenses",
    "freedom_to_operate", "licensable_assets", "licensing_options", "deal_data",
    "partnership_investment_implications",
]


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class IPClaim(Claim):
    id: str = Field(max_length=128, pattern=r"^ip_licensing\.[a-z][a-z0-9_]*$")
    provenance: Literal["source", "user", "ai"]


class IPFinding(StrictOutput):
    """A sourced observation, explicit hypothesis, or explained unknown."""
    value: Text | None
    basis: Literal["documented", "hypothesis", "unknown"]
    claim_ids: list[str]
    assumptions: list[Text]
    unknowns: list[Text]


class ProtectedSubject(StrictOutput):
    category: Literal["molecule", "composition", "method_of_use", "manufacturing",
                      "formulation", "delivery", "biomarker", "other", "unknown"]
    description: IPFinding


class TerritoryTerm(StrictOutput):
    territory: Text
    # Dates are supplied facts; NEVER calculated from filing year plus a term.
    confirmed_expiry_date: date | None
    status_as_of: date | None
    protection_status: Literal["pending", "granted", "expired", "lapsed", "revoked",
                               "withdrawn", "unknown"]
    claim_ids: list[str]
    unknowns: list[Text]


class PatentRecord(StrictOutput):
    id: str = Field(pattern=r"^ip_patent_[a-z0-9_]+$")
    record_type: Literal["patent", "application"]
    publication_number: IPFinding
    title: IPFinding
    applicants: IPFinding
    owners: IPFinding
    legal_status: IPFinding
    status_as_of: date | None
    protected_subjects: list[ProtectedSubject]
    territories_and_term: list[TerritoryTerm]
    relevance: IPFinding
    unknowns: list[Text]


class LicenseRecord(StrictOutput):
    id: str = Field(pattern=r"^ip_license_[a-z0-9_]+$")
    patent_ids: list[str]
    licensors: IPFinding
    licensees: IPFinding
    rights_granted: IPFinding
    exclusivity: IPFinding
    territory: IPFinding
    term: IPFinding
    field_of_use: IPFinding
    assignment_restrictions: IPFinding
    sublicensing_restrictions: IPFinding
    other_restrictions: IPFinding
    unknowns: list[Text]


class LicensableAsset(StrictOutput):
    id: str = Field(pattern=r"^ip_asset_[a-z0-9_]+$")
    asset_type: Literal["patent_rights", "know_how", "data", "manufacturing_process",
                        "material", "other"]
    patent_ids: list[str]
    license_ids: list[str]
    description: IPFinding
    control_of_rights: IPFinding
    licensing_uncertainties: list[Text]


class LicensingOption(StrictOutput):
    id: str = Field(pattern=r"^ip_option_[a-z0-9_]+$")
    format: Literal["exclusive", "nonexclusive", "field_limited", "territory_limited",
                    "option_to_license", "cross_license", "other"]
    asset_ids: list[str] = Field(min_length=1)
    rationale: IPFinding
    prerequisites: list[Text] = Field(min_length=1)
    unknown_terms: list[Text]
    # No invented upfront, royalty, milestone payment or acquisition price fields.


class PatentBarrier(StrictOutput):
    id: str = Field(pattern=r"^ip_barrier_[a-z0-9_]+$")
    patent_ids: list[str]
    license_ids: list[str]
    concern: IPFinding
    affected_activity: Literal["research", "development", "manufacturing", "sale",
                               "transfer", "multiple", "unknown"]
    consequence: Text
    next_check: Text


class FTOAssessment(StrictOutput):
    status: Literal["potential_barriers", "unresolved"]
    assessment: IPFinding
    barriers: list[PatentBarrier]
    missing_checks: list[Text] = Field(min_length=1)


class DealDataGap(StrictOutput):
    topic: Text
    missing_data: Text
    evidence_needed: Text
    impact_on_deal: Text


class LegalQuestion(StrictOutput):
    question: Text
    why_it_matters: Text
    evidence_needed: Text
    decision_if_positive: Text
    decision_if_negative: Text
    claim_ids: list[str]
    patent_ids: list[str]
    license_ids: list[str]


class IPImplication(StrictOutput):
    finding: IPFinding
    partnership_impact: Text
    investment_impact: Text
    next_check: Text


class CoverageFinding(StrictOutput):
    status: Literal["documented", "insufficient_data"]
    claim_ids: list[str]
    unknowns: list[Text]


class IPLicensingAnalysis(StrictOutput):
    summary: Text
    position: Literal["potential_barriers", "mixed", "insufficient_data"]
    claims: list[IPClaim]
    patents: list[PatentRecord]
    rights_and_licenses: list[LicenseRecord]
    licensable_assets: list[LicensableAsset]
    licensing_options: list[LicensingOption]
    freedom_to_operate: FTOAssessment
    deal_data_gaps: list[DealDataGap]
    specialist_questions: list[LegalQuestion] = Field(min_length=1)
    implications: list[IPImplication]
    coverage: dict[CoverageArea, CoverageFinding]
    risks: list[Risk]
    unknowns: list[Text]
    change_conditions: list[Text]
    limitations: list[Text]


def prepare_ip_licensing_inputs(case: CaseInput, pack: EvidencePack, ctx: RunContext,
                                *, science: RoleResult | None = None,
                                clinical: RoleResult | None = None,
                                market: RoleResult | None = None) -> dict:
    """Keep the full snapshot. Upstream outputs are context, not new evidence."""
    assert_pack(pack)
    if ctx.snapshot_id is not None and ctx.snapshot_id != pack.snapshot_id:
        raise ValueError("RunContext and evidence snapshot differ")
    if ctx.as_of_date is not None and case.as_of_date is not None and ctx.as_of_date != case.as_of_date:
        raise ValueError("Case and context as_of_date differ")
    evidence_ids = {e.id for e in pack.evidence}
    context = {}
    for name, result in (("science", science), ("clinical", clinical), ("market", market)):
        if result is not None:
            if result.role_id != name:
                raise ValueError(f"Expected {name} RoleResult")
            if any(not set(c.evidence_ids) <= evidence_ids for c in result.claims):
                raise ValueError(f"{name} references evidence outside the supplied snapshot")
            context[name] = result.model_dump(mode="json")
        else:
            context[name] = None
    sources = {s.id: s for s in pack.sources}
    return {
        "prompt_version": PROMPT_VERSION,
        "case": case.model_dump(mode="json"),
        "as_of_date": (ctx.as_of_date or case.as_of_date).isoformat()
                      if ctx.as_of_date or case.as_of_date else None,
        "snapshot_id": pack.snapshot_id,
        "sources": [s.model_dump(mode="json") for s in pack.sources],
        "evidence": [e.model_dump(mode="json") | {"synthetic": sources[e.source_id].synthetic}
                     for e in pack.evidence],
        "synthetic": pack.synthetic or any(s.synthetic for s in pack.sources),
        "retrieval_warnings": pack.retrieval_warnings,
        "upstream_context": context,
        "context_availability": {k: v is not None for k, v in context.items()},
    }


def _walk(value):
    """Visit typed nested blocks for reference and missing-data validation."""
    if isinstance(value, BaseModel):
        yield value
        for key in type(value).model_fields:
            yield from _walk(getattr(value, key))
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def normalize_ip_risk_ids(analysis: IPLicensingAnalysis) -> IPLicensingAnalysis:
    """Namespace model risk IDs without changing claims or substantive IP findings."""
    original_ids = [risk.id for risk in analysis.risks]
    if len(set(original_ids)) != len(original_ids):
        raise ValueError("Duplicate IP risk IDs are ambiguous")
    occupied = {rid for rid in original_ids if rid.startswith("ip_licensing.")}
    normalized = []
    for risk in analysis.risks:
        if risk.id.startswith("ip_licensing."):
            normalized.append(risk)
            continue
        # Hash the full original ID: distinct foreign namespaces stay distinct.
        base = "ip_licensing.risk." + hashlib.sha256(risk.id.encode("utf-8")).hexdigest()[:16]
        candidate, suffix = base, 1
        while candidate in occupied:
            candidate = f"{base}_{suffix}"
            suffix += 1
        occupied.add(candidate)
        normalized.append(risk.model_copy(update={"id": candidate}))
    return analysis.model_copy(update={"risks": normalized})


def validate_ip_licensing_result(analysis: IPLicensingAnalysis,
                                 case: CaseInput, pack: EvidencePack) -> None:
    """Structural screening only. Excerpt support and FTO need expert review."""
    claims = {c.id: c for c in analysis.claims}
    evidence = {e.id: e for e in pack.evidence}
    if len(claims) != len(analysis.claims):
        raise ValueError("Duplicate claim IDs")
    for claim in analysis.claims:
        if not set(claim.evidence_ids) <= evidence.keys():
            raise ValueError("Unknown evidence ID")
        if case.scope == "approach" and claim.scope == "program":
            raise ValueError("Program claim cannot expand approach scope")
        if claim.scope == "program" and claim.support_status in ("supported", "mixed", "contradicted"):
            if not any(evidence[e].scope == "program" for e in claim.evidence_ids):
                raise ValueError("Program fact requires program evidence")
        if claim.support_status in ("unknown", "unverified") and not claim.assumptions:
            raise ValueError("Unverified/unknown claims must explain their assumptions or gaps")
    collections = {"patent_ids": analysis.patents, "license_ids": analysis.rights_and_licenses,
                   "asset_ids": analysis.licensable_assets}
    for entries in [*collections.values(), analysis.licensing_options,
                    analysis.freedom_to_operate.barriers, analysis.risks]:
        if len({x.id for x in entries}) != len(entries):
            raise ValueError("Duplicate record IDs")
    for block in _walk(analysis):
        if hasattr(block, "claim_ids"):
            if not set(block.claim_ids) <= claims.keys():
                raise ValueError("Unknown claim reference")
        for attr, entries in collections.items():
            if hasattr(block, attr) and not set(getattr(block, attr)) <= {x.id for x in entries}:
                raise ValueError(f"Unknown {attr} reference")
        if isinstance(block, IPFinding):
            if block.basis == "unknown":
                if block.value is not None or not block.unknowns:
                    raise ValueError("Unknown finding needs null and an explicit gap")
            else:
                if block.value is None or not block.claim_ids:
                    raise ValueError("Finding requires value and claim references")
                linked = [claims[c] for c in block.claim_ids]
                if block.basis == "documented" and any(c.support_status != "supported" for c in linked):
                    raise ValueError("Documented finding requires supported claims")
                if block.basis == "hypothesis" and (not block.assumptions or
                        any(c.support_status not in ("unknown", "unverified") for c in linked)):
                    raise ValueError("Hypothesis must retain assumptions and unverified status")
        if isinstance(block, TerritoryTerm):
            if not block.claim_ids or any(claims[c].support_status != "supported" for c in block.claim_ids):
                raise ValueError("Territory/term requires supported claim references")
            if (block.confirmed_expiry_date is None or block.status_as_of is None or
                    block.protection_status == "unknown") and not block.unknowns:
                raise ValueError("Incomplete territory/term requires explicit gaps")
        if isinstance(block, PatentRecord):
            if block.publication_number.basis != "documented":
                raise ValueError("Listed patent/application requires documented identifier")
            if (block.status_as_of is None or not block.protected_subjects or
                    not block.territories_and_term) and not block.unknowns:
                raise ValueError("Incomplete patent requires explicit gaps")
        if isinstance(block, LicenseRecord) and block.rights_granted.basis != "documented":
            raise ValueError("Known license requires documented rights; proposals belong in options")
    if len({r.id for r in analysis.risks}) != len(analysis.risks):
        raise ValueError("Duplicate IP risk IDs are ambiguous")
    if any(not r.id.startswith("ip_licensing.") for r in analysis.risks):
        raise ValueError("Risk IDs must belong to ip_licensing")
    if set(analysis.coverage) != set(CoverageArea.__args__):
        raise ValueError("Coverage must explain every IP domain")
    domain_entries = {
        "patents": analysis.patents,
        "protected_subjects": [s for p in analysis.patents for s in p.protected_subjects],
        "territories_and_term": [t for p in analysis.patents for t in p.territories_and_term],
        "rights_and_licenses": analysis.rights_and_licenses,
        "freedom_to_operate": analysis.freedom_to_operate.barriers,
        "licensable_assets": analysis.licensable_assets,
        "licensing_options": analysis.licensing_options,
        "deal_data": analysis.deal_data_gaps,
        "partnership_investment_implications": analysis.implications,
    }
    for name, finding in analysis.coverage.items():
        if finding.status == "insufficient_data" and not finding.unknowns:
            raise ValueError("Missing coverage requires explicit gaps")
        if finding.status == "documented" and (not domain_entries[name] or not finding.claim_ids or
                any(claims[c].support_status != "supported" for c in finding.claim_ids)):
            raise ValueError("Documented coverage requires entries and supported claims")
    fto = analysis.freedom_to_operate
    if fto.status == "potential_barriers" and not fto.barriers:
        raise ValueError("Potential barriers requires listed concerns")
    if fto.status == "unresolved" and fto.barriers:
        raise ValueError("Listed barriers require potential_barriers status")
    if analysis.position == "potential_barriers" and not fto.barriers:
        raise ValueError("Position requires barriers")
    if not analysis.deal_data_gaps and analysis.coverage["deal_data"].status == "insufficient_data":
        raise ValueError("Missing deal data requires actionable data requests")
    if not pack.evidence and (analysis.position != "insufficient_data" or analysis.patents or
            analysis.rights_and_licenses or analysis.licensable_assets or analysis.licensing_options or
            fto.barriers or any(c.support_status == "supported" for c in analysis.claims)):
        raise ValueError("Empty evidence requires insufficient_data without factual IP records")


def identify_ip_licensing_gaps(analysis: IPLicensingAnalysis) -> list[str]:
    gaps = list(analysis.unknowns)
    for block in _walk(analysis):
        if block is not analysis and hasattr(block, "unknowns"):
            gaps.extend(block.unknowns)
        if isinstance(block, LicensableAsset):
            gaps.extend(block.licensing_uncertainties)
        if isinstance(block, LicensingOption):
            gaps.extend(block.unknown_terms)
    gaps.extend(analysis.freedom_to_operate.missing_checks)
    gaps.extend(f"{g.topic}: {g.missing_data}; evidence needed: {g.evidence_needed}"
                for g in analysis.deal_data_gaps)
    return list(dict.fromkeys(gaps))


async def analyze_ip_licensing(case: CaseInput, pack: EvidencePack, ctx: RunContext,
                               *, science: RoleResult | None = None,
                               clinical: RoleResult | None = None,
                               market: RoleResult | None = None) -> RoleResult:
    """One shared-adapter call, validation, then a shared RoleResult."""
    payload = prepare_ip_licensing_inputs(case, pack, ctx, science=science,
                                         clinical=clinical, market=market)
    if ctx.model is None or not callable(getattr(ctx.model, "generate_structured", None)):
        raise RuntimeError("R2 model adapter with generate_structured is required")
    raw = await ctx.model.generate_structured(PROMPT_ID, payload, IPLicensingAnalysis, ctx)
    analysis = IPLicensingAnalysis.model_validate(raw)
    original_risk_ids = [risk.id for risk in analysis.risks]
    analysis = normalize_ip_risk_ids(analysis)
    changed = sum(before != risk.id for before, risk in zip(original_risk_ids, analysis.risks))
    if changed:
        ctx.trace.log(RunStage.ANALYZE, f"ip_licensing normalized risk IDs: count={changed}")
    validate_ip_licensing_result(analysis, case, pack)
    gaps = identify_ip_licensing_gaps(analysis)
    limitations = list(dict.fromkeys([*analysis.limitations, *pack.retrieval_warnings,
        "Evidence support requires R3 audit; legal status, scope and FTO require specialist review.",
        "No legal clearance, deal valuation or confirmed licensing availability is provided."]))
    data = analysis.model_dump(mode="json", exclude={"claims", "risks"})
    data.update({"source_requests": gaps, "snapshot_id": pack.snapshot_id,
                 "as_of_date": payload["as_of_date"], "synthetic": payload["synthetic"],
                 "prompt_version": PROMPT_VERSION,
                 "context_availability": payload["context_availability"],
                 "claim_evidence_links": {c.id: c.evidence_ids for c in analysis.claims},
                 "evidence_source_links": {e.id: e.source_id for e in pack.evidence},
                 "legal_review_required": True})
    # Keep the existing 11-section contract. R2 merges this IP block with other
    # critical_unknowns contributions; it must not overwrite the whole section.
    section = SectionContent(key="critical_unknowns", summary=analysis.summary,
        claim_ids=[c.id for c in analysis.claims], limitations=limitations,
        structured_data={"ip_licensing": data})
    return RoleResult(role_id="ip_licensing", summary=analysis.summary,
        position=analysis.position, claims=[Claim.model_validate(c.model_dump()) for c in analysis.claims],
        risks=analysis.risks, unknowns=gaps, change_conditions=analysis.change_conditions,
        section_content=[section])
