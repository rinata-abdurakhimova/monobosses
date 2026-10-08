"""Offline synthetic validation and adapter/RoleResult checks, not live evaluation."""
from copy import deepcopy
from datetime import date
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from vic.agents.business.investment import (
    InvestmentAnalysis, InvestmentExplanation, PreparedInvestmentPlan,
    analyze_investment, prepare_investment_inputs, validate_investment_result,
)
from vic.agents.business.investment_calculations import InvestmentScenario, StressScenario
from vic.contracts import CaseInput, Claim, EvidencePack, RoleResult, RunContext, SectionContent


def inputs(empty=False):
    text = ("SYNTHETIC ONLY. A fictional plan targets preclinical proof with preparation and a study. "
            "Preparation costs USD 100-200 thousand and takes 10-20 days. The study costs USD "
            "300-500 thousand and takes 20-40 days after preparation. Separate diligence costs "
            "USD 5-10 thousand. USD 100-150 thousand is allocated to this asset and milestone. "
            "A synthetic delay adds 2-4 days, USD 1-2 thousand extra costs and USD 100-200/day "
            "incremental burn. Actual development, CMC, regulatory requirements, ownership, "
            "partner interest and future financing are not established by this synthetic plan.")
    case = CaseInput(indication="Synthetic disease", mechanism="Synthetic target", scope="approach",
                     as_of_date="2026-10-08")
    pack = EvidencePack(snapshot_id="snapshot-investment", synthetic=True,
        sources=[] if empty else [dict(id="s1", title="Synthetic budget and schedule", type="synthetic",
            synthetic=True, retrieved_at="2026-10-08T00:00:00Z", content_hash="sha256:" + sha256(text.encode()).hexdigest())],
        evidence=[] if empty else [dict(id="e1", source_id="s1", scope="approach",
            locator="Synthetic budget", excerpt=text)])
    ctx = RunContext(case_id="case-investment", run_id="run-investment", snapshot_id=pack.snapshot_id,
                     as_of_date=date(2026,10,8), mode="evidence_only")
    return case, pack, ctx


def numeric_inputs():
    def r(low=None, high=None):
        return dict(minimum=low, maximum=high, evidence_ids=["e1"] if low is not None else [],
                    assumptions=["Synthetic plan; not a real quote"], unknowns=["Need budget"] if low is None else [])
    scenario = dict(id="base", name="base", milestone_id="proof", horizon="next_milestone",
        currency="USD", geography="Synthetic region", as_of_date="2026-10-08",
        assumptions=["Scope limited to fictional preclinical proof; completeness is illustrative"],
        costs=[dict(id=id_, category="research" if id_ != "diligence" else "other", description=id_,
            scope="development" if id_ != "diligence" else "diligence", work_ids=[id_] if id_ != "diligence" else [],
            amount=r(low, high), currency="USD", scale="thousand") for id_,low,high in
            (("prepare","100","200"),("study","300","500"),("diligence","5","10"))],
        cost_coverage="full", cost_unknowns=[],
        schedule=[dict(work_id="prepare", duration_days=r("10","20"), depends_on=[]),
                  dict(work_id="study", duration_days=r("20","40"), depends_on=["prepare"])],
        schedule_coverage="full", schedule_unknowns=[], allocated_asset_cash=r("100000","150000"))
    stress = dict(id="delay", base_scenario_id="base", kind="delay", assumptions=["No overlap or double counting"],
        incremental_delay_days=r("2","4"), incremental_cost=r("1","2"), currency="USD", cost_scale="thousand",
        burn_per_day=r("100","200"), cost_coverage="full", unknowns=[])
    return [InvestmentScenario.model_validate(scenario)], [StressScenario.model_validate(stress)]


