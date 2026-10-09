"""Offline coverage, decision guards and full upstream data preservation."""
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from test_failure_miner import inputs, upstream
from vic.agents.business.chair import (
    ROLES,
    ChairAnalysis,
    ChairResult,
    analyze_chair,
    prepare_chair_inputs,
    validate_chair_result,
)
from vic.contracts import AuditResult, Importance, RoleId, RoleResult, SectionContent, SupportStatus


@pytest.fixture(autouse=True)
def _canonical_transport_contract(monkeypatch):
    # These fixtures exercise the uncompressed transport/validation contract.
    # Default bounded execution is covered by test_full_workflow/test_request_protocol.
    monkeypatch.setenv("NODE_INITIAL_REQUEST_BYTES", "10000000")
    monkeypatch.setenv("NODE_REQUEST_MAX_BYTES", "10000000")


def reason(basis="unknown", cid=None):
    return {"text": "Evidence applicability requires review", "basis": basis,
        "claim_ids": [cid] if cid else [], "assumptions": ["Prospective assumption"] if basis == "hypothesis" else [],
        "unknowns": ["Result unavailable"] if basis == "unknown" else [],
        "evidence_weight": "No independent applicable evidence establishes benefit"}


def output():
    return {"summary": "Committee requires diligence before financing", "recommendation": "Conditional",
        "rationale": reason(), "claims": [], "arguments": [{"id": "potential", "direction": "for", "reason": reason(),
            "decision_impact": "Potential benefit requires demonstration", "decisive": False},
            {"id": "gap", "direction": "against", "reason": reason(), "decision_impact": "Do not commit before evidence", "decisive": True}],
        "conditions": [{"id": "verification", "requirement": "Obtain applicable evidence", "rationale": reason(),
            "verification_method": "Independent data review", "evidence_needed": "Validated applicable results",
            "pass_if": "Validated results satisfy agreed criteria", "fail_if": "Validated adverse result",
            "inconclusive_if": "Invalid controls", "timing": "before_investment", "failure_action": "Withhold funding"}],
        "conflicts": [], "conflict_limitations": ["No supplied conclusions to compare"], "key_risks": [],
        "critical_unknowns": [{"id": "benefit", "description": "Clinical benefit unknown", "role_ids": ["clinical"],
            "decision_impact": "Funding benefit uncertain", "blocks_invest": True}],
        "change_triggers": [{"id": "adverse", "result_or_new_evidence": "Validated unacceptable toxicity",
            "verification_method": "Review controlled applicable study", "rationale": reason(), "resulting_recommendation": "Do Not Invest"}],
        "questions": [{"id": f"check_{i}", "rank": i, "role_ids": [ROLES[i-1]], "argument_ids": ["gap"], "risk_ids": [],
            "unknown_ids": ["benefit"], "condition_ids": ["verification"], "conflict_ids": [],
            "question": f"Verify applicable decision evidence in domain {ROLES[i-1]}?", "why_it_matters": reason(),
            "evidence_needed": "Validated domain results", "method": "Independent specialist review",
            "decision_if_positive": "Consider release after other gates", "decision_if_negative": "Withhold capital",
            "inconclusive_if": "Repeat with valid controls"} for i in range(1, 6)],
        "domain_reviews": [{"role_id": r, "assessment": reason(), "dispositions": []} for r in ROLES],
        "unknowns": ["Program applicability"], "limitations": ["Synthetic offline case"]}


def prepared(contexts=None, audit=None):
    case, pack, ctx = inputs()
    return case, pack, ctx, prepare_chair_inputs(case, pack, ctx, **(contexts or {}), audit=audit)


def validate(raw, contexts=None, audit=None):
    case, pack, ctx, payload = prepared(contexts, audit)
    analysis = ChairAnalysis.model_validate(raw)
    validate_chair_result(analysis, case, pack, payload)
    return analysis


def complete():
    contexts = {r: upstream(r) for r in ROLES}
    for r, result in contexts.items():
        result.section_content[0].structured_data[r].update(
            plan={"full_plan": [1, 2, 3], "unknowns": ["Nested plan gap"]},
            calculated_financials={"npv": 42, "sensitivity": {"downside": -100}},
            questions=[{"id": "candidate", "question": f"Verify {r}?", "unknowns": ["Nested question gap"]}])
    raw = output()
    payload = prepared(contexts)[3]
    for review in raw["domain_reviews"]:
        review["dispositions"] = [{"item_id": i["id"], "disposition": "considered", "rationale": "Affects diligence decision",
            "argument_ids": ["gap"], "question_ids": [], "condition_ids": []} for i in payload["input_inventory"][review["role_id"]]]
    return raw, contexts


