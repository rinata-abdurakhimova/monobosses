"""Critical opponent: evidence-linked failure chains and risk interactions."""
from pathlib import Path
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from vic.contracts import CaseInput, Claim, EvidencePack, Risk, RoleResult, RunContext, SectionContent
from vic.integrity import assert_pack

PROMPT_ID = "failure_miner"
PROMPT_VERSION = "1.0.0"
PROMPT_PATH = Path(__file__).parent / "prompts" / "failure_miner.md"
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
UpstreamRole = Literal["science", "translation", "clinical", "market", "investment", "partnerships", "ip_licensing", "investment_threshold"]
ROLES = UpstreamRole.__args__


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FailureClaim(Claim):
    id: str = Field(max_length=128, pattern=r"^failure_miner\.[a-z][a-z0-9_]*$")


class Finding(StrictOutput):
    value: Text | None
    basis: Literal["documented", "hypothesis", "unknown"]
    claim_ids: list[str]
    assumptions: list[Text]
    unknowns: list[Text]


class Origin(StrictOutput):
    role_id: UpstreamRole
    upstream_claim_ids: list[str]
    upstream_risk_ids: list[str]
    record_ids: list[str]


class FailureCheck(StrictOutput):
    question: Text
    method: Text
    evidence_needed: Text
    uncertainty_reduced: Text
    decision_if_positive: Text
    decision_if_negative: Text
    inconclusive_if: Text


class FailureMode(StrictOutput):
    id: Identifier
    domains: list[UpstreamRole] = Field(min_length=1)
    origins: list[Origin]
    problem: Finding
    affected: Finding
    consequence: Finding
    investment_impact: Finding
    priority: Literal["critical", "major", "minor"]
    priority_rationale: Finding
    next_check: FailureCheck


class RiskDisposition(StrictOutput):
    upstream_risk_id: str
    disposition: Literal["included", "deferred"]
    failure_ids: list[Identifier]
    rationale: Text


class DomainReview(StrictOutput):
    role_id: UpstreamRole
    assessment: Finding
    failure_ids: list[Identifier]
    risk_dispositions: list[RiskDisposition]
    next_check: Text


class RiskInteraction(StrictOutput):
    id: Identifier
    from_failure_id: Identifier
    to_failure_id: Identifier
    relationship: Literal["causes", "amplifies", "shared_dependency"]
    mechanism: Finding
    investment_impact: Finding
    next_check: FailureCheck


class DiligencePriority(StrictOutput):
    id: Identifier
    rank: int = Field(ge=1)
    failure_ids: list[Identifier] = Field(min_length=1)
    interaction_ids: list[Identifier]
    priority: Literal["critical", "major", "minor"]
    rationale: Finding
    check: FailureCheck


class FailureAnalysis(StrictOutput):
    summary: Text
    position: Literal["material_risks", "conditional", "insufficient_data"]
    claims: list[FailureClaim]
    failure_modes: list[FailureMode] = Field(min_length=1)
    domain_reviews: list[DomainReview] = Field(min_length=8, max_length=8)
    interactions: list[RiskInteraction]
    interaction_limitations: list[Text]
    diligence_priorities: list[DiligencePriority] = Field(min_length=1)
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


def prepare_failure_inputs(case: CaseInput, pack: EvidencePack, ctx: RunContext, *,
        science: RoleResult | dict | None = None, translation: RoleResult | dict | None = None,
        clinical: RoleResult | dict | None = None, market: RoleResult | dict | None = None,
        partnerships: RoleResult | dict | None = None, investment: RoleResult | dict | None = None,
        ip_licensing: RoleResult | dict | None = None,
        investment_threshold: RoleResult | dict | None = None) -> dict:
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
                    partnerships=partnerships, investment=investment, ip_licensing=ip_licensing, investment_threshold=investment_threshold)
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