def output(numeric=False):
    def f(basis="unknown", value="Synthetic work proposal"):
        return dict(value=None if basis == "unknown" else value, basis=basis,
            claim_ids=[] if basis == "unknown" else ["investment.plan"],
            assumptions=["Synthetic proposal, needs R4 review"] if basis == "hypothesis" else [],
            unknowns=["Need reviewed evidence or plan"] if basis == "unknown" else [])
    def dep(role):
        return dict(role_id=role, assessment=f(), upstream_claim_ids=[], record_ids=[], next_check="Review upstream evidence")
    return dict(summary="Synthetic investment plan; no valuation or return established.",
        position="insufficient_data", claims=[dict(id="investment.plan", text="A proof stage may be considered",
            provenance="ai", support_status="unverified", evidence_ids=[], assumptions=["Synthetic proposal"],
            scope="approach", importance="major")],
        next_milestone=dict(id="proof", stage=f("hypothesis"), required_result=f("hypothesis"),
            success_criteria=[f()], clinical_alignment=f()),
        work_packages=[dict(id=id_, milestone_id="proof", work=f("hypothesis"),
            required_resources=[f()], depends_on=[] if id_ == "prepare" else ["prepare"],
            completion_criteria=f()) for id_ in ("prepare", "study")],
        capital=dict(budget_basis=f("hypothesis"), scenario_ids=["base"] if numeric else [],
            missing_inputs=[] if numeric else ["Reviewed CRO/CMC asset budget needed"],
            company_financials_boundary="Company cash and diligence are separate from allocated asset funding."),
        time=dict(scheduling_basis=f("hypothesis"), scenario_ids=["base"] if numeric else [],
            dependencies=[f()], possible_delays=[f()], missing_inputs=[] if numeric else ["Reviewed work durations needed"]),
        value_inflections=[dict(id="readout", event=f("hypothesis"), required_result=f(), potential_value_effect=f(),
            conditions=["Evidence supports clinically relevant benefit"], next_check="Review result with R4")],
        future_financing=[dict(milestone_id="later", stage=f(), purpose=f(), funding_need=f(),
            possible_sources=[f()], prerequisites=["Confirm next stage and responsibility"], scenario_ids=[],
            unknowns=["Future stage budget and financing terms unknown"])],
        financial_paths=[dict(path=path, feasibility="insufficient_data", rationale=f(),
            financial_consequences=[f()], retained_costs_and_obligations=f(),
            financing_dependencies=[dep("partnerships"),dep("ip_licensing")],
            prerequisites=["Confirm rights and funding responsibilities"], unknowns=["No transaction evidence"],
            next_check="Review ownership and partner interest") for path in ("own_development","licensing","acquisition")],
        stress_assessments=[dict(kind=kind, trigger=f(), budget_effect=f(), financing_effect=f(), time_effect=f(),
            stress_ids=["delay"] if numeric and kind == "delay" else [], unknowns=["Financing effects need review"],
            next_check="Review incremental studies, delays and financing conditions") for kind in
            ("delay","additional_studies","weaker_results")],
        commercial_constraints=[dep("market")],
        risks=[dict(id="investment.financing", description="Funding unavailable", priority="major",
            claim_ids=["investment.plan"], impact="May prevent next stage", next_check="Obtain verified funding plan")],
        unknowns=["Synthetic case; stage and financing need review"],
        next_checks=[dict(question="What budget funds the next result?", why_it_matters="Sets capital need",
            evidence_needed="Reviewed work plan and vendor quotes", decision_if_positive="Assess funding path",
            decision_if_negative="Keep capital unknown", claim_ids=[])],
        change_conditions=["Verified stage budget changes financing path"], limitations=["Synthetic offline fixture"])


