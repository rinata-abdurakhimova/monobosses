"""R5 partnerships: one structured call, evidence links and explicit deal gaps.

No retrieval, outreach, upstream node execution, pricing or legal clearance.
Uses the shared RoleResult for both output and upstream context.
"""
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from vic.contracts import CaseInput, Claim, EvidencePack, Risk, RoleResult, RunContext, SectionContent
from vic.integrity import assert_pack

PROMPT_ID = "partnerships"
PROMPT_VERSION = "1.0.0"
PROMPT_PATH = Path(__file__).parent / "prompts" / "partnerships.md"
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Format = Literal["joint_research", "co_development", "licensing", "acquisition"]


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PartnershipClaim(Claim):
    id: str = Field(max_length=128, pattern=r"^partnerships\.[a-z][a-z0-9_]*$")


class Finding(StrictOutput):
    value: Text | None
    basis: Literal["documented", "hypothesis", "unknown"]
    claim_ids: list[str]
    assumptions: list[Text]
    unknowns: list[Text]


class PartnerFit(StrictOutput):
    work_direction: Finding
    portfolio: Finding
    capabilities: Finding
    partner_needs: Finding
    rationale: Finding


class CollaborationOption(StrictOutput):
    format: Format
    assessment: Literal["potential", "not_currently_suitable", "insufficient_data"]
    rationale: Finding
    prerequisites: list[Text] = Field(min_length=1)
    unknowns: list[Text]


class DataGap(StrictOutput):
    missing_result_or_data: Text
    why_needed_for_discussion: Text
    evidence_needed: Text


class PartnershipTiming(StrictOutput):
    stage: Finding
    milestone: Finding
    readiness: Literal["conditional", "not_ready", "insufficient_data"]
    conditions: list[Text] = Field(min_length=1)


class PartnershipDependency(StrictOutput):
    kind: Literal["ip_licensing", "science", "clinical", "market", "resources", "other"]
    finding: Finding
    impact: Text
    next_check: Text


class PartnershipCheck(StrictOutput):
    question: Text
    evidence_needed: Text
    decision_if_positive: Text
    decision_if_negative: Text
    claim_ids: list[str]


class InvestmentImplication(StrictOutput):
    finding: Finding
    scenario_effect: Text
    conditions: list[Text] = Field(min_length=1)
    next_check: Text


class PartnerCandidate(StrictOutput):
    id: str = Field(pattern=r"^partner_[a-z0-9_]+$")
    kind: Literal["organization", "category"]
    identity: Finding
    fit: PartnerFit
    required_competencies_and_resources: list[Finding] = Field(min_length=1)
    collaboration_options: list[CollaborationOption] = Field(min_length=4, max_length=4)
    project_offer: Finding
    discussion_gaps: list[DataGap] = Field(min_length=1)
    timing: PartnershipTiming
    dependencies: list[PartnershipDependency] = Field(min_length=1)
    risk_ids: list[str]
    next_checks: list[PartnershipCheck] = Field(min_length=1)
    investment_implications: list[InvestmentImplication] = Field(min_length=1)
    # Suitability never implies interest or readiness to sign a deal.
    partner_interest: Finding
    deal_readiness: Finding


class PartnershipsAnalysis(StrictOutput):
    summary: Text
    position: Literal["potential_fit", "mixed", "insufficient_data"]
    claims: list[PartnershipClaim]
    candidates: list[PartnerCandidate]
    candidate_search_unknowns: list[Text]
    risks: list[Risk]
    unknowns: list[Text]
    next_checks: list[PartnershipCheck] = Field(min_length=1)
    change_conditions: list[Text]
    limitations: list[Text]


def _walk(value):
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


def _validate_claims(claims, case, pack):
    evidence = {e.id: e for e in pack.evidence}
    if len({c.id for c in claims}) != len(claims):
        raise ValueError("Duplicate claim IDs")
    for c in claims:
        if not set(c.evidence_ids) <= evidence.keys():
            raise ValueError("Unknown evidence ID")
        if case.scope == "approach" and c.scope == "program":
            raise ValueError("Program claim cannot expand approach scope")
        if c.support_status in ("supported", "mixed", "contradicted"):
            if not c.evidence_ids:
                raise ValueError("Factual claim requires evidence")
            if c.scope == "program" and not any(evidence[e].scope == "program" for e in c.evidence_ids):
                raise ValueError("Program fact requires program evidence")
        elif not c.assumptions:
            raise ValueError("Unknown/unverified claim requires assumptions or gaps")


