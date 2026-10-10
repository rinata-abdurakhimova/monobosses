"""Investment: prepare fixed plan -> Python arithmetic -> financial explanation.

No retrieval, upstream node calls, outreach, final recommendation or deal valuation.
"""
import json
import re
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
from vic.failures import MalformedModelOutput
from vic.integrity import assert_pack
from vic.tracing import scrub

from .investment_calculations import (
    InvestmentScenario,
    StressScenario,
    calculate_investment_scenarios,
)
from .investment_preparation import (
    NumericBinding,
    ScenarioBlueprint,
    StressBlueprint,
    resolve_numeric_inputs,
)

PLAN_PROMPT_ID = "investment_plan"
PLAN_PROMPT_VERSION = "1.0.0"
PLAN_PROMPT_PATH = Path(__file__).parent / "prompts" / "investment_plan.md"
PROMPT_ID = "investment"
PROMPT_VERSION = "2.0.0"
PROMPT_PATH = Path(__file__).parent / "prompts" / "investment.md"
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
UpstreamRole = Literal["clinical", "market", "partnerships", "ip_licensing"]


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InvestmentClaim(Claim):
    id: str = Field(max_length=128, pattern=r"^investment\.[a-z][a-z0-9_]*$")


class Finding(StrictOutput):
    value: Text | None
    basis: Literal["documented", "hypothesis", "unknown"]
    claim_ids: list[str]
    assumptions: list[Text]
    unknowns: list[Text]


class NextMilestone(StrictOutput):
    id: Identifier
    stage: Finding
    required_result: Finding
    success_criteria: list[Finding] = Field(min_length=1)
    clinical_alignment: Finding


class WorkPackage(StrictOutput):
    id: Identifier
    milestone_id: Identifier
    work: Finding
    required_resources: list[Finding] = Field(min_length=1)
    depends_on: list[Identifier]
    completion_criteria: Finding


class CapitalAssessment(StrictOutput):
    budget_basis: Finding
    scenario_ids: list[Identifier]
    missing_inputs: list[Text]
    # Explicit boundary, not a blend with asset development spending.
    company_financials_boundary: Text


class TimeAssessment(StrictOutput):
    scheduling_basis: Finding
    scenario_ids: list[Identifier]
    dependencies: list[Finding] = Field(min_length=1)
    possible_delays: list[Finding] = Field(min_length=1)
    missing_inputs: list[Text]


class ValueInflection(StrictOutput):
    id: Identifier
    event: Finding
    required_result: Finding
    potential_value_effect: Finding
    conditions: list[Text] = Field(min_length=1)
    next_check: Text


class FutureFinancing(StrictOutput):
    milestone_id: Identifier
    stage: Finding
    purpose: Finding
    funding_need: Finding
    possible_sources: list[Finding] = Field(min_length=1)
    prerequisites: list[Text] = Field(min_length=1)
    scenario_ids: list[Identifier]
    unknowns: list[Text]


class ContextDependency(StrictOutput):
    role_id: UpstreamRole
    assessment: Finding
    upstream_claim_ids: list[str]
    # Optional references to partnerships candidate IDs or IP option/asset/license IDs.
    record_ids: list[Identifier]
    next_check: Text


class FinancialPath(StrictOutput):
    path: Literal["own_development", "licensing", "acquisition"]
    feasibility: Literal["conditional", "not_currently_supported", "insufficient_data"]
    rationale: Finding
    financial_consequences: list[Finding] = Field(min_length=1)
    retained_costs_and_obligations: Finding
    financing_dependencies: list[ContextDependency] = Field(min_length=1)
    prerequisites: list[Text] = Field(min_length=1)
    unknowns: list[Text]
    next_check: Text


class StressAssessment(StrictOutput):
    kind: Literal["delay", "additional_studies", "weaker_results"]
    trigger: Finding
    budget_effect: Finding
    financing_effect: Finding
    time_effect: Finding
    stress_ids: list[Identifier]
    unknowns: list[Text]
    next_check: Text


class InvestmentCheck(StrictOutput):
    question: Text
    why_it_matters: Text
    evidence_needed: Text
    decision_if_positive: Text
    decision_if_negative: Text
    claim_ids: list[str]


class InvestmentAnalysis(StrictOutput):
    """Python-assembled plan and explanation; never a schema for the second LLM call."""
    summary: Text
    position: Literal["conditional_path", "material_constraints", "mixed", "insufficient_data"]
    claims: list[InvestmentClaim]
    next_milestone: NextMilestone
    work_packages: list[WorkPackage] = Field(min_length=1)
    capital: CapitalAssessment
    time: TimeAssessment
    value_inflections: list[ValueInflection] = Field(min_length=1)
    future_financing: list[FutureFinancing] = Field(min_length=1)
    financial_paths: list[FinancialPath] = Field(min_length=3, max_length=3)
    stress_assessments: list[StressAssessment] = Field(min_length=3, max_length=3)
    commercial_constraints: list[ContextDependency] = Field(min_length=1)
    risks: list[Risk]
    unknowns: list[Text]
    next_checks: list[InvestmentCheck] = Field(min_length=1)
    change_conditions: list[Text]
    limitations: list[Text]