def invest():
    raw, contexts = complete()
    raw.update(recommendation="Invest", conditions=[], critical_unknowns=[])
    raw["rationale"] = reason("documented", "science.result")
    for review in raw["domain_reviews"]:
        review["assessment"] = reason("documented", f"{review['role_id']}.result")
    raw["arguments"][0].update(reason=reason("documented", "science.result"), decisive=True)
    for q in raw["questions"]:
        q.update(condition_ids=[], unknown_ids=[])
    raw["change_triggers"][0]["resulting_recommendation"] = "Conditional"
    return raw, contexts


def test_requirements_sparse_and_complete():
    assert validate(output()).recommendation == "Conditional"
    raw, contexts = complete()
    validate(raw, contexts)
    assert len(raw["questions"]) == 5


@pytest.mark.parametrize("field", list(output()))
def test_required_output_fields(field):
    raw = output(); del raw[field]
    with pytest.raises(ValidationError): validate(raw)


@pytest.mark.parametrize("field", list(output()["conditions"][0]))
def test_required_condition_fields(field):
    raw = output(); del raw["conditions"][0][field]
    with pytest.raises(ValidationError): validate(raw)


@pytest.mark.parametrize("field", list(output()["questions"][0]))
def test_required_question_fields(field):
    raw = output(); del raw["questions"][0][field]
    with pytest.raises(ValidationError): validate(raw)


@pytest.mark.parametrize("defect", ["extra", "blank", "recommendation", "no_conditions", "unconditional_conditions",
    "no_for", "no_decisive", "documented_unknown", "unknown_claim", "hypothesis_assumptions", "unknown_gaps",
    "question_count", "too_many", "rank", "duplicate_question", "question_link", "dangling_link",
    "condition_uncovered", "unknown_uncovered", "duplicate_domain", "missing_domain", "absent_domain_fact",
    "conflicts_unexplained", "change_same", "duplicate_trigger", "risk_uncovered", "claim_namespace",
    "claim_evidence", "claim_scope", "unverified_assumptions", "unknown_disposition", "dropped_input", "duplicate_input",
    "considered_unlinked", "deferred_linked", "duplicate_argument"])
def test_reject_invalid_outputs(defect):
    raw, contexts = complete()
    q = raw["questions"][0]
    if defect == "extra": raw["extra"] = 1
    if defect == "blank": raw["summary"] = " "
    if defect == "recommendation": raw["recommendation"] = "Maybe"
    if defect == "no_conditions": raw["conditions"] = []
    if defect == "unconditional_conditions": raw["recommendation"] = "Invest"
    if defect == "no_for": raw["arguments"][0]["direction"] = "against"
    if defect == "no_decisive": raw["arguments"][1]["decisive"] = False
    if defect == "documented_unknown": raw["rationale"] = reason("documented", "science.result"); contexts["science"].claims[0].support_status = SupportStatus.UNVERIFIED
    if defect == "unknown_claim": raw["rationale"]["claim_ids"] = ["chair.missing"]
    if defect == "hypothesis_assumptions": raw["rationale"].update(basis="hypothesis", assumptions=[])
    if defect == "unknown_gaps": raw["rationale"]["unknowns"] = []
    if defect == "question_count": raw["questions"].pop()
    if defect == "too_many": raw["questions"] *= 3
    if defect == "rank": q["rank"] = 2
    if defect == "duplicate_question": raw["questions"][1]["question"] = q["question"]
    if defect == "question_link": q.update(argument_ids=[], unknown_ids=[], condition_ids=[])
    if defect == "dangling_link": q["risk_ids"] = ["missing"]
    if defect == "condition_uncovered":
        for row in raw["questions"]: row["condition_ids"] = []
    if defect == "unknown_uncovered":
        for row in raw["questions"]: row["unknown_ids"] = []
    if defect == "duplicate_domain": raw["domain_reviews"][1] = deepcopy(raw["domain_reviews"][0])
    if defect == "missing_domain": raw["domain_reviews"].pop()
    if defect == "absent_domain_fact": contexts["science"] = None; raw["domain_reviews"][0].update(assessment=reason("hypothesis"), dispositions=[])
    if defect == "conflicts_unexplained": raw["conflict_limitations"] = []
    if defect == "change_same": raw["change_triggers"][0]["resulting_recommendation"] = "Conditional"
    if defect == "duplicate_trigger": raw["change_triggers"] *= 2
    if defect == "risk_uncovered": raw["key_risks"] = [{"id": "toxicity", "description": reason(), "priority": "critical", "impact": "Safety blocker", "next_check": "Study"}]
    if defect.startswith("claim_") or defect == "unverified_assumptions":
        raw["claims"] = [{"id": "chair.new", "text": "Hypothetical result", "provenance": "ai", "support_status": "unverified",
            "assumptions": ["Assumption"], "evidence_ids": [], "scope": "approach", "importance": "major"}]
        c = raw["claims"][0]
        if defect == "claim_namespace": c["id"] = "market.new"
        if defect == "claim_evidence": c["evidence_ids"] = ["missing"]
        if defect == "claim_scope": c["scope"] = "program"
        if defect == "unverified_assumptions": c["assumptions"] = []
    d = raw["domain_reviews"][0]["dispositions"]
    if defect == "unknown_disposition": d[0]["item_id"] = "missing"
    if defect == "dropped_input": d.pop()
    if defect == "duplicate_input": d.append(deepcopy(d[0]))
    if defect == "considered_unlinked": d[0]["argument_ids"] = []
    if defect == "deferred_linked": d[0]["disposition"] = "deferred"
    if defect == "duplicate_argument": raw["arguments"].append(deepcopy(raw["arguments"][0]))
    with pytest.raises((ValueError, ValidationError)): validate(raw, contexts)