def plan_output(numeric=False, supplied=False):
    data = output(numeric)
    plan = dict(claims=data["claims"], next_milestone=data["next_milestone"],
        work_packages=data["work_packages"], future_milestones=[dict(milestone_id=f["milestone_id"],stage=f["stage"])
            for f in data["future_financing"]],
        stress_events=[dict(id=s["kind"]+"_event",kind=s["kind"],trigger=s["trigger"],
            work_ids=["study"],already_in_baseline=False,stress_ids=s["stress_ids"])
            for s in data["stress_assessments"]],
        scenario_blueprints=[],stress_blueprints=[],numeric_bindings=[],risks=[],
        unknowns=["Synthetic plan; needs review"],limitations=["Synthetic preparation only"])
    if not numeric:
        return plan
    plan["stress_events"][0]["trigger"] = deepcopy(data["next_milestone"]["stage"])
    if supplied:
        return plan
    scenarios,stresses=numeric_inputs()
    blueprint=scenarios[0].model_dump(mode="json")
    stress_blueprint=stresses[0].model_dump(mode="json") | {"trigger_id":"delay_event"}
    missing=dict(minimum=None,maximum=None,evidence_ids=[],assumptions=[],unknowns=["Source binding pending"])
    for c in blueprint["costs"]: c["amount"]=deepcopy(missing)
    for t in blueprint["schedule"]: t["duration_days"]=deepcopy(missing)
    blueprint["allocated_asset_cash"]=deepcopy(missing)
    for key in ("incremental_delay_days","incremental_cost","burn_per_day"):
        stress_blueprint[key]=deepcopy(missing)
    plan["scenario_blueprints"]=[blueprint]
    plan["stress_blueprints"]=[stress_blueprint]
    def bind(record_type,record_id,path,quote,low,high,unit,unit_text,currency):
        return dict(record_type=record_type,record_id=record_id,input_path=path,operation="copy",
            operands=[dict(evidence_id="e1",quote=quote,minimum_text=low,maximum_text=high,
                unit=unit,unit_text=unit_text,currency=currency)],basis="direct",
            applicability="Matches the fictional plan only",assumptions=["Synthetic source, no actual quote"],unknowns=[])
    entries=[("scenario","base","costs.prepare.amount","Preparation costs USD 100-200 thousand","100","200","thousand","thousand","USD"),
        ("scenario","base","costs.study.amount","The study costs USD 300-500 thousand","300","500","thousand","thousand","USD"),
        ("scenario","base","costs.diligence.amount","Separate diligence costs USD 5-10 thousand","5","10","thousand","thousand","USD"),
        ("scenario","base","schedule.prepare.duration_days","takes 10-20 days","10","20","days","days",None),
        ("scenario","base","schedule.study.duration_days","takes 20-40 days after preparation","20","40","days","days",None),
        ("scenario","base","allocated_asset_cash","USD 100-150 thousand is allocated to this asset and milestone","100","150","thousand","thousand","USD"),
        ("stress","delay","incremental_delay_days","A synthetic delay adds 2-4 days","2","4","days","days",None),
        ("stress","delay","incremental_cost","USD 1-2 thousand extra costs","1","2","thousand","thousand","USD"),
        ("stress","delay","burn_per_day","USD 100-200/day incremental burn","100","200","units_per_day","/day","USD")]
    plan["numeric_bindings"]=[bind(*entry) for entry in entries]
    return plan


def explanation_output(numeric=False):
    data=output(numeric)
    for field in ("next_milestone","work_packages"):
        data.pop(field)
    data["claims"]=[]  # Refer to immutable planning claims without repeating them.
    for f in data["future_financing"]:
        f.pop("stage")
    data["stress_explanations"]=[dict(event_id=s["kind"]+"_event",**{
        k:v for k,v in s.items() if k not in ("kind","trigger","stress_ids")})
        for s in data.pop("stress_assessments")]
    return data


def dual_adapter(numeric=False, supplied=False):
    return SimpleNamespace(generate_structured=AsyncMock(side_effect=[
        plan_output(numeric,supplied),explanation_output(numeric)]))


def validate(data=None, empty=False, numeric=False, **upstream):
    case, pack, ctx = inputs(empty)
    scenarios, stresses = numeric_inputs() if numeric else ([], [])
    payload = prepare_investment_inputs(case, pack, ctx, scenarios=scenarios, stresses=stresses, **upstream)
    analysis = InvestmentAnalysis.model_validate(data or output(numeric))
    validate_investment_result(analysis, case, pack, payload)
    return analysis, payload


