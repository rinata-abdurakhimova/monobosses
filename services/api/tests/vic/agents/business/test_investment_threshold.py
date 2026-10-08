"""Offline gate, provenance and data-flow regression tests."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from vic.agents.business.investment_threshold import (
    ROLES, ThresholdAnalysis, analyze_investment_threshold,
    identify_threshold_gaps, prepare_threshold_inputs, validate_threshold_result,
)
from vic.contracts import CaseInput, EvidencePack, RoleResult, RunContext


def inputs(empty=False):
    case = CaseInput(indication="Synthetic disease", mechanism="Synthetic mechanism", scope="approach")
    pack = EvidencePack(snapshot_id="threshold-snapshot", synthetic=True,
        sources=[] if empty else [dict(id="s1", title="Synthetic study", type="synthetic",
            retrieved_at="2026-10-08T00:00:00Z", synthetic=True, content_hash="sha256:" + "a" * 64)],
        evidence=[] if empty else [dict(id="e1", source_id="s1", scope="approach",
            excerpt="Synthetic target engagement result", locator="study result")])
    ctx = RunContext(case_id="case-threshold", run_id="run-threshold", mode="evidence_only",
                     snapshot_id=pack.snapshot_id, as_of_date=None)
    return case, pack, ctx


def finding(basis="hypothesis"):
    return dict(value=None if basis == "unknown" else "Proposed target engagement gate",
        basis=basis, claim_ids=[] if basis == "unknown" else ["investment_threshold.result"],
        assumptions=["Synthetic proposal requires expert review"] if basis == "hypothesis" else [],
        unknowns=["Need applicable study"] if basis == "unknown" else [])


def rule(result):
    return dict(result=result, rationale="Assess relevance to funding the next test",
                claim_ids=["investment_threshold.result"])


def output():
    gates = []
    for horizon in ("now", "next_stage"):
        cid = f"criterion_{horizon}"
        gates.append(dict(id=f"gate_{horizon}", horizon=horizon,
            required_result=finding(), obtainable_stage=finding(),
            criteria=[dict(id=cid, sufficient_result=finding(), rationale=finding(),
                           assessment_method="Reviewed target engagement assay")],
            existing_evidence=[dict(criterion_id=cid, finding=finding("unknown"),
                                    evidence_ids=[], limitations=["No applicable result supplied"])],
            status="unknown", assessment=finding("unknown"),
            gaps=[dict(id=f"gap_{horizon}", criterion_ids=[cid],
                missing_result_or_data="Applicable target engagement result",
                investment_impact=finding(), priority="critical",
                check=dict(method="Run validated assay", evidence_needed="Assay result and controls",
                    feasible_stage=finding(), continue_if=rule("Reproducible engagement supports test funding"),
                    revise_if=rule("Mixed engagement requires revised experiment"),
                    stop_if=rule("Confirmed absence of engagement undermines mechanism"),
                    inconclusive_if="Invalid controls require repeating the assay"))],
            dependencies=[dict(role_id=r, assessment=finding("unknown"),
                upstream_claim_ids=[], record_ids=[], next_check=f"Obtain {r} review") for r in ROLES],
            continue_if=rule("All critical criteria met supports continuation"),
            revise_if=rule("Mixed decisive data requires review"),
            stop_if=rule("Validated decisive failure supports stopping recommendation")))
    return dict(summary="Synthetic threshold proposal; data insufficient", position="insufficient_data",
        claims=[dict(id="investment_threshold.result", text="Engagement may justify a bounded test",
            provenance="ai", support_status="unverified", evidence_ids=[],
            assumptions=["Proposed requirement; expert review needed"], scope="approach", importance="critical")],
        gates=gates, risks=[dict(id="investment_threshold.engagement", description="Engagement unknown",
            priority="critical", claim_ids=["investment_threshold.result"], impact="Funding rationale unresolved",
            next_check="Review assay")], unknowns=["Applicable result absent"],
        change_conditions=["Reviewed decisive data changes readiness"], limitations=["Synthetic test"])


def validate(data, empty=False, upstream=None):
    case, pack, ctx = inputs(empty)
    payload = prepare_threshold_inputs(case, pack, ctx, **(upstream or {}))
    analysis = ThresholdAnalysis.model_validate(data)
    validate_threshold_result(analysis, case, pack, payload)
    return analysis


def upstream(role):
    return RoleResult(role_id=role, summary="Synthetic upstream", position="unknown",
        claims=[dict(id=f"{role}.result", text="Synthetic result", provenance="source",
            support_status="supported", evidence_ids=["e1"], scope="approach", importance="major")],
        unknowns=["Applicability pending"], section_content=[dict(key="critical_unknowns", summary="Synthetic",
            claim_ids=[f"{role}.result"], structured_data={role: dict(snapshot_id="threshold-snapshot",
                records=[dict(id=f"record_{role}", value="Keep complete upstream data")])})])


def documented(data):
    data["claims"][0].update(provenance="source", support_status="supported", evidence_ids=["e1"], assumptions=[])
    for gate in data["gates"]:
        gate.update(status="met", assessment=finding("documented"), gaps=[])
        gate["required_result"] = finding("documented")
        gate["obtainable_stage"] = finding("documented")
        gate["criteria"][0].update(sufficient_result=finding("documented"), rationale=finding("documented"))
        gate["existing_evidence"][0].update(finding=finding("documented"), evidence_ids=["e1"])
        for dep in gate["dependencies"]:
            role = dep["role_id"]
            dep.update(assessment=finding("documented"), upstream_claim_ids=[f"{role}.result"],
                       record_ids=[f"record_{role}"])
    data["position"] = "thresholds_met"
    return {r: upstream(r) for r in ROLES}


@pytest.mark.parametrize("empty", [False, True])
def test_all_eight_requirements_and_missing_evidence(empty):
    analysis = validate(output(), empty)
    for gate in analysis.gates:
        assert gate.required_result and gate.obtainable_stage
        assert gate.criteria[0].sufficient_result and gate.criteria[0].rationale
        assert gate.existing_evidence[0].finding.value is None
        gap = gate.gaps[0]
        assert gap.missing_result_or_data and gap.investment_impact and gap.check.method
        assert gap.check.continue_if and gap.check.revise_if and gap.check.stop_if
        assert gate.continue_if and gate.revise_if and gate.stop_if


def test_documented_met_gates_and_evidenced_failure():
    data = output()
    contexts = documented(data)
    validate(data, upstream=contexts)
    data["position"] = "material_barriers"
    gate = data["gates"][0]
    gate["status"] = "not_met"
    gate["gaps"] = output()["gates"][0]["gaps"]
    gate["gaps"][0]["investment_impact"] = finding("documented")
    gate["gaps"][0]["check"]["feasible_stage"] = finding("documented")
    validate(data, upstream=contexts)


@pytest.mark.parametrize("defect", ["claim_dup", "evidence", "scope", "claim_ref", "documented",
    "hypothesis", "unknown_value", "unknown_gap", "claim_assumptions", "gate_dup", "criterion_dup",
    "gap_dup", "risk_dup", "risk_namespace", "risk_claim", "horizon", "roles", "dependency_dup",
    "upstream_claim", "upstream_record", "absent_context", "existing_missing", "existing_dup",
    "existing_wrong", "existing_unknown", "existing_unlinked", "documented_no_evidence",
    "gap_criterion", "gap_missing", "uncovered", "false_met", "false_failure", "false_partial",
    "unknown_assessment", "false_position", "false_barrier", "unknown_position", "extra", "blank"])
def test_reject_invalid_outputs(defect):
    d = output()
    g = d["gates"][0]
    c = d["claims"][0]
    if defect == "claim_dup": d["claims"].append(deepcopy(c))
    if defect == "evidence": c["evidence_ids"] = ["missing"]
    if defect == "scope": c["scope"] = "program"
    if defect == "claim_ref": g["required_result"]["claim_ids"] = ["market.result"]
    if defect == "documented": g["required_result"]["basis"] = "documented"
    if defect == "hypothesis": g["required_result"]["assumptions"] = []
    if defect == "unknown_value": g["assessment"]["value"] = "Invented result"
    if defect == "unknown_gap": g["assessment"]["unknowns"] = []
    if defect == "claim_assumptions": c["assumptions"] = []
    if defect == "gate_dup": d["gates"][1]["id"] = g["id"]
    if defect == "criterion_dup": d["gates"][1]["criteria"][0]["id"] = g["criteria"][0]["id"]
    if defect == "gap_dup": d["gates"][1]["gaps"][0]["id"] = g["gaps"][0]["id"]
    if defect == "risk_dup": d["risks"].append(deepcopy(d["risks"][0]))
    if defect == "risk_namespace": d["risks"][0]["id"] = "market.risk"
    if defect == "risk_claim": d["risks"][0]["claim_ids"] = []
    if defect == "horizon": d["gates"][1]["horizon"] = "now"
    if defect == "roles":
        for gate in d["gates"]: gate["dependencies"] = gate["dependencies"][:-1]
    if defect == "dependency_dup": g["dependencies"].append(deepcopy(g["dependencies"][0]))
    if defect == "upstream_claim": g["dependencies"][0]["upstream_claim_ids"] = ["science.missing"]
    if defect == "upstream_record": g["dependencies"][0]["record_ids"] = ["missing"]
    if defect == "absent_context": g["dependencies"][0]["assessment"] = finding()
    if defect == "existing_missing": g["existing_evidence"] = []
    if defect == "existing_dup": g["existing_evidence"].append(deepcopy(g["existing_evidence"][0]))
    if defect == "existing_wrong": g["existing_evidence"][0]["criterion_id"] = "wrong"
    if defect == "existing_unknown": g["existing_evidence"][0]["evidence_ids"] = ["missing"]
    if defect == "existing_unlinked": g["existing_evidence"][0]["evidence_ids"] = ["e1"]
    if defect == "documented_no_evidence":
        c.update(support_status="supported", evidence_ids=["e1"])
        g["existing_evidence"][0]["finding"] = finding("documented")
    if defect == "gap_criterion": g["gaps"][0]["criterion_ids"] = ["criterion_next_stage"]
    if defect == "gap_missing": g["gaps"] = []
    if defect == "uncovered":
        g["criteria"].append(dict(id="additional", sufficient_result=finding(), rationale=finding(), assessment_method="Review"))
        g["existing_evidence"].append(dict(criterion_id="additional", finding=finding("unknown"), evidence_ids=[], limitations=[]))
    if defect == "false_met": g["status"] = "met"
    if defect == "false_failure": g["status"] = "not_met"
    if defect == "false_partial": g["status"] = "partially_met"
    if defect == "unknown_assessment": g["assessment"] = finding()
    if defect == "false_position": d["position"] = "thresholds_met"
    if defect == "false_barrier": d["position"] = "material_barriers"
    if defect == "unknown_position": d["position"] = "conditional"
    if defect == "extra": d["score"] = 99
    if defect == "blank": g["gaps"][0]["check"]["method"] = "   "
    with pytest.raises((ValueError, ValidationError)): validate(d)


@pytest.mark.parametrize("field", ["required_result", "obtainable_stage", "criteria", "existing_evidence",
    "gaps", "dependencies", "continue_if", "revise_if", "stop_if", "assessment", "status"])
def test_required_gate_fields(field):
    d = output()
    del d["gates"][0][field]
    with pytest.raises(ValidationError): validate(d)


@pytest.mark.parametrize("field", ["method", "evidence_needed", "feasible_stage", "continue_if", "revise_if", "stop_if", "inconclusive_if"])
def test_required_check_fields(field):
    d = output()
    del d["gates"][0]["gaps"][0]["check"][field]
    with pytest.raises(ValidationError): validate(d)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("serialized", [False, True])
def test_all_upstream_inputs_preserved(role, serialized):
    case, pack, ctx = inputs()
    result = upstream(role)
    raw = result.model_dump(mode="json") if serialized else result
    before = deepcopy(result.model_dump(mode="json"))
    payload = prepare_threshold_inputs(case, pack, ctx, **{role: raw})
    assert payload["upstream_context"][role] == before
    assert result.model_dump(mode="json") == before
    assert payload["context_availability"][role]
    assert payload["evidence"][0]["excerpt"] == pack.evidence[0].excerpt
    assert payload["sources"][0]["content_hash"] == pack.sources[0].content_hash


@pytest.mark.parametrize("defect", ["snapshot", "date", "role", "source", "duplicate_source", "duplicate_evidence",
    "claim_evidence", "claim_duplicate", "risk_claim", "section_claim", "nested_snapshot", "metadata_date",
    "nested_evidence"])
def test_invalid_inputs_fail_before_model_call(defect):
    case, pack, ctx = inputs()
    market = upstream("market").model_dump(mode="json")
    if defect == "snapshot": ctx.snapshot_id = "wrong"
    if defect == "date":
        case.as_of_date = date(2026, 10, 7)
        ctx.as_of_date = date(2026, 10, 8)
    if defect == "role": market["role_id"] = "clinical"
    if defect == "source": pack.evidence[0].source_id = "missing"
    if defect == "duplicate_source": pack.sources.append(pack.sources[0])
    if defect == "duplicate_evidence": pack.evidence.append(pack.evidence[0])
    if defect == "claim_evidence": market["claims"][0]["evidence_ids"] = ["missing"]
    if defect == "claim_duplicate": market["claims"].append(deepcopy(market["claims"][0]))
    if defect == "risk_claim": market["risks"] = [dict(id="market.risk", description="Risk", priority="major", claim_ids=["market.missing"], impact="Impact", next_check="Review")]
    if defect == "section_claim": market["section_content"][0]["claim_ids"] = ["market.missing"]
    if defect in ("nested_snapshot", "metadata_date", "nested_evidence"):
        record = market["section_content"][0]["structured_data"]["market"]["records"][0]
        if defect == "nested_snapshot": record["snapshot_id"] = "wrong"
        elif defect == "metadata_date":
            ctx.as_of_date = date(2026, 10, 8)
            market["section_content"][0]["structured_data"]["market"]["as_of_date"] = "2026-10-07"
        elif defect == "nested_evidence": record["evidence_ids"] = ["missing"]
    with pytest.raises(ValueError): prepare_threshold_inputs(case, pack, ctx, market=market)


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_one_call_full_result_roundtrip_and_no_mutation(empty):
    case, pack, ctx = inputs(empty)
    raw = output()
    before = deepcopy(raw)
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(return_value=raw))
    result = await analyze_investment_threshold(case, pack, ctx)
    assert raw == before
    assert type(result) is RoleResult
    assert RoleResult.model_validate(result.model_dump(mode="json")) == result
    ctx.model.generate_structured.assert_awaited_once()
    args = ctx.model.generate_structured.call_args.args
    assert args[0] == "investment_threshold" and args[2] is ThresholdAnalysis
    data = result.section_content[0].structured_data["investment_threshold"]
    assert data["gates"] == before["gates"]
    assert data["synthetic"] and data["snapshot_id"] == pack.snapshot_id
    assert data["claim_evidence_links"] == {"investment_threshold.result": []}
    assert result.claims and result.risks
    assert "claims" not in data and "risks" not in data
    assert all(any(f"{r} context absent" in gap for gap in result.unknowns) for r in ROLES)


@pytest.mark.asyncio
async def test_adapter_and_response_validation():
    case, pack, ctx = inputs()
    with pytest.raises(RuntimeError): await analyze_investment_threshold(case, pack, ctx)
    d = output()
    d["gates"][0]["status"] = "met"
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(return_value=d))
    with pytest.raises(ValueError): await analyze_investment_threshold(case, pack, ctx)
    ctx.model.generate_structured.assert_awaited_once()


def test_gap_collection_deduplicates_and_keeps_checks():
    gaps = identify_threshold_gaps(validate(output()))
    assert gaps.count("Need applicable study") == 1
    assert any("gap_now" in gap and "Assay result and controls" in gap for gap in gaps)


def test_historical_market_dates_are_not_run_metadata():
    case, pack, ctx = inputs()
    ctx.as_of_date = date(2026, 10, 8)
    market = upstream("market").model_dump(mode="json")
    market["section_content"][0]["structured_data"]["market"]["records"][0]["as_of_date"] = "2020-01-01"
    payload = prepare_threshold_inputs(case, pack, ctx, market=market)
    assert payload["upstream_context"]["market"] == market


@pytest.mark.parametrize("filename,role", [("investment-synthetic.json", "investment"),
    ("partnerships-synthetic.json", "partnerships"), ("ip-licensing-synthetic.json", "ip_licensing")])
def test_real_upstream_serialization_examples(filename, role):
    root = Path(__file__).resolve().parents[6]
    fixtures = json.loads((root / "docs" / "examples" / filename).read_text())
    if isinstance(fixtures, dict):
        fixtures = fixtures.values()
    for fixture in fixtures:
        case = CaseInput.model_validate(fixture["case"])
        pack = EvidencePack.model_validate(fixture["pack"])
        context = dict(fixture.get("context", dict(case_id="case-test", run_id="run-test",
            snapshot_id=pack.snapshot_id, as_of_date=case.as_of_date, mode="evidence_only")))
        if isinstance(context.get("as_of_date"), str):
            context["as_of_date"] = date.fromisoformat(context["as_of_date"])
        ctx = RunContext(**context)
        payload = prepare_threshold_inputs(case, pack, ctx, **{role: fixture["result"]})
        assert payload["upstream_context"][role] == fixture["result"]


@pytest.mark.parametrize("value", ["invalid-date", 42])
def test_invalid_context_date(value):
    case, pack, ctx = inputs()
    ctx.as_of_date = value
    with pytest.raises(ValueError): prepare_threshold_inputs(case, pack, ctx)


def test_iso_context_date_normalized_without_mutation():
    case, pack, ctx = inputs()
    ctx.as_of_date = "2026-10-08"
    assert prepare_threshold_inputs(case, pack, ctx)["as_of_date"] == "2026-10-08"
    assert ctx.as_of_date == "2026-10-08"


@pytest.mark.asyncio
async def test_upstream_unknowns_and_full_financial_data_carried_forward():
    case, pack, ctx = inputs()
    investment = upstream("investment")
    investment.section_content[0].structured_data["investment"]["calculated_financials"] = {
        "subtotal": 100, "cost_coverage": "partial", "unknowns": ["Full development budget unknown"]}
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(return_value=output()))
    result = await analyze_investment_threshold(case, pack, ctx, investment=investment)
    data = result.section_content[0].structured_data["investment_threshold"]
    assert data["upstream_context"]["investment"] == investment.model_dump(mode="json")
    assert "investment: Applicability pending" in result.unknowns


def test_synthetic_upstream_marker_preserved():
    case, pack, ctx = inputs()
    pack.synthetic = False
    pack.sources[0].synthetic = False
    market = upstream("market")
    market.section_content[0].structured_data["market"]["synthetic"] = True
    assert prepare_threshold_inputs(case, pack, ctx, market=market)["synthetic"]


@pytest.mark.asyncio
@pytest.mark.parametrize("with_feedback", [False, True])
async def test_current_r2_adapter_prompt_and_complete_data_flow(with_feedback):
    from vic.config import Settings
    from vic.llm import ProviderResponse, StructuredLlm
    from vic.prompts import load_prompt

    calls = []

    class OfflineProvider:
        name = "offline-threshold-test"

        async def complete(self, **request):
            calls.append(request)
            return ProviderResponse(json.dumps(output()), input_tokens=100, output_tokens=50)

    case, pack, ctx = inputs()
    contexts = {role: upstream(role) for role in ROLES}
    if with_feedback:
        ctx.feedback["investment_threshold"] = [{"reason": "Review criterion applicability"}]
    ctx.model = StructuredLlm(OfflineProvider(), Settings(_env_file=None,
        llm_max_retries=0, llm_max_repairs=0))
    result = await analyze_investment_threshold(case, pack, ctx, **contexts)
    assert len(calls) == 1
    prompt = load_prompt("investment_threshold")
    assert prompt.path.name == "investment_threshold.md"
    assert prompt.text in calls[0]["system"]
    assert '"InvestmentGate"' in calls[0]["system"]
    sent = json.loads(calls[0]["messages"][0]["content"])
    assert sent["sources"] == [s.model_dump(mode="json") for s in pack.sources]
    assert sent["evidence"][0]["excerpt"] == pack.evidence[0].excerpt
    assert all(sent["context_availability"].values())
    assert sent["upstream_context"] == {r: value.model_dump(mode="json") for r, value in contexts.items()}
    if with_feedback:
        assert "Review criterion applicability" in calls[0]["messages"][1]["content"]
    data = result.section_content[0].structured_data["investment_threshold"]
    assert data["upstream_context"] == sent["upstream_context"]
    assert data["gates"] == output()["gates"]
    assert all(f"{r}: Applicability pending" in result.unknowns for r in ROLES)
    assert ctx.trace.usage[0]["prompt_id"] == "investment_threshold"
    assert ctx.trace.usage[0]["prompt_version"] == prompt.version
    assert ctx.trace.usage[0]["outcome"] == "ok"
    assert RoleResult.model_validate(result.model_dump(mode="json")) == result


@pytest.mark.asyncio
async def test_current_r2_adapter_does_not_bypass_semantic_structure_checks():
    from vic.config import Settings
    from vic.llm import ProviderResponse, StructuredLlm

    class OfflineProvider:
        name = "offline-threshold-test"

        async def complete(self, **request):
            invalid = output()
            invalid["gates"][0]["status"] = "met"
            return ProviderResponse(json.dumps(invalid), input_tokens=100, output_tokens=50)

    case, pack, ctx = inputs()
    ctx.model = StructuredLlm(OfflineProvider(), Settings(_env_file=None,
        llm_max_retries=0, llm_max_repairs=0))
    with pytest.raises(ValueError, match="Met gate requires"):
        await analyze_investment_threshold(case, pack, ctx)
