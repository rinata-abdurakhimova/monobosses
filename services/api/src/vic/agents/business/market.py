"""R5-01 market node. Parallel task-specific calls through the shared R2 adapter."""
import asyncio
import hashlib
import json
import re
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
from vic.failures import RunFailure
from vic.llm import request_sizes, structured_request

from .calculations import MarketScenario, estimate_market_scenarios, summarize_market_ranges

PROMPT_ID = "market"
PROMPT_VERSION = "2.1.0"
PROMPT_PATH = Path(__file__).parent / "prompts" / "market.md"
Category = Literal["standard_of_care", "approved", "clinical_stage", "same_target", "alternative_mechanism", "discontinued"]


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketClaim(StrictOutput):
    id: str = Field(pattern=r"^market\.[a-z][a-z0-9_]*$")
    text: str = Field(min_length=1)
    support_status: Literal["supported", "contradicted", "mixed", "unverified", "unknown"]
    evidence_ids: list[str]
    assumptions: list[str]
    scope: Literal["approach", "program"]
    importance: Literal["critical", "major", "minor"]


class Competitor(StrictOutput):
    name: str = Field(min_length=1)
    # Tags overlap: same-target can also be approved; status is separate.
    categories: list[Category] = Field(min_length=1)
    development_status: Literal["approved", "clinical_stage", "preclinical", "discontinued", "unknown"]
    discontinuation_reason: str | None = Field(min_length=1)
    discontinuation_reason_claim_ids: list[str]
    discontinuation_unknowns: list[str]
    claim_ids: list[str] = Field(min_length=1)


class CoverageFinding(StrictOutput):
    status: Literal["documented", "insufficient_data"]
    claim_ids: list[str]
    unknowns: list[str]


class PricingAnalogue(StrictOutput):
    name: str = Field(min_length=1)
    price_description: str | None = Field(min_length=1)
    geography: str | None = Field(min_length=1)
    as_of_date: str | None = Field(min_length=1)
    comparability: str = Field(min_length=1)
    limitations: list[str]
    claim_ids: list[str] = Field(min_length=1)
    unknowns: list[str]


class AccessAssessment(StrictOutput):
    reimbursement: list[str]
    prescribing: list[str]
    other_access: list[str]
    claim_ids: list[str]
    unknowns: list[str]


class CommercialValue(StrictOutput):
    assessment: Literal["potential_value", "limited_value", "mixed", "insufficient_data"]
    rationale: str = Field(min_length=1)
    unmet_need: str | None = Field(min_length=1)
    willingness_to_pay: str | None = Field(min_length=1)
    claim_ids: list[str]
    unknowns: list[str]


class MarketQuestion(StrictOutput):
    question: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    evidence_needed: str = Field(min_length=1)
    decision_if_positive: str = Field(min_length=1)
    decision_if_negative: str = Field(min_length=1)
    claim_ids: list[str]


class Differentiation(StrictOutput):
    comparator: str = Field(min_length=1)
    dimension: Literal["benefit", "safety", "access", "administration", "other"]
    assessment: str = Field(min_length=1)
    claim_ids: list[str] = Field(min_length=1)


class MarketRisk(StrictOutput):
    id: str = Field(pattern=r"^market\.risk\.[a-z0-9_.]+$")
    description: str
    priority: Literal["critical", "major", "minor"]
    claim_ids: list[str]
    impact: str
    next_check: str


class TargetPopulation(StrictOutput):
    """Patients who may benefit, not customers of the underwriting application.

    Missing facts remain null; all nonempty descriptions reference claims.
    Clinical suitability must be checked against R4 outputs during integration.
    """
    description: str | None = Field(min_length=1)
    indication: str | None = Field(min_length=1)
    eligibility: list[str]
    geography: str | None = Field(min_length=1)
    access_limitations: list[str]
    claim_ids: list[str]
    unknowns: list[str]


class MarketAnalysis(StrictOutput):
    summary: str = Field(min_length=1)
    commercial_summary: str = Field(min_length=1)
    position: Literal["favorable", "mixed", "unfavorable", "insufficient_data"]
    claims: list[MarketClaim]
    competitors: list[Competitor]
    target_population: TargetPopulation
    competitive_coverage: dict[Category, CoverageFinding]
    pricing_analogues: list[PricingAnalogue]
    pricing_unknowns: list[str]
    access: AccessAssessment
    commercial_value: CommercialValue
    diligence_questions: list[MarketQuestion] = Field(min_length=1)
    differentiation: list[Differentiation]
    risks: list[MarketRisk]
    unknowns: list[str]
    change_conditions: list[str]
    limitations: list[str]



class PassAnalysis(StrictOutput):
    summary: str = Field(min_length=1)
    position: Literal["favorable", "mixed", "unfavorable", "insufficient_data"]
    claims: list[MarketClaim]
    risks: list[MarketRisk]
    unknowns: list[str]
    change_conditions: list[str]
    limitations: list[str]
    diligence_questions: list[MarketQuestion] = Field(min_length=1)