@pytest.mark.parametrize("defect", ["role", "snapshot", "nested_snapshot", "date", "evidence", "risk_ref", "section_ref", "audit_claim", "audit_evidence", "ctx_snapshot", "ctx_date"])
def test_input_guards(defect):
    raw, contexts = complete()
    case, pack, ctx = inputs(); audit = None
    result = contexts["science"]
    if defect == "role": result.role_id = RoleId.MARKET
    if defect == "snapshot": result.section_content[0].structured_data["science"]["snapshot_id"] = "other"
    if defect == "nested_snapshot": result.section_content[0].structured_data["science"]["plan"]["snapshot_id"] = "other"
    if defect == "date":
        ctx.as_of_date = "2026-10-09"; result.section_content[0].structured_data["science"]["as_of_date"] = "2026-10-08"
    if defect == "evidence": result.section_content[0].structured_data["science"]["plan"]["evidence_ids"] = ["missing"]
    if defect == "risk_ref": result.risks[0].claim_ids = ["science.missing"]
    if defect == "section_ref": result.section_content[0].claim_ids = ["science.missing"]
    if defect == "audit_claim": audit = {"unresolved_critical_claim_ids": ["science.missing"]}
    if defect == "audit_evidence": audit = {"findings": [{"claim_id": "science.result", "verdict": "supported", "reason": "Review", "evidence_ids": ["missing"], "blocking": False}]}
    if defect == "ctx_snapshot": ctx.snapshot_id = "other"
    if defect == "ctx_date": ctx.as_of_date = "invalid"
    with pytest.raises(ValueError): prepare_chair_inputs(case, pack, ctx, **contexts, audit=audit)


def test_invest_guards_and_adverse_decision():
    raw, contexts = invest()
    case, pack, ctx = inputs(); ctx.as_of_date = "2026-10-09"
    payload = prepare_chair_inputs(case, pack, ctx, **contexts, audit={"findings": [{"claim_id": "science.result", "verdict": "supported", "reason": "Reviewed", "evidence_ids": ["e1"], "blocking": False}]})
    validate_chair_result(ChairAnalysis.model_validate(raw), case, pack, payload)
    for change in ("audit", "date", "missing", "blocked", "reason"):
        p, a = deepcopy(payload), deepcopy(raw)
        if change == "audit": p["audit"] = None
        if change == "date": p["as_of_date"] = None
        if change == "missing": p["context_availability"]["clinical"] = False
        if change == "blocked": p["audit"]["unresolved_critical_claim_ids"] = ["science.result"]
        if change == "reason": a["rationale"] = reason()
        with pytest.raises(ValueError): validate_chair_result(ChairAnalysis.model_validate(a), case, pack, p)
    a = output(); a.update(recommendation="Do Not Invest", conditions=[])
    for q in a["questions"]: q["condition_ids"] = []
    a["change_triggers"][0]["resulting_recommendation"] = "Conditional"
    with pytest.raises(ValueError): validate(a)
    a["rationale"] = reason("documented", "chair.adverse")
    a["arguments"][1]["reason"] = reason("documented", "chair.adverse")
    a["claims"] = [{"id": "chair.adverse", "text": "Observed adverse result", "provenance": "source", "support_status": "supported",
        "evidence_ids": ["e1"], "scope": "approach", "importance": "critical"}]
    validate(a)