@pytest.mark.parametrize("empty,numeric", [(True,False),(False,False),(False,True)])
def test_all_required_outputs_remain_present(empty,numeric):
    a, payload = validate(empty=empty,numeric=numeric)
    assert a.next_milestone.required_result and a.work_packages and a.capital and a.time
    assert a.value_inflections and a.future_financing and len(a.financial_paths)==3
    assert len(a.stress_assessments)==3 and a.next_checks and a.commercial_constraints
    if numeric:
        row = payload["calculated_financials"]["scenarios"][0]
        assert row["capital_to_milestone"] == {"minimum":"400000","maximum":"700000"}
        assert row["time_to_milestone_days"] == {"minimum":"30","maximum":"60"}
        assert row["funding_gap"] == {"minimum":"250000","maximum":"600000"}


@pytest.mark.parametrize("field", ["next_milestone","work_packages","capital","time","value_inflections",
    "future_financing","financial_paths","stress_assessments","commercial_constraints","next_checks"])
def test_missing_required_block_rejected(field):
    data = output(); del data[field]
    with pytest.raises(ValidationError): validate(data)


@pytest.mark.parametrize("defect", ["claim_ref","evidence","scope","duplicate_claim","documented",
    "hypothesis","unknown_value","unknown_gap","duplicate_work","work_dependency","cycle",
    "future_same","future_duplicate","work_milestone","path_duplicate","path_ip","path_gap",
    "path_rationale","stress_duplicate","stress_ref","commercial_role","absent_context",
    "upstream_ref","record_ref","capital_ref","time_ref","capital_gap","time_gap",
    "risk_namespace","risk_claim","duplicate_risk","duplicate_event","blank","extra_number"])
def test_reject_inconsistent_narrative(defect):
    d = output(); finding = d["next_milestone"]["stage"]
    if defect == "claim_ref": finding["claim_ids"] = ["missing"]
    if defect == "evidence": d["claims"][0]["evidence_ids"] = ["missing"]
    if defect == "scope": d["claims"][0]["scope"] = "program"
    if defect == "duplicate_claim": d["claims"].append(deepcopy(d["claims"][0]))
    if defect == "documented": finding["basis"] = "documented"
    if defect == "hypothesis": finding["assumptions"] = []
    if defect == "unknown_value": d["next_milestone"]["clinical_alignment"]["value"] = "Confirmed"
    if defect == "unknown_gap": d["next_milestone"]["clinical_alignment"]["unknowns"] = []
    if defect == "duplicate_work": d["work_packages"].append(deepcopy(d["work_packages"][0]))
    if defect == "work_dependency": d["work_packages"][0]["depends_on"] = ["missing"]
    if defect == "cycle": d["work_packages"][0]["depends_on"] = ["study"]
    if defect == "future_same": d["future_financing"][0]["milestone_id"] = "proof"
    if defect == "future_duplicate": d["future_financing"].append(deepcopy(d["future_financing"][0]))
    if defect == "work_milestone": d["work_packages"][0]["milestone_id"] = "missing"
    if defect == "path_duplicate": d["financial_paths"][0]["path"] = "licensing"
    if defect == "path_ip": d["financial_paths"][0]["financing_dependencies"].pop()
    if defect == "path_gap": d["financial_paths"][0]["unknowns"] = []
    if defect == "path_rationale": d["financial_paths"][0]["feasibility"] = "conditional"
    if defect == "stress_duplicate": d["stress_assessments"][0]["kind"] = "weaker_results"
    if defect == "stress_ref": d["stress_assessments"][0]["stress_ids"] = ["missing"]
    if defect == "commercial_role": d["commercial_constraints"][0]["role_id"] = "clinical"
    if defect == "absent_context": d["commercial_constraints"][0]["assessment"] = deepcopy(finding)
    if defect == "upstream_ref": d["commercial_constraints"][0]["upstream_claim_ids"] = ["market.missing"]
    if defect == "record_ref": d["financial_paths"][0]["financing_dependencies"][0]["record_ids"] = ["missing"]
    if defect == "capital_ref": d["capital"]["scenario_ids"] = ["missing"]
    if defect == "time_ref": d["time"]["scenario_ids"] = ["missing"]
    if defect == "capital_gap": d["capital"]["missing_inputs"] = []
    if defect == "time_gap": d["time"]["missing_inputs"] = []
    if defect == "risk_namespace": d["risks"][0]["id"] = "market.financing"
    if defect == "risk_claim": d["risks"][0]["claim_ids"] = []
    if defect == "duplicate_risk": d["risks"].append(deepcopy(d["risks"][0]))
    if defect == "duplicate_event": d["value_inflections"].append(deepcopy(d["value_inflections"][0]))
    if defect == "blank": d["summary"] = "  "
    if defect == "extra_number": d["capital"]["amount"] = 1000000
    with pytest.raises(ValueError): validate(d)


