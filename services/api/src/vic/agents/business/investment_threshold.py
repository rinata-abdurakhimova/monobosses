"""Evidence-based investment gates; no final committee decision or arithmetic."""
from pathlib import Path
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from vic.contracts import CaseInput, Claim, EvidencePack, Risk, RoleResult, RunContext, SectionContent
from vic.integrity import assert_pack

PROMPT_ID = "investment_threshold"
PROMPT_VERSION = "1.0.0"
PROMPT_PATH = Path(__file__).parent / "prompts" / "investment_threshold.md"
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
UpstreamRole = Literal["science", "translation", "clinical", "market", "partnerships", "investment", "ip_licensing"]
ROLES = UpstreamRole.__args__


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ThresholdClaim(Claim):
    id: str = Field(max_length=128, pattern=r"^investment_threshold\.[a-z][a-z0-9_]*$")


class Finding(StrictOutput):
    value: Text | None
    basis: Literal["documented", "hypothesis", "unknown"]
    claim_ids: list[str]
    assumptions: list[Text]
    unknowns: list[Text]


class ContextDependency(StrictOutput):
    role_id: UpstreamRole
    assessment: Finding
    upstream_claim_ids: list[str]
    record_ids: list[Identifier]
    next_check: Text


class SuccessCriterion(StrictOutput):
    id: Identifier
    sufficient_result: Finding
    rationale: Finding
    assessment_method: Text


class ExistingEvidence(StrictOutput):
    criterion_id: Identifier
    finding: Finding
    evidence_ids: list[str]
    limitations: list[Text]


class OutcomeRule(StrictOutput):
    # These are prospective rules, not claims that the outcome has occurred.
    result: Text
    rationale: Text
    claim_ids: list[str]


class GapCheck(StrictOutput):
    method: Text
    evidence_needed: Text
    feasible_stage: Finding
    continue_if: OutcomeRule
    revise_if: OutcomeRule
    stop_if: OutcomeRule
    inconclusive_if: Text


class ThresholdGap(StrictOutput):
    id: Identifier
    criterion_ids: list[Identifier] = Field(min_length=1)
    missing_result_or_data: Text
    investment_impact: Finding
    priority: Literal["critical", "major", "minor"]
    check: GapCheck


class InvestmentGate(StrictOutput):
    id: Identifier
    horizon: Literal["now", "next_stage"]
    required_result: Finding
    obtainable_stage: Finding
    criteria: list[SuccessCriterion] = Field(min_length=1)
    existing_evidence: list[ExistingEvidence] = Field(min_length=1)
    status: Literal["met", "partially_met", "not_met", "unknown"]
    assessment: Finding
    gaps: list[ThresholdGap]
    dependencies: list[ContextDependency] = Field(min_length=1)
    continue_if: OutcomeRule
    revise_if: OutcomeRule
    stop_if: OutcomeRule


class ThresholdAnalysis(StrictOutput):
    summary: Text
    position: Literal["thresholds_met", "conditional", "material_barriers", "insufficient_data"]
    claims: list[ThresholdClaim]
    gates: list[InvestmentGate] = Field(min_length=2)
    risks: list[Risk]
    unknowns: list[Text]
    change_conditions: list[Text] = Field(min_length=1)
    limitations: list[Text]


def _walk(value):
    if isinstance(value, BaseModel):
        yield value
        for key in type(value).model_fields:
            yield from _walk(getattr(value, key))
    elif isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}")


def _validate_claims(claims, case, pack, *, upstream=False):
    _unique([c.id for c in claims], "claim IDs")
    evidence = {e.id: e for e in pack.evidence}
    for claim in claims:
        if not set(claim.evidence_ids) <= evidence.keys():
            raise ValueError("Unknown evidence ID")
        if case.scope == "approach" and claim.scope == "program":
            raise ValueError("Program claim cannot expand approach scope")
        if claim.support_status in ("supported", "mixed", "contradicted"):
            if not claim.evidence_ids:
                raise ValueError("Factual claim requires evidence")
            if claim.scope == "program" and not any(evidence[e].scope == "program" for e in claim.evidence_ids):
                raise ValueError("Program fact requires program evidence")
        elif not upstream and not claim.assumptions:
            raise ValueError("Unknown/unverified claim requires assumptions or gaps")