class FutureMilestone(StrictOutput):
    milestone_id: Identifier
    stage: Finding


class StressEvent(StrictOutput):
    id: Identifier
    kind: Literal["delay", "additional_studies", "weaker_results"]
    trigger: Finding
    work_ids: list[Identifier]
    already_in_baseline: bool
    stress_ids: list[Identifier]


class PreparedInvestmentPlan(StrictOutput):
    """First LLM response: fixed plan and source-bound input proposals only."""
    claims: list[InvestmentClaim]
    next_milestone: NextMilestone
    work_packages: list[WorkPackage] = Field(min_length=1)
    future_milestones: list[FutureMilestone] = Field(min_length=1)
    stress_events: list[StressEvent] = Field(min_length=3, max_length=3)
    scenario_blueprints: list[ScenarioBlueprint]
    stress_blueprints: list[StressBlueprint]
    numeric_bindings: list[NumericBinding]
    risks: list[Risk]
    unknowns: list[Text]
    limitations: list[Text]


class FutureFundingExplanation(StrictOutput):
    milestone_id: Identifier
    purpose: Finding
    funding_need: Finding
    possible_sources: list[Finding] = Field(min_length=1)
    prerequisites: list[Text] = Field(min_length=1)
    scenario_ids: list[Identifier]
    unknowns: list[Text]


class StressExplanation(StrictOutput):
    event_id: Identifier
    budget_effect: Finding
    financing_effect: Finding
    time_effect: Finding
    unknowns: list[Text]
    next_check: Text


class InvestmentExplanation(StrictOutput):
    """Second LLM response: interpretation only; no plan or numerical inputs."""
    summary: Text
    position: Literal["conditional_path", "material_constraints", "mixed", "insufficient_data"]
    claims: list[InvestmentClaim]
    capital: CapitalAssessment
    time: TimeAssessment
    value_inflections: list[ValueInflection] = Field(min_length=1)
    future_financing: list[FutureFundingExplanation] = Field(min_length=1)
    financial_paths: list[FinancialPath] = Field(min_length=3, max_length=3)
    stress_explanations: list[StressExplanation] = Field(min_length=3, max_length=3)
    commercial_constraints: list[ContextDependency] = Field(min_length=1)
    risks: list[Risk]
    unknowns: list[Text]
    next_checks: list[InvestmentCheck] = Field(min_length=1)
    change_conditions: list[Text]
    limitations: list[Text]


def _walk(value):
    if isinstance(value, BaseModel):
        yield value
        for name in type(value).model_fields:
            yield from _walk(getattr(value, name))
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _validate_claims(claims, case, pack, *, require_assumptions=True):
    evidence = {e.id: e for e in pack.evidence}
    if len({c.id for c in claims}) != len(claims):
        raise ValueError("Duplicate claim IDs")
    for c in claims:
        if not set(c.evidence_ids) <= evidence.keys():
            raise ValueError("Unknown evidence ID")
        if case.scope == "approach" and c.scope == "program":
            raise ValueError("Program claim cannot expand approach scope")
        if c.support_status in ("supported", "contradicted", "mixed"):
            if not c.evidence_ids:
                raise ValueError("Factual claim requires evidence")
            if c.scope == "program" and not any(evidence[e].scope == "program" for e in c.evidence_ids):
                raise ValueError("Program fact requires program evidence")
        elif require_assumptions and not c.assumptions:
            raise ValueError("Unknown/unverified claim requires assumptions or gaps")


def _record_ids(result):
    ids = set()
    if result:
        # Only named ID records; arbitrary text/claim references do not become records.
        def visit(value):
            if isinstance(value, dict):
                if isinstance(value.get("id"), str):
                    ids.add(value["id"])
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
        for section in result.section_content:
            visit(section.structured_data)
    return ids