def upstream(role="market"):
    return RoleResult(role_id=role, summary="Synthetic upstream", position="insufficient_data",
        claims=[Claim(id=f"{role}.context",text="Synthetic context",provenance="source",
            support_status="supported",evidence_ids=["e1"],scope="approach",importance="major")],
        unknowns=["Need semantic review"], section_content=[SectionContent(key="commercial_opportunity",
            summary="Synthetic constraints",claim_ids=[f"{role}.context"],structured_data={
                role: {"snapshot_id":"snapshot-investment","as_of_date":"2026-10-08",
                       "candidates":[{"id":"partner_a"}],"access_limitations":["Access unknown"]}})])


def test_documented_context_uses_local_and_actual_upstream_links():
    d = output()
    d["claims"].append(dict(id="investment.constraint", text="Synthetic constraint", provenance="source",
        support_status="supported", evidence_ids=["e1"], assumptions=[], scope="approach", importance="major"))
    dep = d["commercial_constraints"][0]
    dep["assessment"].update(value="Synthetic limitation",basis="documented",claim_ids=["investment.constraint"], unknowns=[])
    dep["upstream_claim_ids"] = ["market.context"]
    validate(d, market=upstream().model_dump(mode="json"))


@pytest.mark.parametrize("defect", ["snapshot","date","source","role","upstream_evidence","upstream_snapshot",
    "upstream_date","numeric_evidence","numeric_date","numeric_empty"])
def test_reject_invalid_input_before_adapter(defect):
    case,pack,ctx = inputs(empty=defect=="numeric_empty")
    kwargs={}
    if defect == "snapshot": ctx.snapshot_id = "other"
    if defect == "date": ctx.as_of_date = date(2026,10,7)
    if defect == "source": pack.evidence[0].source_id = "missing"
    if defect.startswith("upstream") or defect=="role":
        m=upstream()
        if defect=="role": m.role_id="clinical"
        if defect=="upstream_evidence": m.claims[0].evidence_ids=["missing"]
        if defect=="upstream_snapshot": m.section_content[0].structured_data["market"]["snapshot_id"]="other"
        if defect=="upstream_date": m.section_content[0].structured_data["market"]["as_of_date"]="2026-10-07"
        kwargs["market"]=m
    if defect.startswith("numeric"):
        scenarios,_=numeric_inputs()
        if defect=="numeric_evidence": scenarios[0].costs[0].amount.evidence_ids=["missing"]
        if defect=="numeric_date": scenarios[0].as_of_date=date(2026,10,7)
        kwargs["scenarios"]=scenarios
    with pytest.raises(ValueError): prepare_investment_inputs(case,pack,ctx,**kwargs)


@pytest.mark.parametrize("defect", ["missing_work_cost","missing_schedule","schedule_edges","wrong_milestone",
    "missing_scenario_ref","missing_stress_ref"])
