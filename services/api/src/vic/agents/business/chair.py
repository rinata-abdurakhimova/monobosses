from dataclasses import replace
"""Evidence-weighted committee synthesis. Pipeline wiring belongs to R2."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from vic.contracts import (
    AuditResult,
    CaseInput,
    Claim,
    CommitteeDecision,
    DiligenceQuestion,
    Disagreement,
    EvidencePack,
    Risk,
    RoleResult,
    RunContext,
    SectionContent,
)
from vic.integrity import assert_pack

PROMPT_ID = "chair"
PROMPT_VERSION = "1.0.0"
ROLES = ("science", "translation", "clinical", "market", "investment", "partnerships",
         "ip_licensing", "investment_threshold", "failure_miner")
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
Role = Literal["science", "translation", "clinical", "market", "investment", "partnerships",
               "ip_licensing", "investment_threshold", "failure_miner"]
Recommendation = Literal["Invest", "Conditional", "Do Not Invest"]


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ChairClaim(Claim):
    id: str = Field(max_length=128, pattern=r"^chair\.[a-z][a-z0-9_]*$")


class Reason(StrictOutput):
    text: Text
    basis: Literal["documented", "hypothesis", "unknown"]
    claim_ids: list[str]
    assumptions: list[Text]
    unknowns: list[Text]
    evidence_weight: Text


class Argument(StrictOutput):
    id: Identifier
    direction: Literal["for", "against"]
    reason: Reason
    decision_impact: Text
    decisive: bool


class Condition(StrictOutput):
    id: Identifier
    requirement: Text
    rationale: Reason
    verification_method: Text
    evidence_needed: Text
    pass_if: Text
    fail_if: Text
    inconclusive_if: Text
    timing: Literal["before_investment", "before_next_tranche"]
    failure_action: Text


class Conflict(StrictOutput):
    id: Identifier
    topic: Text
    role_ids: list[Role] = Field(min_length=2)
    upstream_claim_ids: list[str] = Field(min_length=2)
    competing_conclusions: Text
    resolution: Reason
    decision_impact: Text
    status: Literal["resolved", "unresolved"]


class DecisionRisk(StrictOutput):
    id: Identifier
    description: Reason
    priority: Literal["critical", "major", "minor"]
    impact: Text
    next_check: Text


class CriticalUnknown(StrictOutput):
    id: Identifier
    description: Text
    role_ids: list[Role] = Field(min_length=1)
    decision_impact: Text
    blocks_invest: bool


class ChangeTrigger(StrictOutput):
    id: Identifier
    result_or_new_evidence: Text
    verification_method: Text
    rationale: Reason
    resulting_recommendation: Recommendation


class FinalQuestion(StrictOutput):
    id: Identifier
    rank: int = Field(ge=1, le=10)
    role_ids: list[Role] = Field(min_length=1)
    argument_ids: list[Identifier]
    risk_ids: list[Identifier]
    unknown_ids: list[Identifier]
    condition_ids: list[Identifier]
    conflict_ids: list[Identifier]
    question: Text
    why_it_matters: Reason
    evidence_needed: Text
    method: Text
    decision_if_positive: Text
    decision_if_negative: Text
    inconclusive_if: Text


class InputDisposition(StrictOutput):
    item_id: Text
    disposition: Literal["considered", "deferred"]
    rationale: Text
    argument_ids: list[Identifier]
    question_ids: list[Identifier]
    condition_ids: list[Identifier]


class DomainReview(StrictOutput):
    role_id: Role
    assessment: Reason
    dispositions: list[InputDisposition]


class ChairAnalysis(StrictOutput):
    summary: Text
    recommendation: Recommendation
    rationale: Reason
    claims: list[ChairClaim]
    arguments: list[Argument] = Field(min_length=2)
    conditions: list[Condition]
    conflicts: list[Conflict]
    conflict_limitations: list[Text]
    key_risks: list[DecisionRisk]
    critical_unknowns: list[CriticalUnknown]
    change_triggers: list[ChangeTrigger] = Field(min_length=1)
    questions: list[FinalQuestion] = Field(min_length=5, max_length=10)
    domain_reviews: list[DomainReview] = Field(min_length=9, max_length=9)
    unknowns: list[Text]
    limitations: list[Text]


class ChairResult(StrictOutput):
    """Both outputs derive from the same validated analysis; neither loses detail."""
    decision: CommitteeDecision
    role_result: RoleResult


def _walk(value, path=""):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from _walk(child, f"{path}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}/{index}")


def _unique(values, label):
    if len(values) != len(set(values)):
        raise ValueError(f"Duplicate {label}")


def _claims_valid(claims, case, pack):
    _unique([c.id for c in claims], "claim IDs")
    evidence = {e.id: e for e in pack.evidence}
    for c in claims:
        _unique(c.evidence_ids, "claim evidence")
        if not set(c.evidence_ids) <= evidence.keys():
            raise ValueError("Unknown evidence ID")
        if case.scope == "approach" and c.scope == "program":
            raise ValueError("Program claim expands approach scope")
        if c.scope == "program" and c.support_status in ("supported", "mixed", "contradicted") and not any(
                evidence[e].scope == "program" for e in c.evidence_ids):
            raise ValueError("Program fact requires program evidence")


def _inventory(role, raw):
    items = [{"id": f"{role}/{field}", "kind": field} for field in ("summary", "position")]
    for field in ("claims", "risks", "unknowns", "change_conditions", "section_content"):
        for i, value in enumerate(raw[field]):
            items.append({"id": f"{role}/{field}/{i}", "kind": field, "value": value})
    # Include identified records, nested gaps, and candidate questions without truncation.
    def own_records(value):
        if isinstance(value, dict):
            return {key: own_records(child) for key, child in value.items() if key not in {
                "upstream_context", "sources", "evidence", "claim_evidence_links", "evidence_source_links"}}
        if isinstance(value, list):
            return [own_records(child) for child in value]
        return value
    sections = [{**section, "structured_data": own_records(section.get("structured_data") or {})}
                for section in raw["section_content"]]
    for path, block in _walk(sections, "/section_content"):
        if "id" in block or "question" in block:
            items.append({"id": f"{role}{path}", "kind": "record", "value": block})
        for field in ("unknowns", "limitations", "source_requests"):
            if isinstance(block.get(field), list):
                for i, value in enumerate(block[field]):
                    items.append({"id": f"{role}{path}/{field}/{i}", "kind": field, "value": value})
    # A section can itself be an identified record: deduplicate by stable input path.
    return [{"id": item["id"], "kind": item["kind"]} for item in {item["id"]: item for item in items}.values()]


def prepare_chair_inputs(case: CaseInput, pack: EvidencePack, ctx: RunContext, *,
        science: RoleResult | dict | None = None, translation: RoleResult | dict | None = None,
        clinical: RoleResult | dict | None = None, market: RoleResult | dict | None = None,
        investment: RoleResult | dict | None = None, partnerships: RoleResult | dict | None = None,
        ip_licensing: RoleResult | dict | None = None, investment_threshold: RoleResult | dict | None = None,
        failure_miner: RoleResult | dict | None = None,
        audit: AuditResult | dict | None = None) -> dict:
    assert_pack(pack)
    if ctx.snapshot_id is not None and ctx.snapshot_id != pack.snapshot_id:
        raise ValueError("Context and pack snapshots differ")
    as_of = date.fromisoformat(ctx.as_of_date) if isinstance(ctx.as_of_date, str) else ctx.as_of_date
    if as_of is not None and not isinstance(as_of, date):
        raise ValueError("Invalid context date")
    if as_of and case.as_of_date and as_of != case.as_of_date:
        raise ValueError("Case and context dates differ")
    as_of = as_of or case.as_of_date
    supplied = {"science": science, "translation": translation, "clinical": clinical, "market": market,
        "investment": investment, "partnerships": partnerships, "ip_licensing": ip_licensing,
        "investment_threshold": investment_threshold, "failure_miner": failure_miner}
    context, inventory = {}, {}
    all_claims, all_risks = [], []
    for role, value in supplied.items():
        if value is None:
            context[role], inventory[role] = None, []
            continue
        result = RoleResult.model_validate(value.model_dump(mode="json") if isinstance(value, RoleResult) else value)
        if result.role_id != role:
            raise ValueError(f"Expected {role} RoleResult")
        _claims_valid(result.claims, case, pack)
        known = {c.id for c in result.claims}
        for block in [*result.risks, *result.section_content]:
            if not set(block.claim_ids) <= known:
                raise ValueError("Unknown upstream claim reference")
        all_claims.extend(result.claims)
        all_risks.extend(result.risks)
        raw = result.model_dump(mode="json")
        for _, block in _walk(raw):
            if "snapshot_id" in block and block["snapshot_id"] != pack.snapshot_id:
                raise ValueError("Upstream snapshot differs")
            if "evidence_ids" in block and (not isinstance(block["evidence_ids"], list) or
                    any(not isinstance(e, str) or e not in {e.id for e in pack.evidence} for e in block["evidence_ids"])):
                raise ValueError("Unknown nested evidence reference")
        for section in result.section_content:
            metadata = (section.structured_data or {}).get(role, section.structured_data or {})
            if isinstance(metadata, dict) and as_of and "as_of_date" in metadata and metadata["as_of_date"] != as_of.isoformat():
                raise ValueError("Upstream date differs")
        context[role], inventory[role] = raw, _inventory(role, raw)
    _unique([c.id for c in all_claims], "global upstream claim IDs")
    _unique([r.id for r in all_risks], "global upstream risk IDs")
    audited = AuditResult.model_validate(audit) if audit is not None else None
    known = {c.id for c in all_claims}
    if audited:
        if not set(audited.unresolved_critical_claim_ids) <= known:
            raise ValueError("Unknown unresolved audit claim")
        for finding in audited.findings:
            if finding.claim_id not in known or not set(finding.evidence_ids) <= {e.id for e in pack.evidence}:
                raise ValueError("Unknown audit reference")
    return {"prompt_version": PROMPT_VERSION, "case": case.model_dump(mode="json"),
        "snapshot_id": pack.snapshot_id, "as_of_date": as_of.isoformat() if as_of else None,
        "sources": [s.model_dump(mode="json") for s in pack.sources],
        "evidence": [e.model_dump(mode="json") for e in pack.evidence],
        "synthetic": pack.synthetic or any(s.synthetic for s in pack.sources) or any(
            block.get("synthetic") is True for _, block in _walk(context)),
        "retrieval_warnings": list(pack.retrieval_warnings), "upstream_context": context,
        "context_availability": {r: value is not None for r, value in context.items()},
        "input_inventory": inventory, "audit": audited.model_dump(mode="json") if audited else None}


def validate_chair_result(analysis: ChairAnalysis, case: CaseInput, pack: EvidencePack, payload: dict):
    _claims_valid(analysis.claims, case, pack)
    claims = {c["id"]: Claim.model_validate(c) for raw in payload["upstream_context"].values()
              if raw for c in raw["claims"]}
    if set(claims) & {c.id for c in analysis.claims}:
        raise ValueError("Chair claim collides with upstream")
    claims.update({c.id: c for c in analysis.claims})
    for c in analysis.claims:
        if c.support_status in ("unknown", "unverified") and not c.assumptions:
            raise ValueError("Unverified chair claim requires assumptions")
    audit = payload["audit"]
    blocked = set(audit["unresolved_critical_claim_ids"]) if audit else set()
    verdicts = {}
    if audit:
        for f in audit["findings"]:
            verdicts.setdefault(f["claim_id"], []).append(f["verdict"])
            if f["blocking"]:
                blocked.add(f["claim_id"])
    for _, block in _walk(analysis.model_dump(mode="json")):
        if "basis" not in block:
            continue
        reason = Reason.model_validate(block)
        _unique(reason.claim_ids, "reason claim references")
        if not set(reason.claim_ids) <= claims.keys():
            raise ValueError("Unknown reason claim reference")
        if reason.basis == "unknown":
            if reason.claim_ids or not reason.unknowns:
                raise ValueError("Unknown reason requires explicit gaps and no factual claims")
        elif reason.basis == "documented":
            if not reason.claim_ids or any(claims[c].support_status != "supported" or c in blocked or
                    any(v != "supported" for v in verdicts.get(c, [])) for c in reason.claim_ids):
                raise ValueError("Documented reason requires supported, unblocked evidence")
        elif not reason.assumptions:
            raise ValueError("Hypothesis requires assumptions")
    collections = {"argument_ids": analysis.arguments, "condition_ids": analysis.conditions,
        "conflict_ids": analysis.conflicts, "risk_ids": analysis.key_risks,
        "unknown_ids": analysis.critical_unknowns, "question_ids": analysis.questions}
    ids = {}
    for name, rows in collections.items():
        _unique([row.id for row in rows], name)
        ids[name] = {row.id for row in rows}
    _unique([r.id for r in analysis.change_triggers], "change triggers")
    for _, block in _walk(analysis.model_dump(mode="json")):
        for name, known in ids.items():
            if name in block:
                _unique(block[name], name)
                if not set(block[name]) <= known:
                    raise ValueError(f"Unknown {name}")
        if "role_ids" in block:
            _unique(block["role_ids"], "role references")
    if {a.direction for a in analysis.arguments} != {"for", "against"}:
        raise ValueError("Provide arguments for and against, including unknown evidence")
    if not any(a.decisive for a in analysis.arguments):
        raise ValueError("Identify decisive arguments")
    if analysis.recommendation == "Conditional" and not analysis.conditions:
        raise ValueError("Conditional requires verifiable conditions")
    if analysis.recommendation != "Conditional" and analysis.conditions:
        raise ValueError("Funding conditions require Conditional recommendation")
    if not analysis.conflicts and not analysis.conflict_limitations:
        raise ValueError("Explain absence of established conflicts")
    for conflict in analysis.conflicts:
        _unique(conflict.upstream_claim_ids, "conflict claims")
        for role in conflict.role_ids:
            raw = payload["upstream_context"][role]
            if not raw or not set(conflict.upstream_claim_ids) & {c["id"] for c in raw["claims"]}:
                raise ValueError("Conflict requires claims from each supplied role")
        allowed = {c["id"] for r in conflict.role_ids for c in payload["upstream_context"][r]["claims"]}
        if not set(conflict.upstream_claim_ids) <= allowed:
            raise ValueError("Unknown conflict claim")
    _unique([q.question.casefold() for q in analysis.questions], "question texts")
    if sorted(q.rank for q in analysis.questions) != list(range(1, len(analysis.questions) + 1)):
        raise ValueError("Question ranks must be consecutive")
    for q in analysis.questions:
        if not any((q.argument_ids, q.risk_ids, q.unknown_ids, q.condition_ids, q.conflict_ids)):
            raise ValueError("Question requires a decision link")
    for name, rows in (("risk_ids", analysis.key_risks), ("unknown_ids", analysis.critical_unknowns),
                       ("condition_ids", analysis.conditions), ("conflict_ids", analysis.conflicts)):
        required = {r.id for r in rows if name == "condition_ids" or
                    (name == "risk_ids" and r.priority == "critical") or
                    (name == "unknown_ids" and r.blocks_invest) or
                    (name == "conflict_ids" and r.status == "unresolved")}
        covered = {ref for q in analysis.questions for ref in getattr(q, name)}
        if not required <= covered:
            raise ValueError(f"Questions must cover decision-critical {name}")
    _unique([r.role_id for r in analysis.domain_reviews], "domain reviews")
    if {r.role_id for r in analysis.domain_reviews} != set(ROLES):
        raise ValueError("Review all nine domains")
    for review in analysis.domain_reviews:
        expected = {i["id"] for i in payload["input_inventory"][review.role_id]}
        _unique([d.item_id for d in review.dispositions], "input dispositions")
        if {d.item_id for d in review.dispositions} != expected:
            raise ValueError("Every input item requires an explicit disposition")
        if payload["upstream_context"][review.role_id] is None and review.assessment.basis != "unknown":
            raise ValueError("Absent domain requires unknown assessment")
        for d in review.dispositions:
            if d.disposition == "considered" and not (d.argument_ids or d.question_ids or d.condition_ids):
                raise ValueError("Considered input requires a decision link")
            if d.disposition == "deferred" and (d.argument_ids or d.question_ids or d.condition_ids):
                raise ValueError("Deferred input cannot have decision links")
    if analysis.recommendation == "Invest":
        if any(c.importance == "critical" and c.support_status != "supported" for c in claims.values()):
            raise ValueError("Invest cannot rest on unresolved critical claims, including new chair claims")
        decisive_ids = {cid for a in analysis.arguments if a.decisive for cid in a.reason.claim_ids}
        decisive_ids.update(analysis.rationale.claim_ids)
        if any(cid not in verdicts for cid in decisive_ids if cid not in {c.id for c in analysis.claims}):
            raise ValueError("Invest requires audit coverage of decisive upstream claims")
        if any(c.importance == "critical" and (c.support_status != "supported" or c.id not in verdicts)
               for cid, c in claims.items() if cid not in {c.id for c in analysis.claims}):
            raise ValueError("Invest cannot bypass unresolved or unaudited critical upstream claims")
        if (not pack.evidence or not audit or blocked or not all(payload["context_availability"].values()) or
                payload["as_of_date"] is None or any(u.blocks_invest for u in analysis.critical_unknowns) or
                any(c.status == "unresolved" for c in analysis.conflicts) or
                any(r.assessment.basis == "unknown" for r in analysis.domain_reviews)):
            raise ValueError("Invest requires complete, audited evidence without unresolved blockers")
        if analysis.rationale.basis != "documented" or not any(
                a.direction == "for" and a.decisive and a.reason.basis == "documented" for a in analysis.arguments):
            raise ValueError("Invest requires decisive documented support")
    if analysis.recommendation == "Do Not Invest" and (analysis.rationale.basis != "documented" or not any(
            a.direction == "against" and a.decisive and a.reason.basis == "documented" for a in analysis.arguments)):
        raise ValueError("Do Not Invest requires an evidenced decisive adverse result; absence is unknown")
    upstream_risk_ids = {r["id"] for raw in payload["upstream_context"].values() if raw for r in raw["risks"]}
    if {f"chair.{r.id}" for r in analysis.key_risks} & upstream_risk_ids:
        raise ValueError("Chair risk collides with upstream")
    if any(t.resulting_recommendation == analysis.recommendation for t in analysis.change_triggers):
        raise ValueError("Change trigger must change recommendation")


async def analyze_chair(case: CaseInput, pack: EvidencePack, ctx: RunContext, *,
        science: RoleResult | dict | None = None, translation: RoleResult | dict | None = None,
        clinical: RoleResult | dict | None = None, market: RoleResult | dict | None = None,
        investment: RoleResult | dict | None = None, partnerships: RoleResult | dict | None = None,
        ip_licensing: RoleResult | dict | None = None, investment_threshold: RoleResult | dict | None = None,
        failure_miner: RoleResult | dict | None = None,
        audit: AuditResult | dict | None = None) -> ChairResult:
    payload = prepare_chair_inputs(case, pack, ctx, science=science, translation=translation,
        clinical=clinical, market=market, investment=investment, partnerships=partnerships,
        ip_licensing=ip_licensing, investment_threshold=investment_threshold,
        failure_miner=failure_miner, audit=audit)
    if ctx.model is None or not callable(getattr(ctx.model, "generate_structured", None)):
        raise RuntimeError("R2 generate_structured adapter required")
    analysis = ChairAnalysis.model_validate(await ctx.model.generate_structured(PROMPT_ID, payload, ChairAnalysis, ctx))
    try:
        validate_chair_result(analysis, case, pack, payload)
    except ValueError as exc:
        child = replace(ctx, feedback={**ctx.feedback, 'chair': [*ctx.feedback.get('chair', []),
            'Correct this Chair validation error without inventing evidence: ' + str(exc)]})
        analysis = ChairAnalysis.model_validate(await ctx.model.generate_structured(PROMPT_ID, payload, ChairAnalysis, child))
        validate_chair_result(analysis, case, pack, payload)
    questions = [DiligenceQuestion(question=q.question, why_it_matters=q.why_it_matters.text,
        evidence_needed=q.evidence_needed, decision_if_positive=q.decision_if_positive,
        decision_if_negative=q.decision_if_negative) for q in sorted(analysis.questions, key=lambda q: q.rank)]
    risks = [Risk(id=f"chair.{r.id}", description=r.description.text, priority=r.priority,
        claim_ids=r.description.claim_ids, impact=r.impact, next_check=r.next_check) for r in analysis.key_risks]
    conditions = [f"{c.requirement} [{c.timing}] Verify: {c.verification_method}; evidence: {c.evidence_needed}; "
        f"pass: {c.pass_if}; fail: {c.fail_if}; inconclusive: {c.inconclusive_if}; action: {c.failure_action}" for c in analysis.conditions]
    decision = CommitteeDecision(recommendation=analysis.recommendation, rationale=analysis.rationale.text,
        conditions=conditions, disagreements=[Disagreement(topic=c.topic, role_ids=c.role_ids,
            summary=c.competing_conclusions, resolution=f"[{c.status}] {c.resolution.text}; {c.decision_impact}") for c in analysis.conflicts],
        risks=risks, questions=questions, additional_claims=[Claim.model_validate(c.model_dump()) for c in analysis.claims])
    gaps = [*analysis.unknowns, *(u.description for u in analysis.critical_unknowns)]
    for _, block in _walk(analysis.model_dump(mode="json")):
        if "basis" in block:
            gaps.extend(block["unknowns"])
    for role, raw in payload["upstream_context"].items():
        if raw is None:
            gaps.append(f"{role}: upstream context absent")
        else:
            for _, block in _walk(raw):
                for field in ("unknowns", "source_requests"):
                    if isinstance(block.get(field), list):
                        gaps.extend(f"{role}: {gap}" for gap in block[field] if isinstance(gap, str) and gap.strip())
    if payload["audit"] is None:
        gaps.append("R3 audit absent; evidence strength not independently checked")
    if payload["as_of_date"] is None:
        gaps.append("As-of date absent; temporal applicability requires verification")
    if payload["audit"]:
        gaps.extend(f"Audit blocking claim: {c}" for c in payload["audit"]["unresolved_critical_claim_ids"])
        gaps.extend(f"Audit finding {f['claim_id']}: {f['reason']}" for f in payload["audit"]["findings"]
                    if f["blocking"] or f["verdict"] != "supported")
        gaps.extend(f"Audit warning: {w}" for w in payload["audit"]["warnings"])
    data = analysis.model_dump(mode="json", exclude={"claims"})
    data.update({k: payload[k] for k in ("prompt_version", "snapshot_id", "as_of_date", "synthetic",
        "upstream_context", "context_availability", "input_inventory", "audit", "retrieval_warnings")})
    data.update(source_requests=list(dict.fromkeys(gaps)), committee_decision=decision.model_dump(mode="json"),
        claim_evidence_links={c["id"]: c["evidence_ids"] for raw in payload["upstream_context"].values() if raw for c in raw["claims"]} |
            {c.id: c.evidence_ids for c in analysis.claims},
        evidence_source_links={e.id: e.source_id for e in pack.evidence},
        evidence=[e.model_dump(mode="json") for e in pack.evidence], sources=payload["sources"])
    # Section references only local claims: shared RoleResult validators expect that.
    role = RoleResult(role_id="chair", summary=analysis.summary, position=analysis.recommendation,
        claims=decision.additional_claims, risks=[], unknowns=data["source_requests"],
        change_conditions=[f"{t.result_or_new_evidence} -> {t.resulting_recommendation}; {t.verification_method}; {t.rationale.text}"
            for t in analysis.change_triggers], section_content=[SectionContent(key="recommendation", summary=analysis.summary,
                claim_ids=[c.id for c in analysis.claims], limitations=list(dict.fromkeys([*analysis.limitations,
                    *pack.retrieval_warnings, "Structural validation does not prove truth or scientific/financial sufficiency."])),
                structured_data={"chair": data})])
    return ChairResult(decision=decision, role_result=role)