def prepare_investment_inputs(case: CaseInput, pack: EvidencePack, ctx: RunContext, *,
        clinical: RoleResult | dict | None = None, market: RoleResult | dict | None = None,
        partnerships: RoleResult | dict | None = None,
        ip_licensing: RoleResult | dict | None = None,
        scenarios: list[InvestmentScenario] | None = None,
        stresses: list[StressScenario] | None = None,
        calculate: bool = True) -> dict:
    assert_pack(pack)
    if ctx.snapshot_id is not None and ctx.snapshot_id != pack.snapshot_id:
        raise ValueError("Context and pack snapshots differ")
    if ctx.as_of_date and case.as_of_date and ctx.as_of_date != case.as_of_date:
        raise ValueError("Case and context dates differ")
    as_of = ctx.as_of_date or case.as_of_date
    context = {}
    for role, raw in (("clinical", clinical), ("market", market),
                      ("partnerships", partnerships), ("ip_licensing", ip_licensing)):
        result = RoleResult.model_validate(raw) if raw is not None else None
        if result:
            if result.role_id != role:
                raise ValueError(f"Expected {role} RoleResult")
            _validate_claims(result.claims, case, pack, require_assumptions=False)
            claims = {c.id for c in result.claims}
            for block in [*result.risks, *result.section_content]:
                if not set(block.claim_ids) <= claims:
                    raise ValueError("Upstream contains unknown claim references")
            for section in result.section_content:
                data = section.structured_data or {}
                nested = data.get(role, data)
                if isinstance(nested, dict):
                    if nested.get("snapshot_id", pack.snapshot_id) != pack.snapshot_id:
                        raise ValueError("Upstream snapshot differs")
                    if as_of and nested.get("as_of_date", as_of.isoformat()) != as_of.isoformat():
                        raise ValueError("Upstream date differs")
            context[role] = result.model_dump(mode="json")
        else:
            context[role] = None
    scenarios = [InvestmentScenario.model_validate(s) for s in scenarios or []]
    stresses = [StressScenario.model_validate(s) for s in stresses or []]
    evidence = {e.id: e for e in pack.evidence}
    for record in [*scenarios, *stresses]:
        for block in _walk(record):
            if hasattr(block, "evidence_ids"):
                if not set(block.evidence_ids) <= evidence.keys():
                    raise ValueError("Numeric input references unknown evidence")
                if (case.scope == "program" and block.minimum is not None and not any(
                        evidence[e].scope == "program" for e in block.evidence_ids) and not block.assumptions):
                    raise ValueError("Approach analogues for a program require explicit adaptation assumptions")
        if isinstance(record, InvestmentScenario) and as_of and record.as_of_date != as_of:
            raise ValueError("Numeric scenario date differs from effective as-of date")
    calculations = calculate_investment_scenarios(scenarios, stresses) if calculate else {
        "scenarios": [], "scenario_ranges": [], "stress_scenarios": []}
    sources = {s.id: s for s in pack.sources}
    return {"prompt_version": PROMPT_VERSION, "case": case.model_dump(mode="json"),
        "snapshot_id": pack.snapshot_id, "as_of_date": as_of.isoformat() if as_of else None,
        "synthetic": pack.synthetic or any(s.synthetic for s in pack.sources),
        "sources": [s.model_dump(mode="json") for s in pack.sources],
        "evidence": [e.model_dump(mode="json") | {"synthetic": sources[e.source_id].synthetic}
                     for e in pack.evidence],
        "retrieval_warnings": pack.retrieval_warnings,
        "upstream_context": context,
        "context_availability": {role: result is not None for role, result in context.items()},
        "caller_numeric_inputs": {"scenarios": [s.model_dump(mode="json") for s in scenarios],
                                      "stresses": [s.model_dump(mode="json") for s in stresses]},
        "calculated_financials": calculations}