def test_audit_blocks_evidence_laundering():
    raw, contexts = complete(); raw["rationale"] = reason("documented", "science.result")
    for verdict, blocking in (("mixed", False), ("unverified", False), ("supported", True)):
        with pytest.raises(ValueError): validate(raw, contexts, {"findings": [{"claim_id": "science.result",
            "verdict": verdict, "reason": "Audit issue", "evidence_ids": ["e1"], "blocking": blocking}]})


@pytest.mark.asyncio
async def test_full_data_flow_and_json_roundtrip():
    raw, contexts = complete(); case, pack, ctx = inputs()
    ctx.model = type("Model", (), {"generate_structured": AsyncMock(return_value=raw)})()
    result = await analyze_chair(case, pack, ctx, **contexts, audit=AuditResult())
    prompt, payload, schema, actual_ctx = ctx.model.generate_structured.call_args.args
    assert prompt == "chair" and schema is ChairAnalysis and actual_ctx is ctx
    for role in ROLES:
        assert payload["upstream_context"][role] == contexts[role].model_dump(mode="json")
        assert payload["upstream_context"][role]["section_content"][0]["structured_data"][role]["calculated_financials"]["sensitivity"]["downside"] == -100
    data = result.role_result.section_content[0].structured_data["chair"]
    assert data["upstream_context"] == payload["upstream_context"]
    assert data["input_inventory"] == payload["input_inventory"]
    assert data["committee_decision"] == result.decision.model_dump(mode="json")
    assert len(result.decision.questions) == 5
    assert "science: Nested plan gap" in result.role_result.unknowns
    assert "failure_miner: Nested question gap" in result.role_result.unknowns
    assert data["claim_evidence_links"]["investment.result"] == ["e1"]
    assert data["evidence_source_links"]["e1"] == "s1"
    assert ChairResult.model_validate_json(result.model_dump_json()) == result
    assert json.loads(result.model_dump_json())["decision"]["recommendation"] == "Conditional"


@pytest.mark.asyncio
async def test_missing_adapter_and_sparse_context():
    case, pack, ctx = inputs()
    with pytest.raises(RuntimeError): await analyze_chair(case, pack, ctx)
    ctx.model = type("Model", (), {"generate_structured": AsyncMock(return_value=output())})()
    result = await analyze_chair(case, pack, ctx)
    assert all(f"{r}: upstream context absent" in result.role_result.unknowns for r in ROLES)


def test_discovery_unchanged_and_prompt_schema():
    from vic.modules import discover
    from vic.prompts import load_prompt
    prompt = load_prompt("chair")
    assert "not the number" in prompt.text
    assert prompt.path.name == "chair.md"
    assert not any(module.endswith("chair") for module, fn in discover()["synthesize_committee"])
    assert ChairAnalysis.model_json_schema()["additionalProperties"] is False


@pytest.mark.asyncio
async def test_real_gateway_adapter_feedback_trace_and_all_contexts():
    import httpx
    from vic.config import Settings
    from vic.llm import OpenAICompatibleProvider, StructuredLlm
    from vic.prompts import load_prompt
    raw, contexts = complete(); requests = []
    def handler(request):
        body = json.loads(request.content); requests.append(body)
        assert str(request.url) == "https://chair.example/v1/chat/completions"
        assert load_prompt("chair").text in body["messages"][0]["content"]
        payload = json.loads(body["messages"][1]["content"])
        assert payload["upstream_context"] == {r: v.model_dump(mode="json") for r, v in contexts.items()}
        assert "Review evidence weight" in body["messages"][2]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(raw)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}})
    settings = Settings(_env_file=None, llm_provider="openai", llm_api_key="synthetic-test-only",
        llm_base_url="https://chair.example/v1", llm_model="synthetic-model", llm_max_retries=0, llm_max_repairs=0)
    case, pack, ctx = inputs(); ctx.feedback["chair"] = [{"reason": "Review evidence weight"}]
    ctx.model = StructuredLlm(OpenAICompatibleProvider(settings, transport=httpx.MockTransport(handler)), settings)
    result = await analyze_chair(case, pack, ctx, **contexts)
    assert len(requests) == 1 and result.decision.recommendation == "Conditional"
    assert ctx.trace.usage[-1]["prompt_version"] == load_prompt("chair").version
    assert ctx.trace.usage[-1]["input_tokens"] == 100