class CompetitiveAnalysis(PassAnalysis):
    competitors: list[Competitor]
    competitive_coverage: dict[Category, CoverageFinding]
    differentiation: list[Differentiation]


class CommercialAnalysis(PassAnalysis):
    target_population: TargetPopulation
    pricing_analogues: list[PricingAnalogue]
    pricing_unknowns: list[str]
    access: AccessAssessment
    commercial_value: CommercialValue


PASS_MODELS = {"market_competitive": CompetitiveAnalysis, "market_commercial": CommercialAnalysis}
DEFAULT_REQUEST_MAX_BYTES = 18000
# Initial requests use 75% of the configured cap to leave space for repairs.
INITIAL_BUDGET_FRACTION = 0.75


def project_clinical_context(clinical: RoleResult | None, task: str) -> dict | None:
    """Use R4's stable claim keys; never copy nested role results/report sections.

    Unknown/custom critical claims are retained in both passes conservatively.
    All clinical risks/unknowns survive, since their relevance cannot be inferred
    safely from free text alone. R4 context is not independently verified evidence.
    """
    if clinical is None:
        return None
    common = {"clinical.target_population", "clinical.unmet_need",
              "clinical.safety_requirements", "clinical.standard_of_care",
              "clinical.comparator_choice", "clinical.biomarker_strategy",
              "clinical.regulatory_precedent"}
    competitive = common | {"clinical.primary_endpoint", "clinical.secondary_endpoints"}
    wanted = competitive if task == "market_competitive" else common
    known_other = {"clinical.biomarker_strategy", "clinical.trial_size_basis",
                   "clinical.study_sequence", "clinical.regulatory_precedent",
                   "clinical.next_milestone", "clinical.primary_endpoint",
                   "clinical.secondary_endpoints"}
    risk_claims = {cid for risk in clinical.risks for cid in risk.claim_ids}
    selected = [c for c in clinical.claims if c.id in risk_claims or c.id in wanted
                or c.importance == "critical" or c.id not in known_other]
    fields = {"target_population": "clinical.target_population",
              "comparator": "clinical.comparator_choice", "standard_of_care": "clinical.standard_of_care",
              "unmet_need": "clinical.unmet_need", "biomarker_strategy": "clinical.biomarker_strategy",
              "regulatory_context": "clinical.regulatory_precedent",
              "science_gaps_carried_forward": "clinical.science_gaps_carried_forward"}
    # Carry unclaimed section facts as explicitly unverified context, not new evidence.
    unclaimed = []
    ids = {c.id for c in selected}
    for section in clinical.section_content:
        data = section.structured_data or {}
        for field, cid in fields.items():
            if field in data and cid not in ids:
                unclaimed.append({"field": field, "value": data[field],
                                  "claim_ids": [cid for cid in section.claim_ids if cid in ids],
                                  "support_status": "unverified"})
    return {"claims": [c.model_dump(mode="json") for c in selected],
            "unclaimed_context": unclaimed,
            "risks": [r.model_dump(mode="json") for r in clinical.risks],
            "unknowns": clinical.unknowns, "change_conditions": clinical.change_conditions,
            "limitations": list(dict.fromkeys(x for section in clinical.section_content
                                               for x in section.limitations)),
            "excluded_claim_ids": [c.id for c in clinical.claims if c not in selected],
            "exclusion_reason": "Clinical development planning; not needed by this Market task"}