def validate_investment_result(analysis: InvestmentAnalysis, case: CaseInput,
                               pack: EvidencePack, payload: dict) -> None:
    """Structural consistency, not semantic evidence audit or financial certification."""
    _validate_claims(analysis.claims, case, pack)
    claims = {c.id: c for c in analysis.claims}
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
                if block.basis == "hypothesis" and (not block.assumptions or any(
                        c.support_status not in ("unverified", "unknown") for c in linked)):
                    raise ValueError("Hypothesis requires assumptions and unverified/unknown claims")
        if isinstance(block, ContextDependency):
            raw = payload["upstream_context"][block.role_id]
            upstream = RoleResult.model_validate(raw) if raw else None
            known = {c.id for c in upstream.claims} if upstream else set()
            if not set(block.upstream_claim_ids) <= known or not set(block.record_ids) <= _record_ids(upstream):
                raise ValueError("Unknown upstream claim/record reference")
            if upstream is None and block.assessment.basis != "unknown":
                raise ValueError("Absent upstream requires unknown dependency assessment")
            if block.assessment.basis == "documented":
                upstream_claims = {c.id: c for c in upstream.claims}
                if not block.upstream_claim_ids or any(upstream_claims[c].support_status != "supported"
                                                       for c in block.upstream_claim_ids):
                    raise ValueError("Documented context assessment requires supported upstream claims")
    for entries in (analysis.work_packages, analysis.value_inflections, analysis.risks):
        if len({x.id for x in entries}) != len(entries):
            raise ValueError("Duplicate record IDs")
    if any(not r.id.startswith("investment.") or not r.claim_ids for r in analysis.risks):
        raise ValueError("Investment risks require namespace and claim references")
    next_id = analysis.next_milestone.id
    future_ids = [f.milestone_id for f in analysis.future_financing]
    if next_id in future_ids or len(set(future_ids)) != len(future_ids):
        raise ValueError("Future milestones must be distinct from next milestone and each other")
    milestones = {next_id, *future_ids}
    work = {w.id: w for w in analysis.work_packages}
    for w in work.values():
        if w.milestone_id not in milestones or not set(w.depends_on) <= work.keys():
            raise ValueError("Unknown work milestone/dependency")
        if any(work[d].milestone_id != w.milestone_id for d in w.depends_on):
            raise ValueError("Cross-milestone work dependency requires explicit narrative, not schedule edge")
    # Validate narrative DAG independently of numeric scenarios.
    from .investment_calculations import ReviewedRange, ScheduleTask, _schedule_bounds
    missing = ReviewedRange(minimum=None, maximum=None, evidence_ids=[], assumptions=[],
                            unknowns=["Narrative DAG validation only"])
    _schedule_bounds([ScheduleTask(work_id=w.id, duration_days=missing, depends_on=w.depends_on)
                      for w in work.values()])
    if not any(w.milestone_id == next_id for w in work.values()):
        raise ValueError("Next milestone requires work packages or explicitly unknown work placeholder")
    rows = payload["calculated_financials"]["scenarios"]
    scenarios = {r["id"]: r["inputs"] for r in rows}
    capital_ids, time_ids = set(analysis.capital.scenario_ids), set(analysis.time.scenario_ids)
    next_scenarios = {key for key, s in scenarios.items() if s["horizon"] == "next_milestone"}
    if capital_ids != next_scenarios or time_ids != next_scenarios:
        raise ValueError("Capital and time must reference every supplied next-milestone scenario")
    for future in analysis.future_financing:
        expected = {key for key, s in scenarios.items() if s["horizon"] == "future_milestone"
                    and s["milestone_id"] == future.milestone_id}
        if set(future.scenario_ids) != expected:
            raise ValueError("Future financing scenario references differ")
        if not expected and not future.unknowns:
            raise ValueError("Future financing without numeric inputs requires gaps")
    for s in scenarios.values():
        if s["milestone_id"] not in milestones or (s["horizon"] == "next_milestone"
                                                   and s["milestone_id"] != next_id) or (
                s["horizon"] == "future_milestone" and s["milestone_id"] == next_id):
            raise ValueError("Scenario milestone/horizon differs from analysis")
        expected_work = {w.id for w in work.values() if w.milestone_id == s["milestone_id"]}
        cost_work = set()
        for c in s["costs"]:
            if not set(c["work_ids"]) <= expected_work:
                raise ValueError("Cost references unknown or wrong-milestone work")
            if c["scope"] == "development":
                cost_work.update(c["work_ids"])
        if s["cost_coverage"] == "full" and (not expected_work or cost_work != expected_work):
            raise ValueError("Full budget must cover every work package")
        scheduled = {t["work_id"] for t in s["schedule"]}
        if not scheduled <= expected_work:
            raise ValueError("Schedule references unknown or wrong-milestone work")
        if s["schedule_coverage"] == "full" and scheduled != expected_work:
            raise ValueError("Full schedule must cover every work package")
        for t in s["schedule"]:
            if set(t["depends_on"]) != set(work[t["work_id"]].depends_on):
                raise ValueError("Numeric and narrative schedule dependencies differ")
    if not next_scenarios and (not analysis.capital.missing_inputs or not analysis.time.missing_inputs):
        raise ValueError("Absent next-milestone scenarios require capital and time gaps")
    if any(r["capital_to_milestone"] is None for r in rows if r["id"] in next_scenarios) and not analysis.capital.missing_inputs:
        raise ValueError("Incomplete capital requires missing inputs")
    if any(r["time_to_milestone_days"] is None for r in rows if r["id"] in next_scenarios) and not analysis.time.missing_inputs:
        raise ValueError("Incomplete time requires missing inputs")
    if {p.path for p in analysis.financial_paths} != {"own_development", "licensing", "acquisition"}:
        raise ValueError("Assess each financial path exactly once")
    for path in analysis.financial_paths:
        if not {"partnerships", "ip_licensing"} <= {d.role_id for d in path.financing_dependencies}:
            raise ValueError("Every path must explain partnerships and IP dependencies")
        if path.feasibility == "insufficient_data" and not path.unknowns:
            raise ValueError("Insufficient path requires gaps")
        if path.feasibility != "insufficient_data" and path.rationale.basis == "unknown":
            raise ValueError("Path feasibility requires rationale")
    if any(d.role_id != "market" for d in analysis.commercial_constraints):
        raise ValueError("Commercial constraints must explicitly refer to market context")
    kinds = {"delay", "additional_studies", "weaker_results"}
    if {s.kind for s in analysis.stress_assessments} != kinds:
        raise ValueError("Assess each stress kind exactly once")
    numeric_stress = payload["calculated_financials"]["stress_scenarios"]
    for stress in analysis.stress_assessments:
        expected = {r["id"] for r in numeric_stress if r["inputs"]["kind"] == stress.kind}
        if set(stress.stress_ids) != expected:
            raise ValueError("Stress references must match supplied calculations")
        if not expected and not stress.unknowns:
            raise ValueError("Unquantified stress requires gaps")
    if not pack.evidence and (analysis.position != "insufficient_data" or any(
            c.support_status in ("supported", "contradicted", "mixed") for c in analysis.claims)):
        raise ValueError("Empty evidence requires insufficient_data without factual claims")