def prepare_partnerships_inputs(case: CaseInput, pack: EvidencePack, ctx: RunContext,
                                *, market: RoleResult | None = None,
                                ip_licensing: RoleResult | dict | None = None,
                                science: RoleResult | None = None,
                                clinical: RoleResult | None = None) -> dict:
    """Pass full evidence, sources and explicit upstream context; no retrieval."""
    assert_pack(pack)
    if ctx.snapshot_id is not None and ctx.snapshot_id != pack.snapshot_id:
        raise ValueError("Context and pack snapshots differ")
    if ctx.as_of_date is not None and case.as_of_date is not None and ctx.as_of_date != case.as_of_date:
        raise ValueError("Case and context dates differ")
    if isinstance(ip_licensing, dict):
        ip_licensing = RoleResult.model_validate(ip_licensing)
    context = {}
    for name, result in (("market", market), ("ip_licensing", ip_licensing),
                         ("science", science), ("clinical", clinical)):
        if result is not None:
            if result.role_id != name:
                raise ValueError(f"Expected {name} RoleResult")
            _validate_claims(result.claims, case, pack)
            known = {c.id for c in result.claims}
            for block in [*result.risks, *result.section_content]:
                if not set(block.claim_ids) <= known:
                    raise ValueError("Upstream contains unknown claim references")
            for section in result.section_content:
                data = section.structured_data or {}
                nested = data.get(name, data)
                if isinstance(nested, dict):
                    if nested.get("snapshot_id", pack.snapshot_id) != pack.snapshot_id:
                        raise ValueError("Upstream snapshot differs")
                    expected_date = ctx.as_of_date or case.as_of_date
                    if expected_date and nested.get("as_of_date", expected_date.isoformat()) != expected_date.isoformat():
                        raise ValueError("Upstream date differs")
            context[name] = result.model_dump(mode="json")
        else:
            context[name] = None
    sources = {s.id: s for s in pack.sources}
    as_of = ctx.as_of_date or case.as_of_date
    return {"prompt_version": PROMPT_VERSION, "case": case.model_dump(mode="json"),
            "snapshot_id": pack.snapshot_id, "as_of_date": as_of.isoformat() if as_of else None,
            "sources": [s.model_dump(mode="json") for s in pack.sources],
            "evidence": [e.model_dump(mode="json") | {"synthetic": sources[e.source_id].synthetic}
                         for e in pack.evidence],
            "synthetic": pack.synthetic or any(s.synthetic for s in pack.sources),
            "retrieval_warnings": pack.retrieval_warnings,
            "upstream_context": context,
            "context_availability": {k: v is not None for k, v in context.items()}}


def validate_partnerships_result(analysis: PartnershipsAnalysis, case: CaseInput,
                                pack: EvidencePack) -> None:
    """Validate structure and links, never factual accuracy or deal feasibility."""
    _validate_claims(analysis.claims, case, pack)
    claims = {c.id: c for c in analysis.claims}
    risks = {r.id: r for r in analysis.risks}
    for entries in (analysis.candidates, analysis.risks):
        if len({x.id for x in entries}) != len(entries):
            raise ValueError("Duplicate record IDs")
    for risk in analysis.risks:
        if not risk.id.startswith("partnerships."):
            raise ValueError("Risk ID must belong to partnerships")
        if not risk.claim_ids:
            raise ValueError("Risk requires claim references")
    for block in _walk(analysis):
        if hasattr(block, "claim_ids") and not set(block.claim_ids) <= claims.keys():
            raise ValueError("Unknown claim reference")
        if isinstance(block, Finding):
            if block.basis == "unknown":
                if block.value is not None or not block.unknowns:
                    raise ValueError("Unknown finding requires null and explicit gaps")
            else:
                if block.value is None or not block.claim_ids:
                    raise ValueError("Finding requires value and claim references")
                linked = [claims[c] for c in block.claim_ids]
                if block.basis == "documented" and any(c.support_status != "supported" for c in linked):
                    raise ValueError("Documented finding requires supported claims")
                if block.basis == "hypothesis" and (not block.assumptions or
                        any(c.support_status not in ("unverified", "unknown") for c in linked)):
                    raise ValueError("Hypothesis requires assumptions and unverified/unknown claims")
    if not analysis.candidates:
        if not analysis.candidate_search_unknowns or analysis.position != "insufficient_data":
            raise ValueError("No candidates requires insufficient_data and search gaps")
    if analysis.position == "potential_fit" and not any(
            p.fit.rationale.basis != "unknown" for p in analysis.candidates):
        raise ValueError("Potential fit requires a rationale")
    for partner in analysis.candidates:
        if partner.identity.basis == "unknown":
            raise ValueError("Candidate requires an explicit identity/category")
        if partner.kind == "organization" and partner.identity.basis != "documented":
            raise ValueError("Named organization requires documented identity")
        if set(o.format for o in partner.collaboration_options) != set(Format.__args__):
            raise ValueError("Assess each of the four formats exactly once")
        for option in partner.collaboration_options:
            if option.assessment == "insufficient_data" and not option.unknowns:
                raise ValueError("Insufficient format requires explicit gaps")
            if option.assessment != "insufficient_data" and option.rationale.basis == "unknown":
                raise ValueError("Format assessment requires a rationale")
        if not set(partner.risk_ids) <= risks.keys() or not partner.risk_ids:
            raise ValueError("Candidate requires valid risk references")
        if not any(d.kind == "ip_licensing" for d in partner.dependencies):
            raise ValueError("Candidate requires explicit IP dependency")
        # Interest/transaction readiness can only be direct documented facts or unknown.
        for field in (partner.partner_interest, partner.deal_readiness):
            if field.basis == "hypothesis":
                raise ValueError("Do not infer partner interest or deal readiness")
        if partner.timing.readiness == "conditional" and partner.timing.milestone.basis == "unknown":
            raise ValueError("Conditional timing requires a milestone")
    if not pack.evidence and (analysis.position != "insufficient_data" or
            any(p.kind == "organization" for p in analysis.candidates) or
            any(c.support_status in ("supported", "mixed", "contradicted") for c in analysis.claims)):
        raise ValueError("Empty evidence permits only explicit category hypotheses and insufficient_data")