def test_numeric_plan_must_match_narrative(defect):
    case,pack,ctx=inputs(); scenarios,stresses=numeric_inputs(); d=output(True)
    if defect=="missing_work_cost": scenarios[0].costs[0].work_ids=[]
    if defect=="missing_schedule": scenarios[0].schedule.pop()
    if defect=="schedule_edges": d["work_packages"][1]["depends_on"]=[]
    if defect=="wrong_milestone": scenarios[0].milestone_id="other"
    if defect=="missing_scenario_ref": d["capital"]["scenario_ids"]=[]
    if defect=="missing_stress_ref": d["stress_assessments"][0]["stress_ids"]=[]
    payload=prepare_investment_inputs(case,pack,ctx,scenarios=scenarios,stresses=stresses)
    with pytest.raises(ValueError): validate_investment_result(InvestmentAnalysis.model_validate(d),case,pack,payload)


@pytest.mark.asyncio
async def test_adapter_two_distinct_calls_shared_result_and_preserved_market_context():
    case,pack,ctx=inputs(); scenarios,stresses=numeric_inputs()
    ctx.model=dual_adapter(True, supplied=True)
    result=await analyze_investment(case,pack,ctx,scenarios=scenarios,stresses=stresses,
                                   market=upstream().model_dump(mode="json"))
    assert ctx.model.generate_structured.await_count==2
    calls=ctx.model.generate_structured.call_args_list
    assert calls[0].args[0]=="investment_plan" and calls[0].args[2] is PreparedInvestmentPlan
    assert calls[1].args[0]=="investment" and calls[1].args[2] is InvestmentExplanation
    assert RoleResult.model_validate(result.model_dump(mode="json"))==result
    section=result.section_content[0]; assert section.key=="capital_to_milestone"
    data=section.structured_data["investment"]
    assert data["upstream_context"]["market"]["unknowns"]==["Need semantic review"]
    assert data["upstream_context"]["market"]["section_content"][0]["structured_data"]["market"]["access_limitations"]==["Access unknown"]
    assert data["calculated_financials"]["scenarios"][0]["capital_to_milestone"]["minimum"]=="400000"
    assert data["synthetic"] and data["snapshot_id"]==pack.snapshot_id
    assert data["claim_evidence_links"]=={"investment.plan":[]}
    assert any("ip_licensing context absent" in g for g in result.unknowns)


@pytest.mark.asyncio
async def test_no_adapter_errors_without_live_call():
    case,pack,ctx=inputs()
    with pytest.raises(RuntimeError): await analyze_investment(case,pack,ctx)


@pytest.mark.asyncio
async def test_invalid_output_is_not_emitted():
    case,pack,ctx=inputs(); d=explanation_output(); d["capital"]["scenario_ids"]=["invented"]
    ctx.model=SimpleNamespace(generate_structured=AsyncMock(side_effect=[plan_output(),d]))
    with pytest.raises(ValueError): await analyze_investment(case,pack,ctx)


def test_future_numeric_horizon_kept_separate():
    case,pack,ctx=inputs(); scenarios,_=numeric_inputs(); future=scenarios[0].model_copy(deep=True)
    future.id="future_base"; future.horizon="future_milestone"; future.milestone_id="later"
    for c in future.costs: c.work_ids=["later_work"] if c.scope=="development" else []
    future.schedule=[future.schedule[0].model_copy(update={"work_id":"later_work","depends_on":[]})]
    d=output(True); d["future_financing"][0]["scenario_ids"]=["future_base"]
    work=deepcopy(d["work_packages"][0]); work.update(id="later_work",milestone_id="later"); d["work_packages"].append(work)
    d["stress_assessments"][0]["stress_ids"]=[]
    payload=prepare_investment_inputs(case,pack,ctx,scenarios=[*scenarios,future])
    validate_investment_result(InvestmentAnalysis.model_validate(d),case,pack,payload)
    assert len(payload["calculated_financials"]["scenario_ranges"])==2