def identify_investment_gaps(analysis: InvestmentAnalysis, payload: dict) -> list[str]:
    gaps = list(analysis.unknowns)
    for block in _walk(analysis):
        if block is not analysis and hasattr(block, "unknowns"):
            gaps.extend(block.unknowns)
        if hasattr(block, "missing_inputs"):
            gaps.extend(block.missing_inputs)
    for claim in analysis.claims:
        if claim.support_status in ("unknown", "unverified"):
            gaps.append(f"Requires verification: {claim.id}: {claim.text}")
    for role, available in payload["context_availability"].items():
        if not available:
            gaps.append(f"{role} context absent; alignment remains pending.")
    for row in payload["calculated_financials"]["scenarios"]:
        s = row["inputs"]
        gaps.extend(f"{row['id']}: {g}" for g in [*s["cost_unknowns"], *s["schedule_unknowns"],
                                                     *s["allocated_asset_cash"]["unknowns"]])
        for cost in s["costs"]:
            gaps.extend(f"{row['id']}/{cost['id']}: {g}" for g in cost["amount"]["unknowns"])
        for task in s["schedule"]:
            gaps.extend(f"{row['id']}/{task['work_id']}: {g}" for g in task["duration_days"]["unknowns"])
    for row in payload["calculated_financials"]["stress_scenarios"]:
        s = row["inputs"]
        gaps.extend(f"{row['id']}: {g}" for g in s["unknowns"])
        for key in ("incremental_delay_days", "incremental_cost", "burn_per_day"):
            gaps.extend(f"{row['id']}/{key}: {g}" for g in s[key]["unknowns"])
    return list(dict.fromkeys(gaps))


def validate_prepared_plan(plan: PreparedInvestmentPlan, case: CaseInput, pack: EvidencePack,
                           payload: dict, scenarios: list[InvestmentScenario],
                           stresses: list[StressScenario]) -> None:
    """Reject invalid plan before paying for the explanation call."""
    _validate_claims(plan.claims, case, pack)
    claims = {c.id: c for c in plan.claims}
    for block in _walk(plan):
        if hasattr(block, "claim_ids") and not set(block.claim_ids) <= claims.keys():
            raise ValueError("Prepared plan contains unknown claim reference")
        if isinstance(block, Finding):
            if block.basis == "unknown":
                if block.value is not None or not block.unknowns:
                    raise ValueError("Unknown plan finding requires null and gaps")
            else:
                linked = [claims[c] for c in block.claim_ids]
                if block.value is None or not linked:
                    raise ValueError("Plan finding requires value and claims")
                if block.basis == "documented" and any(c.support_status != "supported" for c in linked):
                    raise ValueError("Documented plan finding requires supported claims")
                if block.basis == "hypothesis" and (not block.assumptions or any(
                        c.support_status not in ("unverified", "unknown") for c in linked)):
                    raise ValueError("Plan hypothesis requires assumptions and unverified claims")
    if any(not r.id.startswith("investment.") or not r.claim_ids for r in plan.risks):
        raise ValueError("Plan risks require investment namespace and claims")
    if len({r.id for r in plan.risks}) != len(plan.risks):
        raise ValueError("Duplicate planning risk IDs")
    next_id = plan.next_milestone.id
    future_ids = [f.milestone_id for f in plan.future_milestones]
    if next_id in future_ids or len(set(future_ids)) != len(future_ids):
        raise ValueError("Prepared future milestones must be distinct")
    work = {w.id: w for w in plan.work_packages}
    if len(work) != len(plan.work_packages) or not any(w.milestone_id == next_id for w in work.values()):
        raise ValueError("Prepared plan requires unique work and next-milestone work")
    for w in work.values():
        if w.milestone_id not in {next_id, *future_ids} or not set(w.depends_on) <= work.keys():
            raise ValueError("Unknown plan milestone/work dependency")
        if any(work[d].milestone_id != w.milestone_id for d in w.depends_on):
            raise ValueError("Cross-milestone dependency must remain narrative")
    from .investment_calculations import ReviewedRange, ScheduleTask, _schedule_bounds
    missing = ReviewedRange(minimum=None, maximum=None, evidence_ids=[], assumptions=[], unknowns=["DAG check"])
    _schedule_bounds([ScheduleTask(work_id=w.id, duration_days=missing, depends_on=w.depends_on)
                      for w in work.values()])
    # Validate all supplied and generated scenarios against the same frozen work plan.
    scenario_map = {s.id: s for s in scenarios}
    if len(scenario_map) != len(scenarios):
        raise ValueError("Generated/caller scenario IDs collide")
    for s in scenarios:
        if s.milestone_id not in {next_id, *future_ids} or (s.horizon == "next_milestone") != (s.milestone_id == next_id):
            raise ValueError("Prepared numeric horizon/milestone differs")
        if payload["as_of_date"] and s.as_of_date.isoformat() != payload["as_of_date"]:
            raise ValueError("Prepared numeric date differs")
        expected = {w.id for w in work.values() if w.milestone_id == s.milestone_id}
        covered = set()
        for cost in s.costs:
            if not set(cost.work_ids) <= expected:
                raise ValueError("Prepared cost references unknown work")
            if cost.scope == "development":
                covered.update(cost.work_ids)
        if s.cost_coverage == "full" and (not expected or covered != expected):
            raise ValueError("Full prepared budget must cover every work")
        scheduled = {t.work_id for t in s.schedule}
        if not scheduled <= expected or (s.schedule_coverage == "full" and scheduled != expected):
            raise ValueError("Prepared schedule coverage differs from plan")
        if any(set(t.depends_on) != set(work[t.work_id].depends_on) for t in s.schedule):
            raise ValueError("Prepared schedule edges differ from plan")
    events = {e.id: e for e in plan.stress_events}
    if len(events) != 3 or {e.kind for e in events.values()} != {"delay", "additional_studies", "weaker_results"}:
        raise ValueError("Prepared plan must explain all three stress kinds exactly once")
    stress_map = {s.id: s for s in stresses}
    if len(stress_map) != len(stresses):
        raise ValueError("Generated/caller stress IDs collide")
    for event in events.values():
        if not set(event.work_ids) <= work.keys():
            raise ValueError("Stress event references unknown work")
        expected = {s.id for s in stresses if s.kind == event.kind}
        if set(event.stress_ids) != expected or len(event.stress_ids) != len(expected):
            raise ValueError("Prepared stress references differ from numeric inputs")
        if expected and (event.already_in_baseline or event.trigger.basis == "unknown" or not event.work_ids):
            raise ValueError("Numeric stress requires a known/hypothetical incremental trigger tied to work")
        for stress_id in expected:
            stress = stress_map[stress_id]
            if stress.base_scenario_id not in scenario_map:
                raise ValueError("Unknown prepared stress base")
            base = scenario_map[stress.base_scenario_id]
            if any(work[w].milestone_id != base.milestone_id for w in event.work_ids):
                raise ValueError("Stress event work belongs to another milestone")
    for blueprint in plan.stress_blueprints:
        if blueprint.trigger_id not in events or blueprint.id not in events[blueprint.trigger_id].stress_ids:
            raise ValueError("Stress blueprint must link to its fixed trigger")
    for record in [*scenarios, *stresses]:
        for block in _walk(record):
            if hasattr(block, "evidence_ids"):
                known = {e.id: e for e in pack.evidence}
                if not set(block.evidence_ids) <= known.keys():
                    raise ValueError("Prepared number references unknown evidence")
                if case.scope == "program" and block.minimum is not None and not any(
                        known[e].scope == "program" for e in block.evidence_ids) and not block.assumptions:
                    raise ValueError("Program numeric analogue requires adaptation assumptions")
    if not pack.evidence and any(c.support_status in ("supported", "mixed", "contradicted") for c in plan.claims):
        raise ValueError("Empty evidence cannot support factual planning claims")