def identify_partnerships_gaps(analysis: PartnershipsAnalysis) -> list[str]:
    """Collect existing gaps, without another model call or new analysis."""
    gaps = [*analysis.unknowns, *analysis.candidate_search_unknowns]
    for block in _walk(analysis):
        if block is not analysis and hasattr(block, "unknowns"):
            gaps.extend(block.unknowns)
        if isinstance(block, DataGap):
            gaps.append(f"{block.missing_result_or_data}; evidence needed: {block.evidence_needed}")
    for claim in analysis.claims:
        if claim.support_status in ("unknown", "unverified"):
            gaps.append(f"Requires verification: {claim.id}: {claim.text}")
    return list(dict.fromkeys(gaps))


async def analyze_partnerships(case: CaseInput, pack: EvidencePack, ctx: RunContext,
                               *, market: RoleResult | None = None,
                               ip_licensing: RoleResult | dict | None = None,
                               science: RoleResult | None = None,
                               clinical: RoleResult | None = None) -> RoleResult:
    payload = prepare_partnerships_inputs(case, pack, ctx, market=market,
        ip_licensing=ip_licensing, science=science, clinical=clinical)
    if ctx.model is None or not callable(getattr(ctx.model, "generate_structured", None)):
        raise RuntimeError("R2 model adapter with generate_structured is required")
    raw = await ctx.model.generate_structured(PROMPT_ID, payload, PartnershipsAnalysis, ctx)
    analysis = PartnershipsAnalysis.model_validate(raw)
    validate_partnerships_result(analysis, case, pack)
    gaps = identify_partnerships_gaps(analysis)
    for name, available in payload["context_availability"].items():
        if not available:
            gaps.append(f"{name} context absent; upstream alignment remains pending.")
    if not pack.evidence:
        gaps.append("No evidence supplied: partner fit and transaction feasibility are unverified.")
    limitations = list(dict.fromkeys([*analysis.limitations, *pack.retrieval_warnings,
        "Structural validation is not semantic evidence audit; R3 review required.",
        "Partner fit does not establish interest, deal readiness, price or investment return.",
        "IP rights and restrictions require specialist review."]))
    data = analysis.model_dump(mode="json", exclude={"claims", "risks"})
    data.update({"source_requests": list(dict.fromkeys(gaps)), "prompt_version": PROMPT_VERSION,
        "snapshot_id": pack.snapshot_id, "as_of_date": payload["as_of_date"],
        "synthetic": payload["synthetic"], "context_availability": payload["context_availability"],
        "claim_evidence_links": {c.id: c.evidence_ids for c in analysis.claims},
        "evidence_source_links": {e.id: e.source_id for e in pack.evidence}})
    section = SectionContent(key="commercial_opportunity", summary=analysis.summary,
        claim_ids=[c.id for c in analysis.claims], limitations=limitations,
        structured_data={"partnerships": data})
    return RoleResult(role_id="partnerships", summary=analysis.summary, position=analysis.position,
        claims=[Claim.model_validate(c.model_dump()) for c in analysis.claims], risks=analysis.risks,
        unknowns=data["source_requests"], change_conditions=analysis.change_conditions,
        section_content=[section])