def prepare_threshold_inputs(case: CaseInput, pack: EvidencePack, ctx: RunContext, *,
        science: RoleResult | dict | None = None, translation: RoleResult | dict | None = None,
        clinical: RoleResult | dict | None = None, market: RoleResult | dict | None = None,
        partnerships: RoleResult | dict | None = None, investment: RoleResult | dict | None = None,
        ip_licensing: RoleResult | dict | None = None) -> dict:
    assert_pack(pack)
    if ctx.snapshot_id is not None and ctx.snapshot_id != pack.snapshot_id:
        raise ValueError("Context and pack snapshots differ")
    context_date = date.fromisoformat(ctx.as_of_date) if isinstance(ctx.as_of_date, str) else ctx.as_of_date
    if context_date is not None and not isinstance(context_date, date):
        raise ValueError("Context as_of_date must be a date or ISO date string")
    if context_date and case.as_of_date and context_date != case.as_of_date:
        raise ValueError("Case and context dates differ")
    as_of = context_date or case.as_of_date
    context = {}
    supplied = dict(science=science, translation=translation, clinical=clinical, market=market,
                    partnerships=partnerships, investment=investment, ip_licensing=ip_licensing)
    for role, raw in supplied.items():
        result = RoleResult.model_validate(raw) if raw is not None else None
        if result is not None:
            if result.role_id != role:
                raise ValueError(f"Expected {role} RoleResult")
            _validate_claims(result.claims, case, pack, upstream=True)
            known = {c.id for c in result.claims}
            _unique([r.id for r in result.risks], "upstream risk IDs")
            for block in [*result.risks, *result.section_content]:
                if not set(block.claim_ids) <= known:
                    raise ValueError("Upstream contains unknown claim references")
            # Validate metadata wherever it occurs, including saved plan provenance.
            for section in result.section_content:
                data = section.structured_data or {}
                metadata = data.get(role, data)
                if isinstance(metadata, dict) and as_of and "as_of_date" in metadata and metadata["as_of_date"] != as_of.isoformat():
                    raise ValueError("Upstream date differs")
                for block in _walk(section.structured_data):
                    if isinstance(block, dict):
                        if "snapshot_id" in block and block["snapshot_id"] != pack.snapshot_id:
                            raise ValueError("Upstream snapshot differs")
                        # Historical analogue dates are not run metadata.
                        if "evidence_ids" in block and (not isinstance(block["evidence_ids"], list) or
                                any(not isinstance(ref, str) or ref not in {e.id for e in pack.evidence}
                                    for ref in block["evidence_ids"])):
                            raise ValueError("Upstream contains unknown nested evidence_ids")
            context[role] = result.model_dump(mode="json")
        else:
            context[role] = None
    sources = {s.id: s for s in pack.sources}
    return dict(prompt_version=PROMPT_VERSION, case=case.model_dump(mode="json"),
        snapshot_id=pack.snapshot_id, as_of_date=as_of.isoformat() if as_of else None,
        sources=[s.model_dump(mode="json") for s in pack.sources],
        evidence=[e.model_dump(mode="json") | {"synthetic": sources[e.source_id].synthetic} for e in pack.evidence],
        synthetic=pack.synthetic or any(s.synthetic for s in pack.sources) or any(
            isinstance(block, dict) and block.get("synthetic") is True for block in _walk(context)),
        retrieval_warnings=list(pack.retrieval_warnings), upstream_context=context,
        context_availability={k: v is not None for k, v in context.items()})


