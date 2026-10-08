"""Offline requirements, negative validation and real-adapter data flow."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from vic.agents.business.failure_miner import (
    ROLES, FailureAnalysis, analyze_failure_miner, prepare_failure_inputs,
    validate_failure_result, identify_failure_gaps,
)
from vic.contracts import CaseInput, EvidencePack, RoleResult, RunContext


def inputs(empty=False):
    case = CaseInput(indication="Synthetic indication", mechanism="Synthetic mechanism", scope="approach")
    pack = EvidencePack(snapshot_id="miner-snapshot", synthetic=True,
        sources=[] if empty else [dict(id="s1", title="Synthetic study", type="synthetic",
            retrieved_at="2026-10-08T00:00:00Z", synthetic=True, content_hash="sha256:" + "a" * 64)],
        evidence=[] if empty else [dict(id="e1", source_id="s1", scope="approach", excerpt="Synthetic limitation", locator="result")])
    ctx = RunContext(case_id="miner-case", run_id="miner-run", mode="evidence_only", snapshot_id=pack.snapshot_id, as_of_date=None)
    return case, pack, ctx


def finding(basis="hypothesis"):
    return dict(value=None if basis == "unknown" else "A plausible failure scenario",
        basis=basis, claim_ids=[] if basis == "unknown" else ["failure_miner.scenario"],
        assumptions=["Requires applicable specialist verification"] if basis == "hypothesis" else [],
        unknowns=["Applicable result missing"] if basis == "unknown" else [])


def check():
    return dict(question="Does the validated assay show the proposed limitation?", method="Review assay with controls",
        evidence_needed="Assay results and controls", uncertainty_reduced="Mechanism applicability",
        decision_if_positive="Confirmed limitation requires funding review",
        decision_if_negative="Limitation absent supports continued diligence",
        inconclusive_if="Invalid controls require a repeated assay")


def output():
    return dict(summary="Synthetic failure scenarios", position="conditional",
        claims=[dict(id="failure_miner.scenario", text="Limitation could constrain development", provenance="ai",
            support_status="unverified", evidence_ids=[], assumptions=["Scenario for review"], scope="approach", importance="critical")],
        failure_modes=[dict(id="translation_gap", domains=["science", "translation", "investment"], origins=[],
            problem=finding(), affected=finding(), consequence=finding(), investment_impact=finding(),
            priority="critical", priority_rationale=finding(), next_check=check())],
        domain_reviews=[dict(role_id=r, assessment=finding("unknown"),
            failure_ids=["translation_gap"] if r in ("science", "translation", "investment") else [],
            risk_dispositions=[], next_check=f"Obtain {r} review") for r in ROLES],
        interactions=[], interaction_limitations=["Only one failure identified; cross-domain links require data"],
        diligence_priorities=[dict(id="assay_review", rank=1, failure_ids=["translation_gap"], interaction_ids=[],
            priority="critical", rationale=finding(), check=check())], unknowns=["Applicability unknown"],
        change_conditions=["Applicable results change the risk assessment"], limitations=["Synthetic example"])


def upstream(role):
    return RoleResult(role_id=role, summary="Synthetic upstream", position="conditional",
        claims=[dict(id=f"{role}.result", text="Synthetic limitation", provenance="source", support_status="supported",
            evidence_ids=["e1"], scope="approach", importance="major")],
        risks=[dict(id=f"{role}.risk", description="Synthetic risk", priority="major", claim_ids=[f"{role}.result"],
            impact="Development constraint", next_check="Review data")], unknowns=["Applicability unresolved"],
        section_content=[dict(key="key_risks", summary="Synthetic", claim_ids=[f"{role}.result"],
            structured_data={role:dict(snapshot_id="miner-snapshot", records=[dict(id="record_one", details="Complete nested data")])})])


def validate(raw, contexts=None, empty=False):
    case, pack, ctx = inputs(empty)
    payload = prepare_failure_inputs(case, pack, ctx, **(contexts or {}))
    analysis = FailureAnalysis.model_validate(raw)
    validate_failure_result(analysis, case, pack, payload)
    return analysis


def with_contexts():
    raw = output()
    contexts = {r: upstream(r) for r in ROLES}
    failure = raw["failure_modes"][0]
    failure["domains"] = list(ROLES)
    failure["origins"] = [dict(role_id=r, upstream_claim_ids=[f"{r}.result"], upstream_risk_ids=[f"{r}.risk"], record_ids=["record_one"]) for r in ROLES]
    for review in raw["domain_reviews"]:
        review["failure_ids"] = [failure["id"]]
        review["risk_dispositions"] = [dict(upstream_risk_id=f"{review['role_id']}.risk", disposition="included",
            failure_ids=[failure["id"]], rationale="Material development constraint")]
    return raw, contexts


def with_interaction():
    raw = output()
    second = deepcopy(raw["failure_modes"][0])
    second.update(id="capital_pressure", domains=["investment"], origins=[])
    raw["failure_modes"].append(second)
    raw["domain_reviews"][4]["failure_ids"].append("capital_pressure")
    raw["interactions"] = [dict(id="delay_to_capital", from_failure_id="translation_gap", to_failure_id="capital_pressure",
        relationship="amplifies", mechanism=finding(), investment_impact=finding(), next_check=check())]
    raw["diligence_priorities"][0].update(failure_ids=["translation_gap", "capital_pressure"], interaction_ids=["delay_to_capital"])
    return raw


def test_complete_chain_interactions_and_requirements():
    analysis = validate(with_interaction())
    for f in analysis.failure_modes:
        assert all(getattr(f, key) for key in ("problem", "affected", "consequence", "investment_impact", "priority_rationale", "next_check"))
    assert analysis.interactions[0].mechanism.basis == "hypothesis"
    assert analysis.diligence_priorities[0].check.uncertainty_reduced
    assert {r.role_id for r in analysis.domain_reviews} == set(ROLES)


def test_documented_problem_does_not_upgrade_future_consequence():
    raw = output()
    raw["claims"].append(dict(id="failure_miner.fact", text="Observed limitation", provenance="source", support_status="supported",
        evidence_ids=["e1"], scope="approach", importance="critical"))
    raw["failure_modes"][0]["problem"] = dict(value="Observed limitation", basis="documented", claim_ids=["failure_miner.fact"], assumptions=[], unknowns=[])
    raw["position"] = "material_risks"
    analysis = validate(raw)
    assert analysis.failure_modes[0].consequence.basis == "hypothesis"


@pytest.mark.parametrize("field", ["problem", "affected", "consequence", "investment_impact", "priority", "priority_rationale", "next_check", "domains", "origins"])
def test_required_chain_fields(field):
    raw = output()
    del raw["failure_modes"][0][field]
    with pytest.raises(ValidationError): validate(raw)


@pytest.mark.parametrize("location", ["failure", "interaction", "question"])
@pytest.mark.parametrize("field", list(check()))
def test_required_check_fields(location, field):
    raw = with_interaction()
    target = {"failure": raw["failure_modes"][0]["next_check"], "interaction": raw["interactions"][0]["next_check"], "question": raw["diligence_priorities"][0]["check"]}[location]
    del target[field]
    with pytest.raises(ValidationError): validate(raw)


@pytest.mark.parametrize("defect", ["duplicate_claim", "namespace", "evidence", "scope", "assumptions", "claim_ref", "documented", "hypothesis", "unknown_value", "unknown_gaps", "unknown_claims", "empty_modes", "duplicate_failure", "duplicate_domain", "domain_missing", "domain_failure", "domain_coverage", "absent_documented", "blank_check", "extra", "duplicate_interaction", "endpoint", "self_link", "interaction_reason", "rank", "rank_duplicate", "question_ref", "interaction_ref", "endpoint_coverage", "question_coverage", "material_without_fact", "unknown_position"])
def test_reject_invalid_outputs(defect):
    raw = with_interaction()
    f = raw["failure_modes"][0]
    c = raw["claims"][0]
    q = raw["diligence_priorities"][0]
    if defect == "duplicate_claim": raw["claims"].append(deepcopy(c))
    if defect == "namespace": c["id"] = "market.scenario"
    if defect == "evidence": c["evidence_ids"] = ["missing"]
    if defect == "scope": c["scope"] = "program"
    if defect == "assumptions": c["assumptions"] = []
    if defect == "claim_ref": f["problem"]["claim_ids"] = ["failure_miner.missing"]
    if defect == "documented": f["problem"]["basis"] = "documented"
    if defect == "hypothesis": f["problem"]["assumptions"] = []
    if defect == "unknown_value": f["problem"].update(basis="unknown", unknowns=["Gap"])
    if defect == "unknown_gaps": f["problem"] = dict(value=None, basis="unknown", claim_ids=[], assumptions=[], unknowns=[])
    if defect == "unknown_claims": f["problem"] = finding("unknown"); f["problem"]["claim_ids"] = [c["id"]]
    if defect == "empty_modes": raw["failure_modes"] = []
    if defect == "duplicate_failure": raw["failure_modes"].append(deepcopy(f))
    if defect == "duplicate_domain": f["domains"].append("science")
    if defect == "domain_missing": raw["domain_reviews"].pop()
    if defect == "domain_failure": raw["domain_reviews"][0]["failure_ids"] = ["missing"]
    if defect == "domain_coverage": raw["domain_reviews"][0]["failure_ids"] = []
    if defect == "absent_documented": raw["domain_reviews"][0]["assessment"] = finding()
    if defect == "blank_check": f["next_check"]["method"] = "  "
    if defect == "extra": f["probability"] = 0.9
    if defect == "duplicate_interaction": raw["interactions"].append(deepcopy(raw["interactions"][0]))
    if defect == "endpoint": raw["interactions"][0]["from_failure_id"] = "missing"
    if defect == "self_link": raw["interactions"][0]["to_failure_id"] = "translation_gap"
    if defect == "interaction_reason": raw["interactions"] = []; raw["interaction_limitations"] = []
    if defect == "rank": q["rank"] = 2
    if defect == "rank_duplicate": raw["diligence_priorities"].append(deepcopy(q)); raw["diligence_priorities"][1]["id"] = "second"
    if defect == "question_ref": q["failure_ids"] = ["missing"]
    if defect == "interaction_ref": q["interaction_ids"] = ["missing"]
    if defect == "endpoint_coverage": q["failure_ids"] = ["translation_gap"]
    if defect == "question_coverage": q["failure_ids"] = ["translation_gap"]; q["interaction_ids"] = []
    if defect == "material_without_fact": raw["position"] = "material_risks"
    if defect == "unknown_position":
        for mode in raw["failure_modes"]: mode["problem"] = finding("unknown")
    with pytest.raises((ValueError, ValidationError)): validate(raw)


@pytest.mark.parametrize("defect", ["dropped_risk", "duplicate_disposition", "unknown_risk", "wrong_failure", "missing_origin", "unknown_claim", "unknown_record", "unknown_origin_risk", "duplicate_origin", "wrong_domain", "deferred_links"])
def test_origin_and_risk_coverage(defect):
    raw, contexts = with_contexts()
    f = raw["failure_modes"][0]
    review = raw["domain_reviews"][0]
    if defect == "dropped_risk": review["risk_dispositions"] = []
    if defect == "duplicate_disposition": review["risk_dispositions"].append(deepcopy(review["risk_dispositions"][0]))
    if defect == "unknown_risk": review["risk_dispositions"][0]["upstream_risk_id"] = "missing"
    if defect == "wrong_failure": review["risk_dispositions"][0]["failure_ids"] = ["missing"]
    if defect == "missing_origin": f["origins"] = []
    if defect == "unknown_claim": f["origins"][0]["upstream_claim_ids"] = ["science.missing"]
    if defect == "unknown_record": f["origins"][0]["record_ids"] = ["missing"]
    if defect == "unknown_origin_risk": f["origins"][0]["upstream_risk_ids"] = ["missing"]
    if defect == "duplicate_origin": f["origins"].append(deepcopy(f["origins"][0]))
    if defect == "wrong_domain": f["domains"].remove("science")
    if defect == "deferred_links": review["risk_dispositions"][0]["disposition"] = "deferred"
    with pytest.raises(ValueError): validate(raw, contexts)


def test_deferred_risk_requires_rationale_and_no_fabricated_chain():
    raw, contexts = with_contexts()
    raw["failure_modes"][0]["origins"][0]["upstream_risk_ids"] = []
    raw["domain_reviews"][0]["risk_dispositions"][0].update(disposition="deferred", failure_ids=[], rationale="Duplicate of translational constraint; retain original in upstream context")
    validate(raw, contexts)


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("serialized", [False, True])
def test_complete_inputs_preserved(role, serialized):
    case, pack, ctx = inputs()
    result = upstream(role)
    before = result.model_dump(mode="json")
    payload = prepare_failure_inputs(case, pack, ctx, **{role: deepcopy(before) if serialized else result})
    assert payload["upstream_context"][role] == before
    assert result.model_dump(mode="json") == before
    assert payload["evidence"][0]["excerpt"] == pack.evidence[0].excerpt
    assert payload["sources"][0]["content_hash"] == pack.sources[0].content_hash


@pytest.mark.parametrize("defect", ["snapshot", "date", "invalid_date", "role", "source", "duplicate_source", "duplicate_evidence", "claim_evidence", "claim_duplicate", "risk_claim", "section_claim", "nested_snapshot", "metadata_date", "nested_evidence"])
def test_invalid_inputs(defect):
    case, pack, ctx = inputs()
    result = upstream("market").model_dump(mode="json")
    if defect == "snapshot": ctx.snapshot_id = "wrong"
    if defect == "date": case.as_of_date = date(2026, 10, 7); ctx.as_of_date = date(2026, 10, 8)
    if defect == "invalid_date": ctx.as_of_date = "bad"
    if defect == "role": result["role_id"] = "clinical"
    if defect == "source": pack.evidence[0].source_id = "missing"
    if defect == "duplicate_source": pack.sources.append(pack.sources[0])
    if defect == "duplicate_evidence": pack.evidence.append(pack.evidence[0])
    if defect == "claim_evidence": result["claims"][0]["evidence_ids"] = ["missing"]
    if defect == "claim_duplicate": result["claims"].append(deepcopy(result["claims"][0]))
    if defect == "risk_claim": result["risks"][0]["claim_ids"] = ["market.missing"]
    if defect == "section_claim": result["section_content"][0]["claim_ids"] = ["market.missing"]
    meta = result["section_content"][0]["structured_data"]["market"]
    if defect == "nested_snapshot": meta["records"][0]["snapshot_id"] = "wrong"
    if defect == "metadata_date": ctx.as_of_date = date(2026, 10, 8); meta["as_of_date"] = "2026-10-07"
    if defect == "nested_evidence": meta["records"][0]["evidence_ids"] = ["missing"]
    with pytest.raises(ValueError): prepare_failure_inputs(case, pack, ctx, market=result)


@pytest.mark.asyncio
@pytest.mark.parametrize("feedback", [False, True])
async def test_real_adapter_complete_input_processing_output(feedback):
    from vic.config import Settings
    from vic.llm import ProviderResponse, StructuredLlm
    from vic.prompts import load_prompt
    requests = []
    raw, contexts = with_contexts()
    contexts["investment"].section_content[0].structured_data["investment"]["calculated_financials"] = dict(subtotal=100, cost_coverage="partial", sensitivity=[dict(value=120, assumption="Delay")], unknowns=["Total budget unknown"])
    class OfflineProvider:
        name = "offline-miner-test"
        async def complete(self, **request):
            requests.append(request)
            return ProviderResponse(json.dumps(raw), 100, 50)
    case, pack, ctx = inputs()
    if feedback: ctx.feedback["failure_miner"] = [dict(reason="Review causal link")]
    ctx.model = StructuredLlm(OfflineProvider(), Settings(_env_file=None, llm_max_retries=0, llm_max_repairs=0))
    result = await analyze_failure_miner(case, pack, ctx, **contexts)
    assert len(requests) == 1
    prompt = load_prompt("failure_miner")
    assert prompt.text in requests[0]["system"] and '"FailureMode"' in requests[0]["system"]
    sent = json.loads(requests[0]["messages"][0]["content"])
    assert sent["upstream_context"] == {r:v.model_dump(mode="json") for r,v in contexts.items()}
    data = result.section_content[0].structured_data["failure_miner"]
    assert data["upstream_context"] == sent["upstream_context"]
    assert data["failure_modes"] == raw["failure_modes"]
    assert data["diligence_priorities"] == raw["diligence_priorities"]
    assert len(result.risks) == len(raw["failure_modes"])
    assert result.risks[0].id == "failure_miner.translation_gap"
    assert result.section_content[0].key == "key_risks"
    assert all(f"{r}: Applicability unresolved" in result.unknowns for r in ROLES)
    assert result.unknowns == data["source_requests"]
    assert RoleResult.model_validate_json(result.model_dump_json()) == result
    assert ctx.trace.usage[0]["prompt_version"] == prompt.version
    assert ctx.trace.usage[0]["outcome"] == "ok"
    if feedback: assert "Review causal link" in requests[0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_missing_data_and_no_mutation():
    case, pack, ctx = inputs(empty=True)
    raw = output(); raw["position"] = "insufficient_data"
    raw["failure_modes"][0]["problem"] = finding("unknown")
    before = deepcopy(raw)
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(return_value=raw))
    result = await analyze_failure_miner(case, pack, ctx)
    assert raw == before
    assert result.position == "insufficient_data"
    assert result.risks[0].description.startswith("[unknown]")
    assert all(any(f"{r} context absent" in g for g in result.unknowns) for r in ROLES)
    ctx.model.generate_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_adapter_and_invalid_output():
    case, pack, ctx = inputs()
    with pytest.raises(RuntimeError): await analyze_failure_miner(case, pack, ctx)
    raw = output(); raw["position"] = "material_risks"
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(return_value=raw))
    with pytest.raises(ValueError): await analyze_failure_miner(case, pack, ctx)


def test_gap_collection_and_iso_date():
    gaps = identify_failure_gaps(validate(output()))
    assert gaps.count("Applicable result missing") == 1
    assert any("Assay results and controls" in gap for gap in gaps)
    case, pack, ctx = inputs(); ctx.as_of_date = "2026-10-08"
    assert prepare_failure_inputs(case, pack, ctx)["as_of_date"] == "2026-10-08"
    assert ctx.as_of_date == "2026-10-08"


@pytest.mark.parametrize("filename,role", [("investment-synthetic.json", "investment"), ("partnerships-synthetic.json", "partnerships"), ("ip-licensing-synthetic.json", "ip_licensing")])
def test_existing_upstream_examples(filename, role):
    root = Path(__file__).resolve().parents[6]
    fixtures = json.loads((root / "docs" / "examples" / filename).read_text())
    for fixture in fixtures.values() if isinstance(fixtures, dict) else fixtures:
        case = CaseInput.model_validate(fixture["case"])
        pack = EvidencePack.model_validate(fixture["pack"])
        context = dict(fixture.get("context", dict(case_id="case", run_id="run", snapshot_id=pack.snapshot_id, as_of_date=case.as_of_date, mode="evidence_only")))
        payload = prepare_failure_inputs(case, pack, RunContext(**context), **{role:fixture["result"]})
        assert payload["upstream_context"][role] == fixture["result"]


@pytest.mark.asyncio
async def test_nested_financial_unknowns_remain_actionable():
    case, pack, ctx = inputs()
    raw, contexts = with_contexts()
    contexts["investment"].section_content[0].structured_data["investment"]["calculated_financials"] = dict(
        subtotal=100, cost_coverage="partial", unknowns=["Full budget unknown"], sensitivity=dict(unknowns=["Delay cost unknown"]))
    before = contexts["investment"].model_dump(mode="json")
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(return_value=raw))
    result = await analyze_failure_miner(case, pack, ctx, **contexts)
    assert "investment: Full budget unknown" in result.unknowns
    assert "investment: Delay cost unknown" in result.unknowns
    assert result.section_content[0].structured_data["failure_miner"]["upstream_context"]["investment"] == before


@pytest.mark.asyncio
async def test_r3_audit_and_canonical_report_preserve_complete_role_output():
    from vic.contracts import CommitteeDecision, Report
    from vic.evidence.audit import audit_claims
    from vic.integrity import assert_report
    from vic.report_builder import SECTION_OWNERS, build_report
    case, pack, ctx = inputs()
    raw = with_interaction()
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(return_value=raw))
    miner = await analyze_failure_miner(case, pack, ctx)
    audit = audit_claims(miner.claims, pack)
    assert audit.findings[0].verdict == "unverified"
    assert not audit.unresolved_critical_claim_ids
    # Minimal valid specialist results provide the six owned sections. No shared code changes.
    roles = []
    for owner in dict.fromkeys(SECTION_OWNERS.values()):
        roles.append(RoleResult(role_id=owner, summary="Synthetic", position="unknown",
            section_content=[dict(key=key, summary="Synthetic specialist section")
                             for key, role in SECTION_OWNERS.items() if role == owner]))
    roles.append(miner)
    decision = CommitteeDecision(recommendation="Conditional", rationale="Specialist review pending",
        questions=[dict(question=f"Synthetic question {i}", why_it_matters="Applicability",
            evidence_needed="Applicable data", decision_if_positive="Review", decision_if_negative="Revise") for i in range(5)])
    report = build_report(case=case, pack=pack, roles=roles, decision=decision, claims=miner.claims,
        case_id=ctx.case_id, run_id=ctx.run_id, report_id="miner-report", version=1, synthetic=True)
    assert_report(report)
    restored = Report.model_validate_json(report.model_dump_json())
    assert restored.roles[-1] == miner
    assert restored.risks == miner.risks
    data = restored.roles[-1].section_content[0].structured_data["failure_miner"]
    assert data["interactions"] == raw["interactions"]
    assert data["diligence_priorities"] == raw["diligence_priorities"]
    # Current builder exposes IDs in report sections; full chains live in report.roles.
    risk_section = next(s for s in restored.sections if s.key == "key_risks")
    assert risk_section.structured_data["risk_ids"] == [r.id for r in miner.risks]


@pytest.mark.asyncio
async def test_real_adapter_schema_valid_but_dropped_risk_rejected():
    from vic.config import Settings
    from vic.llm import ProviderResponse, StructuredLlm
    raw, contexts = with_contexts()
    raw["domain_reviews"][0]["risk_dispositions"] = []
    class OfflineProvider:
        name = "offline-invalid-miner"
        async def complete(self, **request):
            return ProviderResponse(json.dumps(raw), 100, 50)
    case, pack, ctx = inputs()
    ctx.model = StructuredLlm(OfflineProvider(), Settings(_env_file=None, llm_max_retries=0, llm_max_repairs=0))
    with pytest.raises(ValueError, match="Every upstream risk"):
        await analyze_failure_miner(case, pack, ctx, **contexts)


@pytest.mark.asyncio
async def test_invalid_input_never_calls_adapter():
    case, pack, ctx = inputs()
    ctx.snapshot_id = "wrong"
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(return_value=output()))
    with pytest.raises(ValueError): await analyze_failure_miner(case, pack, ctx)
    ctx.model.generate_structured.assert_not_awaited()


def test_priority_order_rejects_minor_before_critical():
    raw = with_interaction()
    second = deepcopy(raw["diligence_priorities"][0])
    second.update(id="second_check", rank=2)
    raw["diligence_priorities"][0]["priority"] = "minor"
    raw["diligence_priorities"].append(second)
    with pytest.raises(ValueError, match="Critical questions"): validate(raw)


def test_synthetic_upstream_and_historical_dates():
    case, pack, ctx = inputs()
    pack.synthetic = False; pack.sources[0].synthetic = False
    ctx.as_of_date = date(2026, 10, 8)
    market = upstream("market")
    market.section_content[0].structured_data["market"].update(synthetic=True, as_of_date="2026-10-08")
    market.section_content[0].structured_data["market"]["records"][0]["as_of_date"] = "2020-01-01"
    payload = prepare_failure_inputs(case, pack, ctx, market=market)
    assert payload["synthetic"]
    assert payload["upstream_context"]["market"] == market.model_dump(mode="json")


@pytest.mark.asyncio
async def test_new_main_gateway_full_failure_miner_flow():
    """Real R2 gateway transport, mocked HTTP only; no credentials or live requests."""
    import httpx
    from vic.config import Settings
    from vic.llm import OpenAICompatibleProvider, StructuredLlm
    from vic.prompts import load_prompt
    raw, contexts = with_contexts()
    requests = []

    def handler(request):
        assert str(request.url) == "https://miner.example/v1/chat/completions"
        body = json.loads(request.content)
        requests.append(body)
        assert load_prompt("failure_miner").text in body["messages"][0]["content"]
        sent = json.loads(body["messages"][1]["content"])
        assert sent["upstream_context"] == {r: v.model_dump(mode="json") for r, v in contexts.items()}
        assert "Review causal link" in body["messages"][2]["content"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(raw)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50}})

    settings = Settings(_env_file=None, llm_provider="openai", llm_api_key="synthetic-test-only",
        llm_base_url="https://miner.example/v1", llm_model="synthetic-model",
        llm_max_retries=0, llm_max_repairs=0)
    case, pack, ctx = inputs()
    ctx.feedback["failure_miner"] = [{"reason": "Review causal link"}]
    ctx.model = StructuredLlm(OpenAICompatibleProvider(settings, transport=httpx.MockTransport(handler)), settings)
    result = await analyze_failure_miner(case, pack, ctx, **contexts)
    assert len(requests) == 1
    assert result.section_content[0].structured_data["failure_miner"]["failure_modes"] == raw["failure_modes"]
    assert RoleResult.model_validate_json(result.model_dump_json()) == result
    assert ctx.trace.usage[-1]["input_tokens"] == 100
    assert ctx.trace.usage[-1]["output_tokens"] == 50
    assert ctx.trace.usage[-1]["prompt_version"] == load_prompt("failure_miner").version