@pytest.mark.asyncio
async def test_r3_audit_and_report_preserve_full_chair_and_canonical_risks():
    from vic.contracts import Report
    from vic.evidence.audit import audit_claims
    from vic.integrity import assert_report
    from vic.report_builder import SECTION_OWNERS, build_report
    raw, contexts = complete()
    raw["claims"] = [{"id": "chair.caution", "text": "Possible limitation needs review", "provenance": "ai",
        "support_status": "unverified", "assumptions": ["Applicable results absent"], "evidence_ids": [], "scope": "approach", "importance": "major"}]
    raw["key_risks"] = [{"id": "execution", "description": reason("documented", "investment.result"),
        "priority": "major", "impact": "Execution risk", "next_check": "Review implementation"}]
    raw["conflicts"] = [{"id": "tradeoff", "topic": "Applicability", "role_ids": ["science", "investment"],
        "upstream_claim_ids": ["science.result", "investment.result"], "competing_conclusions": "Different implications",
        "resolution": reason(), "decision_impact": "Withhold pending review", "status": "unresolved"}]
    raw["questions"][0]["conflict_ids"] = ["tradeoff"]
    case, pack, ctx = inputs(); ctx.model = type("Model", (), {"generate_structured": AsyncMock(return_value=raw)})()
    result = await analyze_chair(case, pack, ctx, **contexts)
    audit = audit_claims(result.decision.additional_claims, pack)
    assert audit.findings[0].verdict == "unverified"
    original_investment = contexts["investment"].model_dump(mode="json")
    roles = list(contexts.values())
    for role in roles:
        role.section_content.extend([{"key": k, "summary": "Synthetic section"} for k, owner in SECTION_OWNERS.items()
            if owner == role.role_id])
        role.section_content = [SectionContent.model_validate(s) for s in role.section_content]
    roles.append(result.role_result)
    claims = [c for role in roles for c in role.claims]
    report = build_report(case=case, pack=pack, roles=roles, decision=result.decision, claims=claims,
        case_id=ctx.case_id, run_id=ctx.run_id, report_id="chair-report", version=1, synthetic=True)
    assert_report(report)
    restored = Report.model_validate_json(report.model_dump_json())
    assert restored.roles[-1] == result.role_result
    assert restored.diligence_questions == result.decision.questions
    assert restored.decision_conditions == result.decision.conditions
    assert restored.disagreements == result.decision.disagreements
    assert next(r for r in restored.risks if r.id == "chair.execution").claim_ids == ["investment.result"]
    assert restored.roles[-1].section_content[0].structured_data["chair"]["upstream_context"]["investment"] == original_investment


@pytest.mark.parametrize("filename,role", [("investment-synthetic.json", "investment"),
    ("partnerships-synthetic.json", "partnerships"), ("ip-licensing-synthetic.json", "ip_licensing")])
def test_existing_upstream_examples(filename, role):
    from pathlib import Path

    from vic.contracts import CaseInput, EvidencePack, RunContext
    root = Path(__file__).resolve().parents[6]
    fixtures = json.loads((root / "docs" / "examples" / filename).read_text())
    for fixture in fixtures.values() if isinstance(fixtures, dict) else fixtures:
        case = CaseInput.model_validate(fixture["case"]); pack = EvidencePack.model_validate(fixture["pack"])
        context = fixture.get("context", {"case_id": "case", "run_id": "run", "snapshot_id": pack.snapshot_id,
            "as_of_date": case.as_of_date, "mode": "evidence_only"})
        payload = prepare_chair_inputs(case, pack, RunContext(**context), **{role: fixture["result"]})
        assert payload["upstream_context"][role] == fixture["result"]