def validate_threshold_result(analysis: ThresholdAnalysis, case: CaseInput,
                              pack: EvidencePack, payload: dict) -> None:
    _validate_claims(analysis.claims, case, pack)
    claims = {c.id: c for c in analysis.claims}
    evidence = {e.id: e for e in pack.evidence}
    for block in _walk(analysis):
        if hasattr(block, "claim_ids") and not set(block.claim_ids) <= claims.keys():
            raise ValueError("Unknown local claim reference")
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
                if block.basis == "hypothesis" and (not block.assumptions or any(
                        c.support_status not in ("unverified", "unknown") for c in linked)):
                    raise ValueError("Hypothesis requires assumptions and unverified/unknown claims")
        if isinstance(block, ContextDependency):
            raw = payload["upstream_context"][block.role_id]
            upstream = RoleResult.model_validate(raw) if raw is not None else None
            upstream_claims = {c.id: c for c in upstream.claims} if upstream else {}
            records = {b["id"] for s in upstream.section_content for b in _walk(s.structured_data)
                       if isinstance(b, dict) and isinstance(b.get("id"), str)} if upstream else set()
            if not set(block.upstream_claim_ids) <= upstream_claims.keys() or not set(block.record_ids) <= records:
                raise ValueError("Unknown upstream claim/record reference")
            if upstream is None and block.assessment.basis != "unknown":
                raise ValueError("Absent upstream requires unknown assessment")
            if block.assessment.basis == "documented" and (not block.upstream_claim_ids or any(
                    upstream_claims[c].support_status != "supported" for c in block.upstream_claim_ids)):
                raise ValueError("Documented dependency requires supported upstream claims")
    _unique([g.id for g in analysis.gates], "gate IDs")
    _unique([r.id for r in analysis.risks], "risk IDs")
    _unique([c.id for g in analysis.gates for c in g.criteria], "criterion IDs")
    _unique([gap.id for g in analysis.gates for gap in g.gaps], "gap IDs")
    if any(not r.id.startswith("investment_threshold.") or not r.claim_ids for r in analysis.risks):
        raise ValueError("Threshold risks require namespace and local claims")
    if {g.horizon for g in analysis.gates} != {"now", "next_stage"}:
        raise ValueError("Assess both now and next_stage")
    if {d.role_id for g in analysis.gates for d in g.dependencies} != set(ROLES):
        raise ValueError("Assess every upstream role, including absent context")
    for gate in analysis.gates:
        criteria = {c.id for c in gate.criteria}
        _unique([d.role_id for d in gate.dependencies], "gate dependencies")
        _unique([e.criterion_id for e in gate.existing_evidence], "criterion evidence assessments")
        if {e.criterion_id for e in gate.existing_evidence} != criteria:
            raise ValueError("Assess existing evidence for every criterion exactly once")
        for row in gate.existing_evidence:
            if not set(row.evidence_ids) <= evidence.keys():
                raise ValueError("Unknown existing evidence ID")
            linked = {eid for cid in row.finding.claim_ids for eid in claims[cid].evidence_ids}
            if not set(row.evidence_ids) <= linked:
                raise ValueError("Existing evidence must be linked by its finding claims")
            if row.finding.basis == "documented" and not row.evidence_ids:
                raise ValueError("Documented existing evidence requires evidence IDs")
        covered = set()
        for gap in gate.gaps:
            if not set(gap.criterion_ids) <= criteria:
                raise ValueError("Gap references wrong gate criterion")
            covered.update(gap.criterion_ids)
        unresolved = {r.criterion_id for r in gate.existing_evidence if r.finding.basis != "documented"}
        if not unresolved <= covered:
            raise ValueError("Every unverified criterion requires an actionable gap")
        if gate.status == "met":
            if gate.gaps or gate.assessment.basis != "documented" or unresolved or any(
                    f.basis == "unknown" for f in (gate.required_result, gate.obtainable_stage)) or any(
                    c.sufficient_result.basis == "unknown" or c.rationale.basis == "unknown" for c in gate.criteria):
                raise ValueError("Met gate requires complete documented evidence and no gaps")
            if any(d.assessment.basis != "documented" for d in gate.dependencies):
                raise ValueError("Met gate requires documented dependencies")
        elif not gate.gaps:
            raise ValueError("Unmet or unknown gate requires actionable gaps")
        if gate.status in ("partially_met", "not_met") and gate.assessment.basis != "documented":
            raise ValueError("Observed shortfall requires documented assessment; missing data is unknown")
        if gate.status == "unknown" and gate.assessment.basis != "unknown":
            raise ValueError("Unknown gate requires unknown assessment")
    if analysis.position == "thresholds_met" and any(g.status != "met" for g in analysis.gates):
        raise ValueError("Thresholds met requires all gates met")
    if analysis.position == "material_barriers" and not any(g.status == "not_met" for g in analysis.gates):
        raise ValueError("Material barriers requires an evidenced unmet gate")
    if all(g.status == "unknown" for g in analysis.gates) and analysis.position != "insufficient_data":
        raise ValueError("All unknown gates require insufficient_data")
    if not pack.evidence and analysis.position != "insufficient_data":
        raise ValueError("Empty evidence requires insufficient_data")