def validate_failure_result(analysis: FailureAnalysis, case: CaseInput,
                            pack: EvidencePack, payload: dict) -> None:
    """Reject dangling links, evidence laundering, dropped risks and incomplete chains."""
    _validate_claims(analysis.claims, case, pack)
    claims = {c.id: c for c in analysis.claims}
    failures = {f.id: f for f in analysis.failure_modes}
    interactions = {i.id: i for i in analysis.interactions}
    for rows, label in ((analysis.failure_modes, "failure IDs"), (analysis.interactions, "interaction IDs"),
                        (analysis.diligence_priorities, "question IDs")):
        _unique([r.id for r in rows], label)
    for block in _walk(analysis):
        if isinstance(block, Finding):
            _unique(block.claim_ids, "finding claim references")
            if not set(block.claim_ids) <= claims.keys():
                raise ValueError("Unknown local claim reference")
            linked = [claims[c] for c in block.claim_ids]
            if block.basis == "unknown":
                if block.value is not None or not block.unknowns or block.claim_ids:
                    raise ValueError("Unknown finding requires null, gaps and no factual claims")
            elif block.value is None or not linked:
                raise ValueError("Finding requires value and local claims")
            elif block.basis == "documented" and any(c.support_status != "supported" for c in linked):
                raise ValueError("Documented finding requires supported evidence-linked claims")
            elif block.basis == "hypothesis" and (not block.assumptions or any(
                    c.support_status not in ("unverified", "unknown") for c in linked)):
                raise ValueError("Hypothesis requires assumptions and unverified/unknown claims")
    upstream = {r: RoleResult.model_validate(raw) if raw is not None else None
                for r, raw in payload["upstream_context"].items()}
    for failure in analysis.failure_modes:
        _unique(failure.domains, "failure domains")
        _unique([o.role_id for o in failure.origins], "failure origins")
        for origin in failure.origins:
            if origin.role_id not in failure.domains:
                raise ValueError("Origin role must be an affected domain")
            result = upstream[origin.role_id]
            known_claims = {c.id for c in result.claims} if result else set()
            known_risks = {r.id for r in result.risks} if result else set()
            records = {b['id'] for s in result.section_content for b in _walk(s.structured_data)
                       if isinstance(b, dict) and isinstance(b.get('id'), str)} if result else set()
            for refs, known in ((origin.upstream_claim_ids, known_claims),
                                (origin.upstream_risk_ids, known_risks), (origin.record_ids, records)):
                _unique(refs, "origin references")
                if not set(refs) <= known:
                    raise ValueError("Unknown upstream origin reference")
            if result is None or not (origin.upstream_claim_ids or origin.upstream_risk_ids or origin.record_ids):
                raise ValueError("Origin requires supplied upstream references")
    _unique([r.role_id for r in analysis.domain_reviews], "domain reviews")
    if {r.role_id for r in analysis.domain_reviews} != set(ROLES):
        raise ValueError("Review every upstream domain exactly once")
    for review in analysis.domain_reviews:
        _unique(review.failure_ids, "domain failure references")
        if not set(review.failure_ids) <= failures.keys():
            raise ValueError("Unknown domain failure reference")
        expected = {f.id for f in analysis.failure_modes if review.role_id in f.domains}
        if set(review.failure_ids) != expected:
            raise ValueError("Domain review must include all its failure modes")
        result = upstream[review.role_id]
        if result is None and review.assessment.basis != "unknown":
            raise ValueError("Absent upstream requires unknown assessment")
        risks = {r.id for r in result.risks} if result else set()
        _unique([d.upstream_risk_id for d in review.risk_dispositions], "risk dispositions")
        if {d.upstream_risk_id for d in review.risk_dispositions} != risks:
            raise ValueError("Every upstream risk needs an explicit disposition")
        for disposition in review.risk_dispositions:
            _unique(disposition.failure_ids, "disposition failure references")
            if not set(disposition.failure_ids) <= set(review.failure_ids):
                raise ValueError("Disposition references wrong domain failure")
            if disposition.disposition == "included":
                if not disposition.failure_ids:
                    raise ValueError("Included risk requires a failure chain")
                for fid in disposition.failure_ids:
                    if not any(o.role_id == review.role_id and disposition.upstream_risk_id in o.upstream_risk_ids
                               for o in failures[fid].origins):
                        raise ValueError("Included risk requires matching origin")
            elif disposition.failure_ids:
                raise ValueError("Deferred risk cannot have failure links")
        for failure in analysis.failure_modes:
            for origin in failure.origins:
                if origin.role_id == review.role_id:
                    for rid in origin.upstream_risk_ids:
                        if not any(d.upstream_risk_id == rid and failure.id in d.failure_ids
                                   for d in review.risk_dispositions):
                            raise ValueError("Origin risk must have matching included disposition")
    pairs = []
    for interaction in analysis.interactions:
        if interaction.from_failure_id not in failures or interaction.to_failure_id not in failures:
            raise ValueError("Unknown interaction endpoint")
        if interaction.from_failure_id == interaction.to_failure_id:
            raise ValueError("Self interaction is not a cross-risk relationship")
        pairs.append((interaction.from_failure_id, interaction.to_failure_id, interaction.relationship))
    _unique(pairs, "interaction relationships")
    if not analysis.interactions and not analysis.interaction_limitations:
        raise ValueError("Explain why no risk interactions can be established")
    ranks = [q.rank for q in analysis.diligence_priorities]
    if sorted(ranks) != list(range(1, len(ranks) + 1)):
        raise ValueError("Question ranks must be unique and consecutive")
    weights = {"critical": 0, "major": 1, "minor": 2}
    ordered = sorted(analysis.diligence_priorities, key=lambda q: q.rank)
    if [weights[q.priority] for q in ordered] != sorted(weights[q.priority] for q in ordered):
        raise ValueError("Critical questions must precede lower priority questions")
    covered = set()
    for question in analysis.diligence_priorities:
        _unique(question.failure_ids, "question failure references")
        _unique(question.interaction_ids, "question interaction references")
        if not set(question.failure_ids) <= failures.keys() or not set(question.interaction_ids) <= interactions.keys():
            raise ValueError("Unknown question reference")
        covered.update(question.failure_ids)
        for iid in question.interaction_ids:
            interaction = interactions[iid]
            if not {interaction.from_failure_id, interaction.to_failure_id} <= set(question.failure_ids):
                raise ValueError("Interaction question must cover both endpoints")
    if not failures.keys() <= covered:
        raise ValueError("Every failure needs a prioritized uncertainty-reducing check")
    if analysis.position == "material_risks" and not any(
            f.problem.basis == "documented" and f.priority in ("critical", "major")
            for f in analysis.failure_modes):
        raise ValueError("Material risks requires an evidenced material problem")
    if (not pack.evidence or all(f.problem.basis == "unknown" for f in analysis.failure_modes)) and analysis.position != "insufficient_data":
        raise ValueError("Missing evidence is insufficient data, not an observed failure")