@pytest.mark.asyncio
async def test_real_failure_and_threshold_outputs_reach_chair_without_loss():
    from test_failure_miner import output as failure_output
    from test_investment_threshold import output as threshold_output
    from vic.agents.business.failure_miner import analyze_failure_miner
    from vic.agents.business.investment_threshold import analyze_investment_threshold
    case, pack, ctx = inputs()
    ctx.model = type("Model", (), {"generate_structured": AsyncMock(return_value=failure_output())})()
    failure = await analyze_failure_miner(case, pack, ctx)
    # Threshold fixture uses different snapshot; its output is validated against the same pack here.
    ctx.model.generate_structured.return_value = threshold_output()
    threshold = await analyze_investment_threshold(case, pack, ctx)
    contexts = {"failure_miner": failure, "investment_threshold": threshold}
    payload = prepare_chair_inputs(case, pack, ctx, **contexts)
    raw = output()
    for review in raw["domain_reviews"]:
        review["dispositions"] = [{"item_id": i["id"], "disposition": "considered", "rationale": "Decision evidence",
            "argument_ids": ["gap"], "question_ids": [], "condition_ids": []} for i in payload["input_inventory"][review["role_id"]]]
    ctx.model.generate_structured.return_value = raw
    result = await analyze_chair(case, pack, ctx, **contexts)
    data = result.role_result.section_content[0].structured_data["chair"]
    assert data["upstream_context"]["failure_miner"] == failure.model_dump(mode="json")
    assert data["upstream_context"]["investment_threshold"] == threshold.model_dump(mode="json")


@pytest.mark.parametrize("defect", ["no_audit_coverage", "critical_unverified", "critical_unaudited", "unknown_domain", "audit_blocker"])
def test_invest_cannot_bypass_evidence_checks(defect):
    raw, contexts = invest(); case, pack, ctx = inputs(); ctx.as_of_date = "2026-10-09"
    audit = {"findings": [{"claim_id": "science.result", "verdict": "supported", "reason": "Checked", "evidence_ids": ["e1"], "blocking": False}]}
    if defect == "no_audit_coverage": audit = {}
    if defect in ("critical_unverified", "critical_unaudited"):
        contexts["clinical"].claims[0].importance = Importance.CRITICAL
        if defect == "critical_unverified": contexts["clinical"].claims[0].support_status = SupportStatus.UNVERIFIED
    if defect == "unknown_domain": raw["domain_reviews"][0]["assessment"] = reason()
    if defect == "audit_blocker": audit["findings"][0]["blocking"] = True
    payload = prepare_chair_inputs(case, pack, ctx, **contexts, audit=audit)
    with pytest.raises(ValueError): validate_chair_result(ChairAnalysis.model_validate(raw), case, pack, payload)


def test_upstream_json_inputs_and_immutable_payload():
    raw, contexts = complete()
    before = {r: v.model_dump(mode="json") for r, v in contexts.items()}
    payload = prepared(before)[3]
    assert payload["upstream_context"] == before
    assert contexts["investment"].model_dump(mode="json") == before["investment"]
    assert any(i["id"] == "investment/position" for i in payload["input_inventory"]["investment"])
    assert all(set(i) == {"id", "kind"} for entries in payload["input_inventory"].values() for i in entries)


def test_invest_rejects_new_unverified_critical_chair_claim():
    raw, contexts = invest(); case, pack, ctx = inputs(); ctx.as_of_date = "2026-10-09"
    raw["claims"] = [{"id": "chair.critical", "text": "Critical unknown", "provenance": "ai", "support_status": "unknown",
        "assumptions": ["Missing applicable result"], "evidence_ids": [], "scope": "approach", "importance": "critical"}]
    payload = prepare_chair_inputs(case, pack, ctx, **contexts, audit={"findings": [{"claim_id": "science.result",
        "verdict": "supported", "reason": "Checked", "evidence_ids": ["e1"], "blocking": False}]})
    with pytest.raises(ValueError, match="including new chair"):
        validate_chair_result(ChairAnalysis.model_validate(raw), case, pack, payload)