def validate_explanation_numbers(explanation: InvestmentExplanation | dict) -> None:
    """Keep numeric literals in Python records, not free-form model interpretation.

    Checking a global whitelist of numbers would still allow a valid amount to be
    attached to the wrong scenario, currency or time unit. Reference fields remain
    available; narrative must point to the structured calculations instead.
    This is a lexical guard, not semantic verification of qualitative claims.
    """
    reference_fields = {
        "id", "claim_ids", "evidence_ids", "scenario_ids", "event_id",
        "upstream_claim_ids", "record_ids", "milestone_id",
    }

    def check(value, path="explanation"):
        if isinstance(value, dict):
            for key, child in value.items():
                if key not in reference_fields:
                    check(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                check(child, f"{path}[{index}]")
        elif isinstance(value, str):
            # R1--R5 are team role names, not financial quantities.
            narrative = re.sub(r"\bR[1-5]\b", "reviewer", value)
            if re.search(r"\d", narrative):
                raise ValueError(
                    f"Numeric literals are forbidden in explanation narrative: {path}; "
                    "refer to Python calculated_financials instead"
                )

    check(explanation.model_dump(mode="json") if isinstance(explanation, BaseModel) else explanation)


def assemble_investment_analysis(plan: PreparedInvestmentPlan,
                                 explanation: InvestmentExplanation) -> InvestmentAnalysis:
    """Only Python combines fixed records and interpretation; the second model cannot replace them."""
    validate_explanation_numbers(explanation)
    if {c.id for c in plan.claims} & {c.id for c in explanation.claims}:
        raise ValueError("Explanation must reference fixed claims, not repeat or replace them")
    if {r.id for r in plan.risks} & {r.id for r in explanation.risks}:
        raise ValueError("Explanation must not replace planning risks")
    future = {f.milestone_id: f for f in plan.future_milestones}
    if {f.milestone_id for f in explanation.future_financing} != future.keys() or len(
            explanation.future_financing) != len(future):
        raise ValueError("Explanation must cover each fixed future milestone exactly once")
    events = {e.id: e for e in plan.stress_events}
    if {e.event_id for e in explanation.stress_explanations} != events.keys() or len(
            explanation.stress_explanations) != len(events):
        raise ValueError("Explanation must cover each fixed stress event exactly once")
    data = explanation.model_dump(mode="json", exclude={"stress_explanations", "future_financing"})
    data.update(next_milestone=plan.next_milestone.model_dump(mode="json"),
        work_packages=[w.model_dump(mode="json") for w in plan.work_packages],
        claims=[c.model_dump(mode="json") for c in [*plan.claims, *explanation.claims]],
        risks=[r.model_dump(mode="json") for r in [*plan.risks, *explanation.risks]],
        unknowns=list(dict.fromkeys([*plan.unknowns, *explanation.unknowns])),
        limitations=list(dict.fromkeys([*plan.limitations, *explanation.limitations])),
        future_financing=[f.model_dump(mode="json") | {"stage": future[f.milestone_id].stage.model_dump(mode="json")}
                          for f in explanation.future_financing],
        stress_assessments=[s.model_dump(mode="json", exclude={"event_id"}) | {
            "kind": events[s.event_id].kind, "trigger": events[s.event_id].trigger.model_dump(mode="json"),
            "stress_ids": events[s.event_id].stress_ids} for s in explanation.stress_explanations])
    return InvestmentAnalysis.model_validate(data)


def qualify_incomplete_plan_findings(plan: PreparedInvestmentPlan) -> PreparedInvestmentPlan:
    data = plan.model_dump(mode='python')
    gaps = []
    def walk(value, path='investment_plan'):
        if isinstance(value, dict):
            if value.get('basis') in ('documented', 'hypothesis') and (
                    value.get('value') is None or not value.get('claim_ids')):
                gap = (f"Incomplete finding at {path}: original value={value.get('value')!r}; "
                    "the model supplied no value or no supporting claim references. "
                    "This planning input remains unknown and requires evidence.")
                value.update(basis='unknown', value=None, unknowns=[*value.get('unknowns', []), gap])
                gaps.append(gap)
            for key, child in value.items():
                walk(child, f'{path}.{key}')
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f'{path}[{index}]')
    walk(data)
    if gaps:
        data['unknowns'].extend(gaps)
        data['limitations'].append('Partial Investment plan: incomplete findings were marked unknown; no missing values or supporting claims were invented.')
    return PreparedInvestmentPlan.model_validate(data)