def identify_threshold_gaps(analysis: ThresholdAnalysis) -> list[str]:
    gaps = list(analysis.unknowns)
    for block in _walk(analysis):
        if isinstance(block, Finding):
            gaps.extend(block.unknowns)
        if isinstance(block, ThresholdGap):
            gaps.append(f"{block.id}: {block.missing_result_or_data}; evidence needed: {block.check.evidence_needed}")
    gaps.extend(f"Requires verification: {c.id}: {c.text}" for c in analysis.claims
                if c.support_status in ("unknown", "unverified"))
    return list(dict.fromkeys(gaps))


async def analyze_investment_threshold(case: CaseInput, pack: EvidencePack, ctx: RunContext, *,
        science: RoleResult | dict | None = None, translation: RoleResult | dict | None = None,
        clinical: RoleResult | dict | None = None, market: RoleResult | dict | None = None,
        partnerships: RoleResult | dict | None = None, investment: RoleResult | dict | None = None,
        ip_licensing: RoleResult | dict | None = None) -> RoleResult:
    payload = prepare_threshold_inputs(case, pack, ctx, science=science, translation=translation,
        clinical=clinical, market=market, partnerships=partnerships, investment=investment, ip_licensing=ip_licensing)
    if ctx.model is None or not callable(getattr(ctx.model, "generate_structured", None)):
        raise RuntimeError("R2 model adapter with generate_structured is required")
    raw = await ctx.model.generate_structured(PROMPT_ID, payload, ThresholdAnalysis, ctx)
    analysis = ThresholdAnalysis.model_validate(raw)
    validate_threshold_result(analysis, case, pack, payload)
    gaps = identify_threshold_gaps(analysis)
    for role, available in payload["context_availability"].items():
        if not available:
            gaps.append(f"{role} context absent; upstream alignment remains pending.")
        else:
            gaps.extend(f"{role}: {gap}" for gap in payload["upstream_context"][role]["unknowns"])
    if payload["as_of_date"] is None:
        gaps.append("As-of date absent; temporal applicability remains pending.")
    limitations = list(dict.fromkeys([*analysis.limitations, *pack.retrieval_warnings,
        "Structural checks do not establish semantic sufficiency; R3 evidence audit and R4 scientific review remain required.",
        "Investment thresholds do not establish investment return or a final committee recommendation."]))
    data = analysis.model_dump(mode="json", exclude={"claims", "risks"})
    data.update(prompt_version=PROMPT_VERSION, snapshot_id=pack.snapshot_id,
        as_of_date=payload["as_of_date"], synthetic=payload["synthetic"],
        context_availability=payload["context_availability"], source_requests=list(dict.fromkeys(gaps)),
        upstream_context=payload["upstream_context"],
        claim_evidence_links={c.id: c.evidence_ids for c in analysis.claims},
        evidence_source_links={e.id: e.source_id for e in pack.evidence})
    return RoleResult(role_id=PROMPT_ID, summary=analysis.summary, position=analysis.position,
        claims=[Claim.model_validate(c.model_dump()) for c in analysis.claims], risks=analysis.risks,
        unknowns=data["source_requests"], change_conditions=analysis.change_conditions,
        section_content=[SectionContent(key="diligence_questions", summary=analysis.summary,
            claim_ids=[c.id for c in analysis.claims], limitations=limitations,
            structured_data={PROMPT_ID: data})])