# These are offline regression tests of the real node/adapter/report path.
# Provider responses are scripted: they do not evaluate live LLM reasoning quality.
def _chair_revision_inputs(update=None):
    from datetime import date

    from vic.contracts import Claim, Evidence, Risk, Source
    from vic.report_builder import SECTION_OWNERS

    _, contexts = complete()
    case, pack, ctx = inputs()
    ctx.as_of_date = date(2026, 10, 9)
    ctx.run_id = "chair-baseline" if update is None else f"chair-{update}"
    for role, result in contexts.items():
        result.section_content.extend(
            SectionContent(key=key, summary="Synthetic specialist section")
            for key, owner in SECTION_OWNERS.items() if owner == result.role_id
        )
        result.section_content[0].structured_data[role]["as_of_date"] = "2026-10-09"
    if update is not None:
        pack.snapshot_id = f"chair-{update}-snapshot"
        ctx.snapshot_id = pack.snapshot_id
        pack.sources.append(Source(id="s2", title=f"Synthetic {update} update",
            type="synthetic", retrieved_at="2026-10-09T00:00:00Z", synthetic=True,
            content_hash="sha256:" + "b" * 64))
        excerpt = (
            "Synthetic controlled study of the assessed approach confirms unacceptable toxicity."
            if update == "safety" else
            "Synthetic administrative update changes the registry contact address only; "
            "no scientific, safety, clinical or financial results change."
        )
        pack.evidence.append(Evidence(id="e2", source_id="s2", scope="approach",
            excerpt=excerpt, locator="update", limitations=["Synthetic test fixture only"]))
        for role, result in contexts.items():
            result.section_content[0].structured_data[role]["snapshot_id"] = pack.snapshot_id
        if update == "safety":
            clinical = contexts["clinical"]
            clinical.claims.append(Claim(id="clinical.toxicity", text=excerpt,
                provenance="source", support_status="supported", evidence_ids=["e2"],
                scope="approach", importance="critical"))
            clinical.risks.append(Risk(id="clinical.toxicity_risk", description=excerpt,
                priority="critical", claim_ids=["clinical.toxicity"],
                impact="Unacceptable safety blocks financing", next_check="Review controlled study"))
            clinical.section_content[0].claim_ids.append("clinical.toxicity")
    return case, pack, ctx, contexts


def _chair_revision_response(case, pack, ctx, contexts, audit, *, adverse=False):
    raw = output()
    if adverse:
        safety = reason("documented", "clinical.toxicity")
        safety.update(text="Do not invest: the new controlled study confirms unacceptable toxicity.",
            evidence_weight="The new applicable controlled safety result is decisive; "
            "other roles repeating earlier favorable evidence cannot outweigh it.")
        raw.update(summary="New safety evidence changes Conditional to Do Not Invest",
            recommendation="Do Not Invest", rationale=safety, conditions=[])
        raw["arguments"][1].update(reason=deepcopy(safety),
            decision_impact="The newly documented safety barrier prevents funding")
        raw["key_risks"] = [{"id": "toxicity", "description": deepcopy(safety), "priority": "critical",
            "impact": "Safety barrier prevents investment", "next_check": "Independently review the safety study"}]
        raw["change_triggers"][0].update(result_or_new_evidence="Validated evidence overturns the safety finding",
            resulting_recommendation="Conditional", rationale=reason("hypothesis"))
        for q in raw["questions"]:
            q["condition_ids"] = []
        raw["questions"][0].update(risk_ids=["toxicity"], question="Does independent review confirm the toxicity?",
            why_it_matters=deepcopy(safety), evidence_needed="Controlled safety study and raw data",
            decision_if_positive="Keep Do Not Invest while toxicity remains confirmed",
            decision_if_negative="Reconsider Conditional if the safety finding is overturned")
    payload = prepare_chair_inputs(case, pack, ctx, **contexts, audit=audit)
    for review in raw["domain_reviews"]:
        review["dispositions"] = [{"item_id": item["id"], "disposition": "considered",
            "rationale": "Included in the decision and follow-up diligence", "argument_ids": ["gap"],
            "question_ids": [], "condition_ids": []} for item in payload["input_inventory"][review["role_id"]]]
        if adverse and review["role_id"] == "clinical":
            review["assessment"] = deepcopy(raw["rationale"])
    return raw


async def _run_chair_revision_pair(update):
    from vic.config import Settings
    from vic.evidence.audit import audit_claims
    from vic.llm import ProviderResponse, StructuredLlm

    calls = []
    runs = []
    for variant in (None, update):
        case, pack, ctx, contexts = _chair_revision_inputs(variant)
        audit = audit_claims([c for result in contexts.values() for c in result.claims], pack)
        assert not audit.unresolved_critical_claim_ids
        raw = _chair_revision_response(case, pack, ctx, contexts, audit, adverse=variant == "safety")
        # Capture through the actual R2 adapter, rather than mocking analyze_chair.
        class ScriptedProvider:
            name = "offline-chair-revision"

            async def complete(self, **request):
                payload = json.loads(request["messages"][0]["content"])
                calls.append(payload)
                return ProviderResponse(json.dumps(raw), 100, 50)

        ctx.model = StructuredLlm(ScriptedProvider(), Settings(
            _env_file=None, llm_max_retries=0, llm_max_repairs=0))
        result = await analyze_chair(case, pack, ctx, **contexts, audit=audit)
        assert calls[-1]["snapshot_id"] == pack.snapshot_id
        assert calls[-1]["upstream_context"] == {
            role: upstream_result.model_dump(mode="json") for role, upstream_result in contexts.items()
        }
        runs.append((case, pack, ctx, contexts, result))
    assert len(calls) == 2
    assert {e["id"] for e in calls[0]["evidence"]} == {"e1"}
    assert {e["id"] for e in calls[1]["evidence"]} == {"e1", "e2"}
    return runs, calls