def _unique(items):
    seen = set()
    result = []
    for item in items:
        key = json.dumps(item.model_dump(mode="json") if isinstance(item, BaseModel) else item,
                         sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _join(values):
    return "\n".join(_unique([v for v in values if v])) or None


def _position(values):
    """Unknown coverage wins over positivity; unanimous negatives remain negative."""
    values = set(values)
    if values == {"unfavorable"}:
        return "unfavorable"
    if "insufficient_data" in values:
        return "insufficient_data"
    return "favorable" if values == {"favorable"} else "mixed"


def _pass_context(ctx, task):
    # Independent containers avoid concurrent changes to shared audit feedback.
    feedback = dict(ctx.feedback)
    # A canonical deduplicated claim may support both sections. Forward every
    # market finding to both passes conservatively instead of dropping feedback
    # based on the namespace of the first producer. Normalize merged IDs to local
    # semantic keys so a repair does not namespace them twice.
    findings = []
    for finding in ctx.feedback.get("market", []):
        cid = getattr(finding, "claim_id", None)
        if cid:
            for prefix in ("market.competitive_", "market.commercial_"):
                if cid.startswith(prefix):
                    local = re.sub(r"_[0-9a-f]{12}$", "", cid.removeprefix(prefix))
                    finding = finding.model_copy(update={"claim_id": "market." + local})
                    break
        findings.append(finding)
    feedback["market"] = findings
    return replace(ctx, feedback=feedback)


def prepare_pass_inputs(payload, clinical, task, evidence):
    """Preserve exact excerpts, deduplicating source metadata by original source ID.

    Free-text evidence has no reliable task labels. Both tasks review all supplied
    records in bounded batches; no lexical filter can silently drop contradictions.
    Only task-specific R4 context and numeric scenarios are projected.
    """
    source_keys = ("source_title", "source_type", "published_at", "synthetic")
    sources = {e["source_id"]: {k: e[k] for k in source_keys} for e in evidence}
    records = [{k: v for k, v in e.items() if k not in source_keys} for e in evidence]
    return {"prompt_version": PROMPT_VERSION, "case": payload["case"],
            "sources": sources, "evidence": records,
            "retrieval_warnings": payload["retrieval_warnings"],
            "clinical_input": project_clinical_context(clinical, task),
            "clinical_alignment": payload["clinical_alignment"],
            "calculated_scenarios": payload["calculated_scenarios"] if task == "market_commercial" else [],
            "coverage": {"policy": "All supplied evidence reviewed; no free-text relevance exclusions",
                         "partial_batch": True, "total_evidence_count": len(payload["evidence"])}}


def plan_market_batches(payload, clinical, task, ctx, *, audit_batch_id=None):
    feedback = [item.model_dump(mode="json") if isinstance(item, BaseModel) else item
                for item in ctx.feedback.get("market", [])]
    if feedback and audit_batch_id is None:
        # Fit exact findings against the complete envelope, including the largest
        # indivisible Clinical record and evidence. A fixed feedback size cannot
        # account for their variable sizes or the serialized schema overhead.
        try:
            return _plan_market_batches(payload, clinical, task, ctx)
        except RunFailure as exc:
            if exc.code != "market_request_budget":
                raise

        def plan_group(group):
            child = replace(ctx, feedback={**ctx.feedback, "market": group})
            identity = hashlib.sha256(json.dumps(group, sort_keys=True).encode()).hexdigest()[:12]
            try:
                planned = _plan_market_batches(payload, clinical, task, child,
                                               audit_batch_id=identity)
            except RunFailure as exc:
                if exc.code != "market_request_budget" or len(group) == 1:
                    raise
                midpoint = len(group) // 2
                return [*plan_group(group[:midpoint]), *plan_group(group[midpoint:])]
            for batch in planned:
                batch["_market_audit_feedback"] = group
            return planned

        return plan_group(feedback)
    return _plan_market_batches(payload, clinical, task, ctx, audit_batch_id=audit_batch_id)


def _plan_market_batches(payload, clinical, task, ctx, *, audit_batch_id=None):
    model = PASS_MODELS[task]
    cap = getattr(ctx.model, "market_request_budget", DEFAULT_REQUEST_MAX_BYTES)
    initial_cap = int(cap * INITIAL_BUDGET_FRACTION)
    full_context = project_clinical_context(clinical, task)
    def make(records, context=full_context, context_ids=None):
        data = prepare_pass_inputs(payload, clinical, task, records)
        data["clinical_input"] = context
        if audit_batch_id:
            data["coverage"]["audit_feedback_batch_id"] = audit_batch_id
        if context_ids is not None:
            data["coverage"].update(partial_clinical_context=True,
                                    clinical_context_ids=context_ids)
        return data
    def measure(data):
        measure_adapter = getattr(ctx.model, "structured_request_size", None)
        if callable(measure_adapter):
            return measure_adapter(task, data, model, ctx)
        _, system, messages = structured_request(task, data, model, ctx)
        return request_sizes(system, messages)
    # Keep the original one-context path when it fits. Otherwise partition exact
    # clinical records, never summarize or truncate safety/unknown text.
    contexts = [(full_context, None)]
    largest_evidence = max(payload["evidence"], default=None, key=lambda e: len(
        json.dumps(e, ensure_ascii=False, default=str).encode("utf-8")))
    probe = [largest_evidence] if largest_evidence else []
    if full_context is not None and measure(make(probe))["request_bytes"] > initial_cap:
        record_fields = {"claims", "risks", "unclaimed_context", "unknowns",
                         "change_conditions", "limitations"}
        header = {key: value for key, value in full_context.items() if key not in record_fields}
        def empty_context():
            return {**header, **{key: [] for key in record_fields}}
        if measure(make(probe, empty_context(), []))["request_bytes"] > initial_cap:
            raise RunFailure("Market schema/case/audit context or one exact excerpt exceeds "
                             "the initial byte budget", code="market_request_budget")
        contexts, current, ids = [], empty_context(), []
        for field in sorted(record_fields):
            for item in full_context.get(field, []):
                identity = item.get("id") if isinstance(item, dict) else None
                identity = identity or hashlib.sha256(json.dumps(item, sort_keys=True,
                    ensure_ascii=False, default=str).encode("utf-8")).hexdigest()[:12]
                record_id = f"{field}:{identity}"
                candidate = {**current, field: [*current[field], item]}
                if measure(make(probe, candidate, [*ids, record_id]))["request_bytes"] > initial_cap:
                    if ids:
                        contexts.append((current, ids))
                    current, ids = empty_context(), []
                    candidate = {**current, field: [item]}
                    if measure(make(probe, candidate, [record_id]))["request_bytes"] > initial_cap:
                        raise RunFailure("One exact Clinical context record exceeds the initial "
                                         "Market byte budget", code="market_request_budget")
                current, ids = candidate, [*ids, record_id]
        if ids:
            contexts.append((current, ids))
    if measure(make([], contexts[0][0], contexts[0][1]))["request_bytes"] > initial_cap:
        raise RunFailure("Market schema/case/clinical/audit context exceeds the initial byte budget; "
                         "reduce the context before calling the model", code="market_request_budget")
    batches = []
    for context, context_ids in contexts:
        current = []
        for evidence in payload["evidence"]:
            if measure(make([*current, evidence], context, context_ids))["request_bytes"] > initial_cap:
                if current:
                    batches.append(make(current, context, context_ids))
                    current = []
                if measure(make([evidence], context, context_ids))["request_bytes"] > initial_cap:
                    raise RunFailure("One exact Market excerpt exceeds the initial byte budget; "
                                     "request a smaller provenance-preserving evidence unit from R3",
                                     code="market_request_budget")
            current.append(evidence)
        if current or not payload["evidence"]:
            batches.append(make(current, context, context_ids))
    for batch in batches:
        batch["coverage"]["partial_batch"] = len(batches) > 1
        sizes = measure(batch)
        if sizes["request_bytes"] > initial_cap:
            raise RunFailure("Market batch exceeds initial byte budget", code="market_request_budget")
        parts = {f"{key}_bytes": len(json.dumps(batch[key], ensure_ascii=False, default=str,
                    separators=(",", ":")).encode("utf-8"))
                 for key in ("case", "evidence", "sources", "clinical_input", "calculated_scenarios")}
        ctx.trace.log(RunStage.ANALYZE, f"{task} planned {sizes}; parts={parts}; initial_budget_bytes={initial_cap}; "
                      f"evidence_ids={[e['id'] for e in batch['evidence']]}")
    return batches


def namespace_pass(result, task, context_ids=None, evidence_ids=None):
    """Stable task/key/evidence/context IDs, independent of batch number and Market text.

    Same key and evidence with different contents is a collision, never overwrite.
    Distinct evidence supporting contradictory facts retains separate claims.
    """
    data = result.model_dump(mode="json")
    prefix = "competitive" if task == "market_competitive" else "commercial"
    mapping, claims = {}, {}
    for claim in data["claims"]:
        old = claim["id"]
        if old in claims and claims[old] != claim:
            raise ValueError("Conflicting claim ID within Market pass")
        claims[old] = claim
        identity = sorted(set(claim["evidence_ids"]))
        if context_ids is not None:
            identity = [identity, sorted(context_ids)]
        digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:12]
        mapping[old] = f"market.{prefix}_{old.removeprefix('market.')}_{digest}"
    def walk(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if k in ("claim_ids", "discontinuation_reason_claim_ids"):
                    if not set(v) <= mapping.keys():
                        raise ValueError("Unknown claim reference in Market pass")
                    value[k] = list(dict.fromkeys(mapping[cid] for cid in v))
                else:
                    walk(v)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(data)
    for claim in data["claims"]:
        claim["id"] = mapping[claim["id"]]
    for risk in data["risks"]:
        identity = sorted(risk["claim_ids"])
        if context_ids is not None:
            identity = [identity, sorted(context_ids), sorted(evidence_ids or [])]
        digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:12]
        risk["id"] = f"market.risk.{prefix}_{risk['id'].removeprefix('market.risk.')}_{digest}"
    data["claims"] = _unique(data["claims"])
    return type(result).model_validate(data)