def _stage_validation_reason(exc, settings):
    if isinstance(exc, ValidationError):
        detail = '; '.join(('.'.join(map(str, e['loc'])) or '<root>') + ': ' + e['msg']
            for e in exc.errors(include_input=False, include_context=False))
    else:
        detail = str(exc)
    return scrub(detail, secrets=[settings.llm_api_key, settings.api_shared_secret])[:1000]


async def _generate_validated_stage(prompt_id, payload, response_model, ctx, validate):
    """Repair the stage that failed domain checks, retaining the validated prior plan."""
    settings = getattr(ctx.model, '_s', None)
    repairs = min(1, settings.llm_max_repairs) if settings is not None else 0
    call_ctx = ctx
    for attempt in range(repairs + 1):
        raw = await ctx.model.generate_structured(prompt_id, deepcopy(payload), response_model, call_ctx)
        try:
            value = response_model.model_validate(raw.model_dump(mode='json') if isinstance(raw, BaseModel) else raw)
            return validate(value)
        except ValueError as exc:
            if attempt == repairs:
                raise
            detail = _stage_validation_reason(exc, settings)
            ctx.trace.log(RunStage.ANALYZE, f'{prompt_id} domain repair: {detail}')
            feedback = [*ctx.feedback.get('investment', []),
                'Correct this domain validation error: ' + detail
                + '. Keep the supplied fixed_plan, its claims, identifiers and calculated_financials unchanged. '
                'Use exact supplied references; do not invent missing inputs or financial numbers.']
            call_ctx = replace(ctx, feedback={**ctx.feedback, 'investment': feedback})