def identify_failure_gaps(analysis: FailureAnalysis) -> list[str]:
    gaps = list(analysis.unknowns)
    for block in _walk(analysis):
        if isinstance(block, Finding):
            gaps.extend(block.unknowns)
    gaps.extend(f"Requires verification: {c.id}: {c.text}" for c in analysis.claims
                if c.support_status in ("unknown", "unverified"))
    for question in sorted(analysis.diligence_priorities, key=lambda q: q.rank):
        gaps.append(f"Check {question.rank} ({question.id}): {question.check.question}; evidence needed: {question.check.evidence_needed}")
    return list(dict.fromkeys(gaps))


async def analyze_failure_miner(case: CaseInput, pack: EvidencePack, ctx: RunContext, *,
        science: RoleResult | dict | None = None, translation: RoleResult | dict | None = None,
        clinical: RoleResult | dict | None = None, market: RoleResult | dict | None = None,
        partnerships: RoleResult | dict | None = None, investment: RoleResult | dict | None = None,
        ip_licensing: RoleResult | dict | None = None,
        investment_threshold: RoleResult | dict | None = None) -> RoleResult:
    payload = prepare_failure_inputs(case, pack, ctx, science=science, translation=translation,
        clinical=clinical, market=market, partnerships=partnerships, investment=investment,
        ip_licensing=ip_licensing, investment_threshold=investment_threshold)
    if ctx.model is None or not callable(getattr(ctx.model, "generate_structured", None)):
        raise RuntimeError("R2 model adapter with generate_structured is required")
    raw = await ctx.model.generate_structured(PROMPT_ID, payload, FailureAnalysis, ctx)
    analysis = FailureAnalysis.model_validate(raw)
    validate_failure_result(analysis, case, pack, payload)
    gaps = identify_failure_gaps(analysis)
    for role, result in payload["upstream_context"].items():
        if result is None:
            gaps.append(f"{role} context absent; obtain upstream review.")
        else:
            # Nested financial/scientific unknowns must also remain visible to consumers.
            for block in _walk(result):
                if isinstance(block, dict) and isinstance(block.get("unknowns"), list):
                    gaps.extend(f"{role}: {gap}" for gap in block["unknowns"] if isinstance(gap, str) and gap.strip())
    if payload["as_of_date"] is None:
        gaps.append("As-of date absent; temporal applicability remains pending.")
    limitations = list(dict.fromkeys([*analysis.limitations, *pack.retrieval_warnings,
        "Structural checks do not prove causal mechanisms or factual truth; R3 audit and specialist review are required.",
        "Possible failure scenarios are not observed failures or a final committee recommendation."]))
    risks = []
    for failure in analysis.failure_modes:
        local_ids = list(dict.fromkeys(cid for finding in (failure.problem, failure.affected,
            failure.consequence, failure.investment_impact, failure.priority_rationale) for cid in finding.claim_ids))
        impact = failure.investment_impact.value or "; ".join(failure.investment_impact.unknowns)
        description = failure.problem.value or "; ".join(failure.problem.unknowns)
        risks.append(Risk(id=f"failure_miner.{failure.id}", description=f"[{failure.problem.basis}] {description}",
            priority=failure.priority, claim_ids=local_ids, impact=f"[{failure.investment_impact.basis}] {impact}",
            next_check=f"{failure.next_check.question} Method: {failure.next_check.method}; evidence: {failure.next_check.evidence_needed}"))
    data = analysis.model_dump(mode="json", exclude={"claims"})
    data.update(prompt_version=PROMPT_VERSION, snapshot_id=pack.snapshot_id,
        as_of_date=payload["as_of_date"], synthetic=payload["synthetic"],
        context_availability=payload["context_availability"], upstream_context=payload["upstream_context"],
        source_requests=list(dict.fromkeys(gaps)),
        claim_evidence_links={c.id: c.evidence_ids for c in analysis.claims},
        evidence_source_links={e.id: e.source_id for e in pack.evidence})
    return RoleResult(role_id=PROMPT_ID, summary=analysis.summary, position=analysis.position,
        claims=[Claim.model_validate(c.model_dump()) for c in analysis.claims], risks=risks,
        unknowns=data["source_requests"], change_conditions=analysis.change_conditions,
        section_content=[SectionContent(key="key_risks", summary=analysis.summary,
            claim_ids=[c.id for c in analysis.claims], limitations=limitations,
            structured_data={PROMPT_ID: data})])