def _merge_identified(items):
    out = {}
    for item in items:
        if item.id in out and out[item.id] != item:
            raise ValueError(f"Conflicting Market ID: {item.id}")
        out[item.id] = item
    return list(out.values())


def merge_market_results(competitive, commercial):
    """Deterministic union; preserve conflicting descriptions and flag review.

    No model synthesis, majority vote, invented numbers or unquoted conclusions.
    Missing batch data cannot erase known facts, nor prove global absence.
    """
    passes = [*competitive, *commercial]
    canonical, aliases = {}, {}
    for part in passes:
        for claim in part.claims:
            fact = claim.model_dump(mode="json", exclude={"id"})
            key = json.dumps(fact, sort_keys=True)
            aliases[claim.id] = canonical.setdefault(key, claim.id)
    def remap(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ("claim_ids", "discontinuation_reason_claim_ids"):
                    value[key] = _unique([aliases[cid] for cid in child])
                else:
                    remap(child)
        elif isinstance(value, list):
            for child in value:
                remap(child)
    normalized = []
    for part in passes:
        data = part.model_dump(mode="json")
        remap(data)
        for claim in data["claims"]:
            claim["id"] = aliases[claim["id"]]
        normalized.append(type(part).model_validate(data))
    competitive, commercial = normalized[:len(competitive)], normalized[len(competitive):]
    passes = normalized
    common = {k: _unique([v for part in passes for v in getattr(part, k)])
              for k in ("unknowns", "change_conditions", "limitations", "diligence_questions")}
    claims = _merge_identified([c for part in passes for c in part.claims])
    identified_risks = _merge_identified([r for part in passes for r in part.risks])
    seen_risks, risks = set(), []
    for risk in identified_risks:
        key = json.dumps(risk.model_dump(mode="json", exclude={"id"}), sort_keys=True)
        if key not in seen_risks:
            seen_risks.add(key)
            risks.append(risk)
    coverage = {}
    for category in Category.__args__:
        findings = [p.competitive_coverage[category] for p in competitive]
        coverage[category] = CoverageFinding(
            status="documented" if any(f.status == "documented" for f in findings) else "insufficient_data",
            claim_ids=_unique([cid for f in findings for cid in f.claim_ids]),
            unknowns=_unique([u for f in findings for u in f.unknowns]))
    population = {}
    conflicts = []
    for field in TargetPopulation.model_fields:
        values = [getattr(p.target_population, field) for p in commercial]
        if field in ("description", "indication", "geography"):
            unique = _unique([v for v in values if v is not None])
            population[field] = _join(unique)
            if len(unique) > 1:
                conflicts.append(f"Target population {field} differs across batches; reconcile original claims.")
        else:
            population[field] = _unique([item for value in values for item in value])
    access = AccessAssessment(**{k: _unique([item for p in commercial for item in getattr(p.access, k)])
                                for k in AccessAssessment.model_fields})
    values = [p.commercial_value for p in commercial]
    assessments = {v.assessment for v in values}
    value_data = {"assessment": next(iter(assessments)) if len(assessments) == 1 else "mixed",
                  "rationale": _join([v.rationale for v in values])}
    for field in ("unmet_need", "willingness_to_pay"):
        distinct = _unique([getattr(v, field) for v in values if getattr(v, field) is not None])
        value_data[field] = _join(distinct)
        if len(distinct) > 1:
            conflicts.append(f"Commercial {field} differs across batches; reconcile original claims.")
    for field in ("claim_ids", "unknowns"):
        value_data[field] = _unique([item for v in values for item in getattr(v, field)])
    competitors = _unique([c for p in competitive for c in p.competitors])
    for name in {c.name for c in competitors}:
        if len({c.development_status for c in competitors if c.name == name}) > 1:
            conflicts.append(f"Conflicting development statuses for {name}; resolve dated evidence.")
    position = _position(p.position for p in passes)
    missing_coverage = any(f.status == "insufficient_data" for f in coverage.values())
    uncertain_claim = any(c.support_status in ("mixed", "contradicted", "unknown", "unverified")
                          and c.importance != "minor" for c in claims)
    if position == "favorable" and (missing_coverage or conflicts or uncertain_claim
            or value_data["assessment"] != "potential_value" or population["unknowns"]
            or access.unknowns or value_data["unknowns"] or common["unknowns"]
            or any(p.pricing_unknowns for p in commercial)):
        position = "insufficient_data" if missing_coverage else "mixed"
    common["unknowns"] = _unique([*common["unknowns"], *conflicts])
    return MarketAnalysis(summary=_join([p.summary for p in competitive]),
        commercial_summary=_join([p.summary for p in commercial]), position=position,
        claims=claims, risks=risks, competitors=competitors, competitive_coverage=coverage,
        differentiation=_unique([d for p in competitive for d in p.differentiation]),
        target_population=TargetPopulation(**population), access=access,
        commercial_value=CommercialValue(**value_data),
        pricing_analogues=_unique([a for p in commercial for a in p.pricing_analogues]),
        pricing_unknowns=_unique([u for p in commercial for u in p.pricing_unknowns]), **common)


async def run_market_pass(task, batches, ctx):
    results = []
    for batch in batches:
        call_ctx = ctx
        if "_market_audit_feedback" in batch:
            call_ctx = replace(ctx, feedback={**ctx.feedback, "market": batch["_market_audit_feedback"]})
            batch = {key: value for key, value in batch.items() if key != "_market_audit_feedback"}
        for attempt in range(2):
            raw = await ctx.model.generate_structured(task, batch, PASS_MODELS[task], call_ctx)
            result = raw if isinstance(raw, PASS_MODELS[task]) else PASS_MODELS[task].model_validate(raw)
            visible_ids = {e["id"] for e in batch["evidence"]}
            try:
                if any(not set(c.evidence_ids) <= visible_ids for c in result.claims):
                    raise ValueError("Market pass cited evidence outside its batch")
                if any(c.support_status in {"supported", "contradicted", "mixed"} and not c.evidence_ids
                       for c in result.claims):
                    raise ValueError("Supported/contradicted/mixed Market claims require supplied evidence IDs; context-only gaps must remain unknown/unverified")
                if isinstance(result, CompetitiveAnalysis):
                    if set(result.competitive_coverage) != set(Category.__args__):
                        raise ValueError("Market pass must cover all six competitor categories")
                    names = {c.name for c in result.competitors}
                    if any(d.comparator not in names for d in result.differentiation):
                        raise ValueError("Differentiation must reference a listed comparator; "
                                         "use an empty differentiation list when no comparator is known")
                context_ids = batch["coverage"].get("clinical_context_ids")
                if batch["coverage"].get("audit_feedback_batch_id"):
                    context_ids = [*(context_ids or []), "audit:" + batch["coverage"]["audit_feedback_batch_id"]]
                normalized = namespace_pass(result, task, context_ids, visible_ids)
            except ValueError as exc:
                if attempt:
                    raise
                # Fresh corrective request avoids replaying a large invalid output.
                # All original evidence/context and existing audit feedback survive.
                feedback = {**call_ctx.feedback, "market": [*call_ctx.feedback.get("market", []), str(exc)]}
                call_ctx = replace(ctx, feedback=feedback)
                ctx.trace.log(RunStage.ANALYZE, f"{task} bounded reference repair")
            else:
                results.append(normalized)
                break
    return results


async def run_market_passes(tasks):
    """Cancel/await the sibling on failure; never leave paid calls running orphaned."""
    pending = [asyncio.create_task(task) for task in tasks]
    try:
        return await asyncio.gather(*pending)
    except BaseException:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        raise

def prepare_market_inputs(case: CaseInput, pack: EvidencePack,
                          scenarios: list[MarketScenario] | None = None,
                          clinical: RoleResult | None = None) -> dict:
    """Keep full supplied excerpts and provenance; avoid losing safety context.

    No retrieval is done here. Scenario numbers are caller supplied, never LLM
    generated. R3/R2 control corpus size, historical availability and retrieval.
    """
    if case.scope not in ("approach", "program"):
        raise ValueError("Invalid case scope")
    if clinical is not None:
        if clinical.role_id != "clinical":
            raise ValueError("Clinical input must be a clinical RoleResult")
        # Explicit upstream result, no agent calls here. Its evidence must be in
        # the same snapshot; R4 eligibility is context, not automatic truth.
        if any(not set(c.evidence_ids) <= {e.id for e in pack.evidence}
               for c in clinical.claims):
            raise ValueError("Clinical input requires evidence from the supplied pack")
    sources = {s.id: s for s in pack.sources}
    ids = {e.id for e in pack.evidence}
    if len(sources) != len(pack.sources) or len(ids) != len(pack.evidence):
        raise ValueError("Duplicate source/evidence IDs")
    evidence = []
    for e in pack.evidence:
        if e.source_id not in sources:
            raise ValueError(f"Evidence {e.id} has no source")
        if e.scope not in ("approach", "program"):
            raise ValueError("Invalid evidence scope")
        s = sources[e.source_id]
        evidence.append({"id": e.id, "source_id": e.source_id, "excerpt": e.excerpt,
                         "scope": e.scope, "locator": e.locator, "limitations": e.limitations,
                         "source_title": s.title, "source_type": s.type,
                         "published_at": s.published_at, "synthetic": s.synthetic})
    for scenario in scenarios or []:
        date.fromisoformat(scenario.as_of_date)
        for key in ("population", "eligible_fraction", "access_fraction", "annual_price"):
            links = scenario.input_evidence_ids.get(key, [])
            if getattr(scenario, key) is not None and (not links or not set(links) <= ids):
                raise ValueError(f"Scenario input {key} requires valid evidence IDs")
        if any(not set(links) <= ids for links in scenario.input_evidence_ids.values()):
            raise ValueError("Unknown scenario evidence ID")
    return {"prompt_version": PROMPT_VERSION,
            "case": {k: getattr(case, k, None) for k in
                     ("indication", "mechanism", "scope", "modality", "development_stage", "program_data", "as_of_date")},
            "evidence": evidence, "retrieval_warnings": pack.retrieval_warnings,
            "clinical_input": project_clinical_context(clinical, "market_commercial"),
            "clinical_alignment": "R4 input supplied; reconcile eligibility" if clinical else "R4 review pending",
            "calculated_scenarios": estimate_market_scenarios(scenarios or [])}


def classify_competitors(analysis: MarketAnalysis) -> dict[str, list[dict]]:
    """Group model-extracted competitors by tags; never infer approval from name."""
    groups = {k: [] for k in ("standard_of_care", "approved", "clinical_stage", "same_target", "alternative_mechanism", "discontinued")}
    for c in analysis.competitors:
        for tag in dict.fromkeys(c.categories):
            groups[tag].append(c.model_dump())
    return groups


def assess_differentiation(analysis: MarketAnalysis) -> list[dict]:
    """Attach evidence and support labels to comparator-specific assessments."""
    claims = {c.id: c for c in analysis.claims}
    return [{**d.model_dump(),
             "evidence_ids": sorted({e for cid in d.claim_ids for e in claims[cid].evidence_ids}),
             "support_statuses": {cid: claims[cid].support_status for cid in d.claim_ids}}
            for d in analysis.differentiation]


def identify_market_gaps(analysis: MarketAnalysis, calculations: list[dict]) -> list[str]:
    """Combine reported unknowns and explicitly missing scenario inputs."""
    gaps = [*analysis.unknowns, *analysis.target_population.unknowns,
            *analysis.pricing_unknowns, *analysis.access.unknowns,
            *analysis.commercial_value.unknowns]
    for finding in analysis.competitive_coverage.values():
        gaps.extend(finding.unknowns)
    for competitor in analysis.competitors:
        gaps.extend(competitor.discontinuation_unknowns)
    for analogue in analysis.pricing_analogues:
        gaps.extend(analogue.unknowns)
    if not analysis.target_population.eligibility:
        gaps.append("Clinical eligibility is unknown; request R4 review.")
    if not analysis.target_population.indication:
        gaps.append("Target population indication is unknown.")
    if analysis.target_population.description is None:
        gaps.append("Target patient population is unknown; request population evidence from R3/R4.")
    if analysis.target_population.geography is None:
        gaps.append("Target geography is unknown; request geographic scope and access evidence.")
    if not calculations:
        gaps.append("No reviewed numeric inputs: market size and pricing remain unknown; request population, eligibility, access and pricing evidence from R3.")
    for result in calculations:
        for key in result["missing_inputs"]:
            gaps.append(f"{result['inputs']['name']}: missing {key}; request evidence from R3.")
    for c in analysis.claims:
        if c.support_status in ("unknown", "unverified"):
            gaps.append(f"Requires verification: {c.id}: {c.text}")
    return list(dict.fromkeys(gaps))


def validate_market_result(analysis: MarketAnalysis, case: CaseInput, pack: EvidencePack) -> None:
    """Reject broken links, scope escalation and contradictory status tags.

    This checks structure, not semantic truth. R3 must audit each excerpt's
    actual support before an investment decision is finalized.
    """
    if not pack.evidence and (analysis.position != "insufficient_data" or analysis.competitors or analysis.differentiation or analysis.pricing_analogues):
        raise ValueError("Empty evidence requires insufficient_data and no factual competitors")
    claims = {c.id: c for c in analysis.claims}
    if len(claims) != len(analysis.claims):
        raise ValueError("Duplicate claim IDs")
    evidence = {e.id: e for e in pack.evidence}
    for c in analysis.claims:
        if not set(c.evidence_ids) <= evidence.keys():
            raise ValueError(f"Unknown evidence ID in {c.id}")
        if case.scope == "approach" and c.scope == "program":
            raise ValueError("Program claim cannot expand approach scope")
        if c.support_status in ("supported", "contradicted", "mixed") and not c.evidence_ids:
            raise ValueError(f"Evidence required for {c.id}")
        if (c.scope == "program"
                and c.support_status in ("supported", "contradicted", "mixed")
                and not any(evidence[eid].scope == "program" for eid in c.evidence_ids)):
            raise ValueError("Program claim requires program evidence")
    population = analysis.target_population
    if not any((population.description, population.indication, population.eligibility, population.geography, population.access_limitations)) and not population.unknowns:
        raise ValueError("Unknown target population must explain missing data")
    if any((population.description, population.indication, population.eligibility, population.geography, population.access_limitations)) and not population.claim_ids:
        raise ValueError("Target population statements require claim references")
    for item in [population, analysis.access, analysis.commercial_value,
                 *analysis.competitive_coverage.values(), *analysis.pricing_analogues,
                 *analysis.diligence_questions, *analysis.competitors,
                 *analysis.differentiation, *analysis.risks]:
        if not set(item.claim_ids) <= claims.keys():
            raise ValueError("Unknown claim reference")
    if len({r.id for r in analysis.risks}) != len(analysis.risks):
        raise ValueError("Duplicate risk IDs")
    for c in analysis.competitors:
        for tag in ("approved", "clinical_stage", "discontinued"):
            if tag in c.categories and c.development_status != tag:
                raise ValueError("Competitor category conflicts with development status")
        if c.development_status in ("approved", "clinical_stage", "discontinued") and c.development_status not in c.categories:
            raise ValueError("Competitor status must have matching category")
    required_categories = set(Category.__args__)
    if set(analysis.competitive_coverage) != required_categories:
        raise ValueError("Coverage must explain every competitor category")
    for category, finding in analysis.competitive_coverage.items():
        matches = [c for c in analysis.competitors if category in c.categories]
        if finding.status == "documented" and (not finding.claim_ids or not matches):
            raise ValueError("Documented competitor category requires entries and claims")
        if finding.status == "insufficient_data" and not finding.unknowns:
            raise ValueError("Missing competitor coverage requires an explicit gap")
    for competitor in analysis.competitors:
        if not set(competitor.discontinuation_reason_claim_ids) <= claims.keys():
            raise ValueError("Unknown discontinuation reason claim reference")
        if competitor.development_status == "discontinued":
            if competitor.discontinuation_reason is None and not competitor.discontinuation_unknowns:
                raise ValueError("Unknown discontinuation reason must be explicit")
            if competitor.discontinuation_reason is not None and not competitor.discontinuation_reason_claim_ids:
                raise ValueError("Discontinuation reason requires claim references")
        elif competitor.discontinuation_reason is not None or competitor.discontinuation_reason_claim_ids or competitor.discontinuation_unknowns:
            raise ValueError("Discontinuation fields apply only to discontinued programs")
    if not analysis.pricing_analogues and not analysis.pricing_unknowns:
        raise ValueError("Missing pricing analogues requires an explicit gap")
    for analogue in analysis.pricing_analogues:
        if any(getattr(analogue, key) is None for key in ("price_description", "geography", "as_of_date")) and not analogue.unknowns:
            raise ValueError("Incomplete pricing analogue requires explicit unknowns")
        if analogue.as_of_date is not None:
            date.fromisoformat(analogue.as_of_date)
    access = analysis.access
    if any((access.reimbursement, access.prescribing, access.other_access)) and not access.claim_ids:
        raise ValueError("Access statements require claim references")
    if not access.unknowns and not all((access.reimbursement, access.prescribing, access.other_access)):
        raise ValueError("Incomplete access assessment requires explicit unknowns")
    value = analysis.commercial_value
    if value.assessment != "insufficient_data" and not value.claim_ids:
        raise ValueError("Commercial value assessment requires claim references")
    if any((value.unmet_need, value.willingness_to_pay)) and not value.claim_ids:
        raise ValueError("Commercial value statements require claim references")
    if (value.assessment == "insufficient_data" or value.willingness_to_pay is None) and not value.unknowns:
        raise ValueError("Unknown commercial value requires explicit gaps")
    if not pack.evidence and value.assessment != "insufficient_data":
        raise ValueError("Empty evidence cannot establish commercial value")
    names = {c.name for c in analysis.competitors}
    if any(d.comparator not in names for d in analysis.differentiation):
        raise ValueError("Differentiation must reference a listed comparator")


async def analyze_market(case: CaseInput, pack: EvidencePack, ctx: RunContext,
                         *, scenarios: list[MarketScenario] | None = None,
                         clinical: RoleResult | None = None) -> RoleResult:
    """Two concurrent task streams; bounded batches and Python-only assembly."""
    payload = prepare_market_inputs(case, pack, scenarios, clinical)
    if ctx.model is None or not callable(getattr(ctx.model, "generate_structured", None)):
        raise RuntimeError("R2 model adapter with generate_structured is required")
    contexts = {task: _pass_context(ctx, task) for task in PASS_MODELS}
    # Plan both streams before sending anything, so a planning failure costs nothing.
    batches = {task: plan_market_batches(payload, clinical, task, contexts[task]) for task in PASS_MODELS}
    competitive, commercial = await run_market_passes([
        run_market_pass(task, batches[task], contexts[task]) for task in PASS_MODELS])
    analysis = merge_market_results(competitive, commercial)
    validate_market_result(analysis, case, pack)
    calculations = payload["calculated_scenarios"]
    claims = [Claim(**c.model_dump(), provenance="ai") for c in analysis.claims]
    risks = [Risk(**r.model_dump()) for r in analysis.risks]
    gaps = identify_market_gaps(analysis, calculations)
    if clinical is None:
        gaps.append("Clinical eligibility alignment with R4 is pending.")
    limitations = list(dict.fromkeys([*analysis.limitations, *pack.retrieval_warnings,
        "Semantic evidence support requires R3 audit."]))
    sections = [
        {"key": "competitive_landscape", "summary": analysis.summary,
         "claim_ids": [c.id for c in claims], "limitations": limitations,
         "structured_data": {"competitors": classify_competitors(analysis),
                             "differentiation": assess_differentiation(analysis),
                             "coverage": {k: v.model_dump() for k, v in analysis.competitive_coverage.items()},
                             "diligence_questions": [q.model_dump() for q in analysis.diligence_questions]}},
        {"key": "commercial_opportunity", "summary": analysis.commercial_summary,
         "claim_ids": [c.id for c in claims], "limitations": limitations,
         "structured_data": {"target_population": analysis.target_population.model_dump(),
                             "clinical_alignment": payload["clinical_alignment"],
                             "pricing_analogues": [a.model_dump() for a in analysis.pricing_analogues],
                             "pricing_unknowns": analysis.pricing_unknowns,
                             "access": analysis.access.model_dump(),
                             "commercial_value": analysis.commercial_value.model_dump(),
                             "scenarios": calculations,
                             "scenario_ranges": summarize_market_ranges(calculations),
                             "addressable_patients": [{"scenario": r["inputs"]["name"],
                                 "eligible_patients": r["eligible_patients"],
                                 "accessible_patients": r["addressable_patients"],
                                 "geography": r["inputs"]["geography"],
                                 "as_of_date": r["inputs"]["as_of_date"]} for r in calculations],
                             "diligence_questions": [q.model_dump() for q in analysis.diligence_questions],
                             "source_requests": gaps}},
    ]
    section_content = []
    for data in sections:
        data["structured_data"].update({
            "prompt_version": PROMPT_VERSION,
            "synthetic": pack.synthetic,
        })
        section_content.append(SectionContent.model_validate(data))
    return RoleResult(role_id="market", summary=analysis.summary, position=analysis.position,
                      claims=claims, risks=risks, unknowns=gaps,
                      change_conditions=analysis.change_conditions, section_content=section_content)