def _chair_revision_report(run, *, parent=None):
    from vic.contracts import Report
    from vic.integrity import assert_report, check_revision
    from vic.report_builder import build_report

    case, pack, ctx, contexts, result = run
    roles = [*contexts.values(), result.role_result]
    report = build_report(case=case, pack=pack, roles=roles, decision=result.decision,
        claims=[claim for role in roles for claim in role.claims], case_id=ctx.case_id,
        run_id=ctx.run_id, report_id=ctx.run_id, version=2 if parent else 1,
        parent=parent, synthetic=True)
    assert_report(report)
    if parent is not None:
        assert check_revision(parent, report) == []
    return Report.model_validate_json(report.model_dump_json())


@pytest.mark.asyncio
async def test_decisive_safety_evidence_changes_chair_recommendation_and_report():
    """Scripted before/after decisions preserve the new decisive evidence and safety risk."""
    runs, calls = await _run_chair_revision_pair("safety")
    before, after = (run[-1] for run in runs)
    before_json = before.model_dump_json()
    assert before.decision.recommendation == "Conditional"
    assert before.decision.conditions
    assert after.decision.recommendation == "Do Not Invest"
    assert not after.decision.conditions
    data = after.role_result.section_content[0].structured_data["chair"]
    assert data["rationale"]["claim_ids"] == ["clinical.toxicity"]
    assert data["claim_evidence_links"]["clinical.toxicity"] == ["e2"]
    assert data["evidence_source_links"]["e2"] == "s2"
    assert next(e for e in data["evidence"] if e["id"] == "e2")["excerpt"] == calls[1]["evidence"][1]["excerpt"]
    assert "new controlled study" in after.decision.rationale
    assert next(r for r in after.decision.risks if r.id == "chair.toxicity").claim_ids == ["clinical.toxicity"]
    assert any("toxicity" in q["risk_ids"] for q in data["questions"])
    assert any(a["decisive"] and a["direction"] == "against" and
        a["reason"]["claim_ids"] == ["clinical.toxicity"] for a in data["arguments"])
    parent = _chair_revision_report(runs[0])
    child = _chair_revision_report(runs[1], parent=parent)
    assert child.revision.previous_recommendation == "Conditional"
    assert child.revision.new_recommendation == "Do Not Invest"
    assert child.revision.new_evidence_ids == ["e2"]
    assert "e2" in child.revision.explanation
    assert "clinical.toxicity" in {c.claim_id for c in child.revision.changed_claims}
    assert child.roles[-1].section_content[0].structured_data["chair"] == data
    assert before.model_dump_json() == before_json


@pytest.mark.asyncio
async def test_irrelevant_evidence_preserves_chair_decision_and_report_recommendation():
    """A new snapshot/document does not mechanically force a recommendation change."""
    runs, calls = await _run_chair_revision_pair("administrative")
    before, after = (run[-1] for run in runs)
    assert calls[0]["snapshot_id"] != calls[1]["snapshot_id"]
    assert calls[0]["evidence"] != calls[1]["evidence"]
    assert before.decision == after.decision
    assert after.decision.recommendation == "Conditional"
    before_data = before.role_result.section_content[0].structured_data["chair"]
    after_data = after.role_result.section_content[0].structured_data["chair"]
    for field in ("recommendation", "rationale", "arguments", "conditions", "questions"):
        assert after_data[field] == before_data[field]
    assert all("e2" not in refs for refs in after_data["claim_evidence_links"].values())
    assert after_data["evidence_source_links"]["e2"] == "s2"
    parent = _chair_revision_report(runs[0])
    child = _chair_revision_report(runs[1], parent=parent)
    assert child.revision.new_evidence_ids == ["e2"]
    assert child.revision.changed_claims == []
    assert child.revision.previous_recommendation == child.revision.new_recommendation == "Conditional"
    assert child.recommendation == parent.recommendation
    assert child.decision_conditions == parent.decision_conditions
    assert child.diligence_questions == parent.diligence_questions
    assert child.roles[-1].section_content[0].structured_data["chair"] == after_data