def test_upstream_contract_unknown_without_assumptions_is_accepted():
    m=upstream("clinical")
    m.claims[0]=Claim(id="clinical.next_milestone",text="Milestone unknown",provenance="ai",
        support_status="unknown",scope="approach",importance="major")
    m.section_content[0].claim_ids=["clinical.next_milestone"]
    _,payload=validate(clinical=m)
    assert payload["upstream_context"]["clinical"]["claims"][0]["support_status"]=="unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("name,role", [("partnerships","partnerships"),("ip-licensing","ip_licensing")])
async def test_actual_merged_upstream_example_can_be_consumed(name,role):
    import json
    from pathlib import Path
    root=Path(__file__).resolve().parents[6]
    examples=json.loads((root/"docs"/"examples"/f"{name}-synthetic.json").read_text())
    example=examples[0] if isinstance(examples,list) else examples["documented_with_unknowns"]
    case=CaseInput.model_validate(example["case"]); pack=EvidencePack.model_validate(example["pack"])
    ctx=RunContext(case_id="case-example",run_id="run-example",snapshot_id=pack.snapshot_id,
        as_of_date=case.as_of_date,mode="evidence_only",
        model=dual_adapter())
    result=await analyze_investment(case,pack,ctx,**{role:example["result"]})
    assert result.section_content[0].structured_data["investment"]["context_availability"][role]


@pytest.mark.asyncio
async def test_manual_synthetic_report_accepts_investment_role():
    from vic.contracts import DiligenceQuestion, Report, SectionKey
    from vic.integrity import assert_report
    case,pack,ctx=inputs(); scenarios,stresses=numeric_inputs()
    ctx.model=dual_adapter(True, supplied=True)
    role=await analyze_investment(case,pack,ctx,scenarios=scenarios,stresses=stresses)
    sections=[SectionContent(key=k,summary="Synthetic assembly; not Report builder") for k in SectionKey]
    for s in sections:
        if s.key=="capital_to_milestone":
            s.claim_ids=role.section_content[0].claim_ids
            s.structured_data=role.section_content[0].structured_data
        if s.key=="recommendation": s.structured_data={"recommendation":"Conditional"}
        if s.key=="key_risks": s.structured_data={"risk_ids":[r.id for r in role.risks]}
        if s.key=="diligence_questions": s.structured_data={"question_count":5}
        if s.key=="sources": s.structured_data={"source_ids":[s.id for s in pack.sources]}
    questions=[DiligenceQuestion(question=f"Synthetic check {i}",why_it_matters="Review gaps",
        evidence_needed="Reviewed plan",decision_if_positive="Reassess",decision_if_negative="Remain conditional")
        for i in range(5)]
    report=Report(id="report-investment",case_id=ctx.case_id,run_id=ctx.run_id,version=1,
        scope=case.scope,synthetic=True,snapshot_id=pack.snapshot_id,recommendation="Conditional",
        rationale="Synthetic structure only",sections=sections,roles=[role],claims=role.claims,
        risks=role.risks,evidence=pack.evidence,sources=pack.sources,diligence_questions=questions)
    assert_report(Report.model_validate(report.model_dump(mode="json")))


@pytest.mark.asyncio
async def test_saved_synthetic_examples_replay_exactly():
    import json
    from pathlib import Path
    root=Path(__file__).resolve().parents[6]
    examples=json.loads((root/"docs/examples/investment-synthetic.json").read_text())
    for e in examples:
        case=CaseInput.model_validate(e["case"]); pack=EvidencePack.model_validate(e["pack"])
        context=dict(e["context"]); context["as_of_date"]=date.fromisoformat(context["as_of_date"])
        ctx=RunContext(**context,model=SimpleNamespace(generate_structured=AsyncMock(side_effect=[e["mock_plan"],e["mock_explanation"]])))
        result=await analyze_investment(case,pack,ctx,**e["upstream_context"],
            scenarios=[InvestmentScenario.model_validate(s) for s in e["scenarios"]],
            stresses=[StressScenario.model_validate(s) for s in e["stresses"]])
        assert result.model_dump(mode="json")==e["result"]
        assert type(result) is RoleResult