async def analyze_investment(case: CaseInput, pack: EvidencePack, ctx: RunContext, *,
        clinical: RoleResult | dict | None = None, market: RoleResult | dict | None = None,
        partnerships: RoleResult | dict | None = None, ip_licensing: RoleResult | dict | None = None,
        scenarios: list[InvestmentScenario] | None = None,
        stresses: list[StressScenario] | None = None) -> RoleResult:
    payload = prepare_investment_inputs(case, pack, ctx, clinical=clinical, market=market,
        partnerships=partnerships, ip_licensing=ip_licensing, scenarios=scenarios, stresses=stresses,
        calculate=False)
    if ctx.model is None or not callable(getattr(ctx.model, "generate_structured", None)):
        raise RuntimeError("R2 model adapter with generate_structured is required")
    # Adapters receive detached payloads so accidental mutation cannot rewrite canonical records.
    payload["prompt_version"] = PLAN_PROMPT_VERSION
    def validate_plan(candidate):
        candidate = qualify_incomplete_plan_findings(candidate)
        generated, generated_stresses, bindings = resolve_numeric_inputs(
            candidate.scenario_blueprints, candidate.stress_blueprints, candidate.numeric_bindings, pack)
        caller = payload["caller_numeric_inputs"]
        scenarios_for_plan = [*[InvestmentScenario.model_validate(s) for s in caller["scenarios"]], *generated]
        stresses_for_plan = [*[StressScenario.model_validate(s) for s in caller["stresses"]], *generated_stresses]
        validate_prepared_plan(candidate, case, pack, payload, scenarios_for_plan, stresses_for_plan)
        return candidate, bindings, calculate_investment_scenarios(scenarios_for_plan, stresses_for_plan)

    plan, bindings, calculations = await _generate_validated_stage(
        PLAN_PROMPT_ID, payload, PreparedInvestmentPlan, ctx, validate_plan)
    fixed_plan = plan.model_dump(mode="json", exclude={"scenario_blueprints", "stress_blueprints", "numeric_bindings"})
    plan_hash = sha256(json.dumps(fixed_plan, sort_keys=True).encode()).hexdigest()
    explanation_payload = {k: v for k, v in payload.items() if k not in (
        "caller_numeric_inputs", "calculated_financials", "prompt_version")}
    explanation_payload.update(prompt_version=PROMPT_VERSION, fixed_plan=fixed_plan,
        fixed_plan_hash=plan_hash, calculated_financials=calculations, numeric_provenance=bindings)
    def validate_explanation(candidate):
        analysis = assemble_investment_analysis(plan, candidate)
        validate_investment_result(analysis, case, pack, explanation_payload)
        return analysis

    try:
        analysis = await _generate_validated_stage(
            PROMPT_ID, explanation_payload, InvestmentExplanation, ctx, validate_explanation)
    except (ValueError, MalformedModelOutput) as exc:
        settings = getattr(ctx.model, '_s', None)
        if settings is None or not settings.continue_on_node_validation_error:
            raise
        reason = _stage_validation_reason(exc, settings)
        gap = 'Financial interpretation unavailable after validation; the validated plan and Python calculations are retained.'
        milestone = plan.next_milestone.required_result.value
        work_items = [w.work.value for w in plan.work_packages if w.work.value]
        summary = ('Preliminary investment plan: ' + (milestone or 'next-milestone requirements remain unknown')
            + ('. Proposed work: ' + '; '.join(work_items[:3]) if work_items else '')
            + '. Financial path feasibility and financing implications require a corrected interpretation.')
        ctx.trace.log(RunStage.ANALYZE, 'investment partial plan retained: ' + reason)
        return RoleResult(role_id='investment', position='partial_assessment', summary=summary,
            claims=[Claim.model_validate(c.model_dump()) for c in plan.claims], risks=plan.risks,
            unknowns=list(dict.fromkeys([*plan.unknowns, gap, 'Validation reason: ' + reason])),
            change_conditions=['Validate financing-path and stress interpretations against the saved plan and calculations.'],
            section_content=[SectionContent(key='capital_to_milestone', summary=summary,
                claim_ids=[c.id for c in plan.claims], limitations=[*plan.limitations, gap,
                    'A retained plan is not a validated financial interpretation or an investment recommendation.'],
                structured_data={'investment': {'prepared_plan': fixed_plan, 'fixed_plan_hash': plan_hash,
                    'calculated_financials': calculations, 'numeric_provenance': bindings,
                    'snapshot_id': pack.snapshot_id, 'as_of_date': payload['as_of_date'],
                    'numeric_review_status': 'semantic_review_pending',
                    'explanation_recovery': {'status': 'analysis_unavailable', 'validation_reason': reason}}})])
    gaps = identify_investment_gaps(analysis, explanation_payload)
    gaps.extend(f"R3 semantic review pending: {b['record_id']}/{b['input_path']}: {b['applicability']}"
                for b in bindings)
    limitations = list(dict.fromkeys([*analysis.limitations, *pack.retrieval_warnings,
        "Source token/unit checks are not semantic evidence audit; R3 review required.",
        "Numeric applicability and completeness require human verification; scenario bounds are not confidence intervals.",
        "Market opportunity, partner fit and IP screening do not establish revenue, deal value or investment return.",
        "No final committee recommendation or legal clearance; R4 milestone review and IP specialist review required."]))
    data = analysis.model_dump(mode="json", exclude={"claims", "risks"})
    data.update({"calculated_financials": calculations, "source_requests": gaps,
        "prompt_version": PROMPT_VERSION, "prompt_versions": {
            PLAN_PROMPT_ID: PLAN_PROMPT_VERSION, PROMPT_ID: PROMPT_VERSION},
        "prepared_plan": fixed_plan, "fixed_plan_hash": plan_hash,
        "numeric_provenance": bindings, "numeric_review_status": "semantic_review_pending",
        "snapshot_id": pack.snapshot_id, "as_of_date": payload["as_of_date"], "synthetic": payload["synthetic"],
        "context_availability": payload["context_availability"], "upstream_context": payload["upstream_context"],
        "claim_evidence_links": {c.id: c.evidence_ids for c in analysis.claims},
        "evidence_source_links": {e.id: e.source_id for e in pack.evidence}})
    section = SectionContent(key="capital_to_milestone", summary=analysis.summary,
        claim_ids=[c.id for c in analysis.claims], limitations=limitations,
        structured_data={"investment": data})
    return RoleResult(role_id="investment", summary=analysis.summary, position=analysis.position,
        claims=[Claim.model_validate(c.model_dump()) for c in analysis.claims], risks=analysis.risks,
        unknowns=gaps, change_conditions=analysis.change_conditions, section_content=[section])
