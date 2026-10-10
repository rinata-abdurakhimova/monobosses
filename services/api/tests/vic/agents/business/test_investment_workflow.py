"""Two-stage synthetic workflow, source binding and immutable-plan boundaries."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from test_investment import (
    inputs, numeric_inputs, plan_output, explanation_output, dual_adapter,
)
from vic.agents.business.investment import (
    InvestmentExplanation, PreparedInvestmentPlan, analyze_investment,
    assemble_investment_analysis,
)
from vic.agents.business.investment_preparation import resolve_numeric_inputs


def resolve(data=None, pack=None):
    p=PreparedInvestmentPlan.model_validate(data or plan_output(True))
    return resolve_numeric_inputs(p.scenario_blueprints,p.stress_blueprints,p.numeric_bindings,
                                  pack or inputs()[1])


@pytest.mark.asyncio
async def test_generated_plan_from_evidence_needs_no_external_numeric_inputs():
    case,pack,ctx=inputs(); ctx.model=dual_adapter(True)
    result=await analyze_investment(case,pack,ctx)
    calls=ctx.model.generate_structured.call_args_list
    assert [c.args[0] for c in calls]==["investment_plan","investment"]
    assert calls[0].args[2] is PreparedInvestmentPlan
    assert calls[1].args[2] is InvestmentExplanation
    assert calls[0].args[1]["calculated_financials"]["scenarios"]==[]
    assert "fixed_plan" not in calls[0].args[1]
    assert "caller_numeric_inputs" not in calls[1].args[1]
    data=result.section_content[0].structured_data["investment"]
    row=data["calculated_financials"]["scenarios"][0]
    assert row["capital_to_milestone"]=={"minimum":"400000","maximum":"700000"}
    assert row["time_to_milestone_days"]=={"minimum":"30","maximum":"60"}
    assert row["funding_gap"]=={"minimum":"250000","maximum":"600000"}
    assert data["calculated_financials"]["stress_scenarios"][0]["incremental_budget"]=={"minimum":"1200","maximum":"2800"}
    assert len(data["numeric_provenance"])==9
    assert data["numeric_review_status"]=="semantic_review_pending"
    assert data["next_milestone"]==calls[1].args[1]["fixed_plan"]["next_milestone"]
    assert data["work_packages"]==calls[1].args[1]["fixed_plan"]["work_packages"]


@pytest.mark.asyncio
async def test_empty_evidence_yields_unknowns_in_two_distinct_calls():
    case,pack,ctx=inputs(True); ctx.model=dual_adapter()
    result=await analyze_investment(case,pack,ctx)
    assert ctx.model.generate_structured.await_count==2
    assert result.position=="insufficient_data"
    assert result.section_content[0].structured_data["investment"]["calculated_financials"]["scenarios"]==[]
    assert result.unknowns


@pytest.mark.parametrize("defect", ["number","number_substring","quote","evidence","unit_text","currency",
    "days_as_money","scale","unknown_target","duplicate_binding","computed_blueprint","analogue_no_assumptions",
    "wrong_operation","ambiguous_locale","unsupported_formula"])
def test_source_binding_rejects_unsupported_numbers_units_or_paths(defect):
    d=plan_output(True); binding=d["numeric_bindings"][0]; operand=binding["operands"][0]
    if defect=="number": operand["minimum_text"]="999"
    if defect=="number_substring": operand["minimum_text"]="10"
    if defect=="quote": operand["quote"]="A fabricated quote USD 100-200 thousand"
    if defect=="evidence": operand["evidence_id"]="missing"
    if defect=="unit_text": operand["unit_text"]="million"
    if defect=="currency": operand["currency"]="EUR"
    if defect=="days_as_money": operand.update(unit="days",unit_text="days",currency=None)
    if defect=="scale": operand.update(unit="units",unit_text="USD")
    if defect=="unknown_target": binding["input_path"]="costs.missing.amount"
    if defect=="duplicate_binding": d["numeric_bindings"].append(deepcopy(binding))
    if defect=="computed_blueprint": d["scenario_blueprints"][0]["costs"][0]["amount"].update(
        minimum="100",maximum="200",evidence_ids=["e1"],unknowns=[])
    if defect=="analogue_no_assumptions": binding.update(basis="analogue",assumptions=[])
    if defect=="wrong_operation": binding["operation"]="multiply"
    if defect=="ambiguous_locale": operand["minimum_text"]="100,50"
    if defect=="unsupported_formula": binding["operation"]="eval"
    with pytest.raises(ValueError): resolve(d)


def test_source_scale_converts_to_cash_units_in_python():
    scenarios,_,trace=resolve()
    cash=scenarios[0].allocated_asset_cash
    assert str(cash.minimum)=="100000" and str(cash.maximum)=="150000"
    assert trace[5]["operands"][0]["minimum_text"]=="100"


def test_python_quantity_times_unit_price_not_llm_arithmetic():
    case,pack,_=inputs()
    quote="Synthetic preparation uses 2-3 samples at USD 50 thousand per sample."
    pack.evidence[0].excerpt += " " + quote
    d=plan_output(True); b=d["numeric_bindings"][0]
    b["operation"]="multiply"
    b["operands"]=[dict(evidence_id="e1",quote=quote,minimum_text="2",maximum_text="3",
        unit="count",unit_text="samples",currency=None),
        dict(evidence_id="e1",quote=quote,minimum_text="50",maximum_text="50",unit="thousand_per_item",
             unit_text="thousand per sample",currency="USD")]
    scenarios,_,trace=resolve(d,pack)
    assert str(scenarios[0].costs[0].amount.minimum)=="100"
    assert str(scenarios[0].costs[0].amount.maximum)=="150"
    assert trace[0]["operation"]=="multiply"


@pytest.mark.asyncio
async def test_missing_cost_remains_partial_not_fabricated_total():
    case,pack,ctx=inputs(); p=plan_output(True)
    p["numeric_bindings"]=[b for b in p["numeric_bindings"] if b["input_path"]!="costs.study.amount"]
    p["scenario_blueprints"][0].update(cost_coverage="partial",cost_unknowns=["Study cost missing"])
    e=explanation_output(True); e["capital"]["missing_inputs"]=["Study cost missing"]
    ctx.model=SimpleNamespace(generate_structured=AsyncMock(side_effect=[p,e]))
    result=await analyze_investment(case,pack,ctx)
    row=result.section_content[0].structured_data["investment"]["calculated_financials"]["scenarios"][0]
    assert row["capital_to_milestone"] is None
    assert row["known_development_subtotal"]=={"minimum":"100000","maximum":"200000"}
    assert row["time_to_milestone_days"]["minimum"]=="30"
    assert any("Study cost missing" in g for g in result.unknowns)


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["baseline_delay","unknown_trigger","work_ref","cycle","wrong_milestone",
    "date","cost_coverage","schedule_edges","stress_trigger_id","duplicate_future","extra_financial_output"])
async def test_invalid_plan_stops_before_second_call(defect):
    case,pack,ctx=inputs(); p=plan_output(True)
    if defect=="baseline_delay": p["stress_events"][0]["already_in_baseline"]=True
    if defect=="unknown_trigger": p["stress_events"][0]["trigger"]=deepcopy(p["stress_events"][1]["trigger"])
    if defect=="work_ref": p["scenario_blueprints"][0]["costs"][0]["work_ids"]=["missing"]
    if defect=="cycle": p["work_packages"][0]["depends_on"]=["study"]
    if defect=="wrong_milestone": p["scenario_blueprints"][0]["milestone_id"]="missing"
    if defect=="date": p["scenario_blueprints"][0]["as_of_date"]="2026-10-07"
    if defect=="cost_coverage": p["scenario_blueprints"][0]["costs"][0]["work_ids"]=[]
    if defect=="schedule_edges": p["work_packages"][1]["depends_on"]=[]
    if defect=="stress_trigger_id": p["stress_blueprints"][0]["trigger_id"]="missing"
    if defect=="duplicate_future": p["future_milestones"].append(deepcopy(p["future_milestones"][0]))
    if defect=="extra_financial_output": p["capital"]={}
    ctx.model=SimpleNamespace(generate_structured=AsyncMock(side_effect=[p,explanation_output(True)]))
    with pytest.raises(ValueError): await analyze_investment(case,pack,ctx)
    assert ctx.model.generate_structured.await_count==1


@pytest.mark.parametrize("field", ["next_milestone","work_packages","scenario_blueprints","numeric_bindings",
    "calculated_financials","stress_events"])
def test_second_schema_cannot_return_replacement_plan_or_numbers(field):
    d=explanation_output(); d[field]=[]
    with pytest.raises(ValidationError): InvestmentExplanation.model_validate(d)


@pytest.mark.parametrize("defect", ["claim_replacement","risk_replacement","future_replacement","stress_replacement"])
def test_final_assembly_protects_fixed_records(defect):
    p=plan_output(); e=explanation_output()
    if defect=="claim_replacement": e["claims"]=deepcopy(p["claims"])
    if defect=="risk_replacement": p["risks"]=deepcopy(e["risks"])
    if defect=="future_replacement": e["future_financing"][0]["milestone_id"]="other"
    if defect=="stress_replacement": e["stress_explanations"][0]["event_id"]="other"
    with pytest.raises(ValueError): assemble_investment_analysis(
        PreparedInvestmentPlan.model_validate(p),InvestmentExplanation.model_validate(e))


@pytest.mark.asyncio
async def test_adapter_payload_mutation_cannot_change_fixed_plan_or_arithmetic():
    case,pack,ctx=inputs()
    async def adapter(prompt,payload,schema,context):
        if prompt=="investment_plan": return plan_output(True)
        payload["fixed_plan"]["work_packages"][0]["id"]="tampered"
        payload["calculated_financials"]["scenarios"][0]["capital_to_milestone"]["minimum"]="0"
        return explanation_output(True)
    ctx.model=SimpleNamespace(generate_structured=adapter)
    result=await analyze_investment(case,pack,ctx)
    data=result.section_content[0].structured_data["investment"]
    assert data["work_packages"][0]["id"]=="prepare"
    assert data["calculated_financials"]["scenarios"][0]["capital_to_milestone"]["minimum"]=="400000"


@pytest.mark.asyncio
async def test_external_scenarios_do_not_get_duplicated():
    case,pack,ctx=inputs(); scenarios,stresses=numeric_inputs()
    ctx.model=dual_adapter(True,supplied=True)
    result=await analyze_investment(case,pack,ctx,scenarios=scenarios,stresses=stresses)
    data=result.section_content[0].structured_data["investment"]
    assert len(data["calculated_financials"]["scenarios"])==1
    assert data["numeric_provenance"]==[]


def test_negative_source_token_cannot_be_reinterpreted_as_positive():
    _,pack,_=inputs(); quote="Synthetic quoted adjustment USD -100 to 200 thousand."
    pack.evidence[0].excerpt += " " + quote
    d=plan_output(True); d["numeric_bindings"][0]["operands"][0]["quote"]=quote
    with pytest.raises(ValueError): resolve(d,pack)


def test_quantity_and_unit_price_must_count_same_item():
    _,pack,_=inputs(); quote="Synthetic 2-3 patients and USD 50 thousand per sample."
    pack.evidence[0].excerpt += " " + quote
    d=plan_output(True); b=d["numeric_bindings"][0]; b["operation"]="multiply"
    b["operands"]=[dict(evidence_id="e1",quote=quote,minimum_text="2",maximum_text="3",
        unit="count",unit_text="patients",currency=None),
        dict(evidence_id="e1",quote=quote,minimum_text="50",maximum_text="50",unit="thousand_per_item",
             unit_text="thousand per sample",currency="USD")]
    with pytest.raises(ValueError): resolve(d,pack)


@pytest.mark.asyncio
async def test_prompt_versions_match_each_distinct_stage():
    case,pack,ctx=inputs(); ctx.model=dual_adapter()
    await analyze_investment(case,pack,ctx)
    calls=ctx.model.generate_structured.call_args_list
    assert calls[0].args[1]["prompt_version"]=="1.0.0"
    assert calls[1].args[1]["prompt_version"]=="2.0.0"


@pytest.mark.parametrize("sign", ["-", "−", "﹣", "－", "‒", "–", "—"])
@pytest.mark.parametrize("spacing", ["", " ", "\u00a0"])
def test_negative_source_signs_cannot_become_positive(sign, spacing):
    _, pack, _ = inputs()
    quote = f"Synthetic adjustment USD {sign}{spacing}100 to 200 thousand."
    pack.evidence[0].excerpt += " " + quote
    data = plan_output(True)
    data["numeric_bindings"][0]["operands"][0]["quote"] = quote
    with pytest.raises(ValueError, match="Nonnegative numeric token"):
        resolve(data, pack)


@pytest.mark.parametrize("separator", ["-", "−", "﹣", "－", "‒", "–", "—"])
def test_positive_source_ranges_keep_unicode_separators(separator):
    _, pack, _ = inputs()
    quote = f"Preparation costs USD 100{separator}200 thousand"
    pack.evidence[0].excerpt += " " + quote
    data = plan_output(True)
    data["numeric_bindings"][0]["operands"][0]["quote"] = quote
    scenarios, _, _ = resolve(data, pack)
    assert str(scenarios[0].costs[0].amount.minimum) == "100"
    assert str(scenarios[0].costs[0].amount.maximum) == "200"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["summary", "capital", "time", "claim", "stress", "path"])
@pytest.mark.parametrize("text", [
    "Required capital is USD 999999999 and development takes 999 days.",
    "Required capital is USD 400000 and development takes 10 days.",
    "Budget increases by 20%.",
    "Expected development takes ９９９ days.",
])
async def test_numeric_explanation_is_rejected_in_every_narrative_area(field, text):
    case, pack, ctx = inputs()
    explanation = explanation_output(True)
    if field == "summary":
        explanation["summary"] = text
    elif field == "capital":
        explanation["capital"]["budget_basis"]["value"] = text
    elif field == "time":
        explanation["time"]["scheduling_basis"]["value"] = text
    elif field == "claim":
        claim = deepcopy(plan_output(True)["claims"][0])
        claim.update(id="investment.extra", text=text)
        explanation["claims"] = [claim]
    elif field == "stress":
        explanation["stress_explanations"][0]["next_check"] = text
    else:
        explanation["financial_paths"][0]["next_check"] = text
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(side_effect=[
        plan_output(True), explanation,
    ]))
    with pytest.raises(ValueError, match="Numeric literals are forbidden"):
        await analyze_investment(case, pack, ctx)


def test_explanation_reference_ids_and_reviewer_names_are_allowed():
    from vic.agents.business.investment import validate_explanation_numbers
    data = explanation_output(True)
    data["summary"] = "R3 and R4 should review the calculated budget and timing."
    data["capital"]["scenario_ids"] = ["scenario_2026"]
    data["stress_explanations"][0]["event_id"] = "delay_2"
    validate_explanation_numbers(InvestmentExplanation.model_validate(data))


def test_incomplete_plan_finding_becomes_unknown_without_inventing_claims():
    from vic.agents.business.investment import qualify_incomplete_plan_findings
    raw = plan_output(True)
    plan = PreparedInvestmentPlan.model_validate(raw)
    from vic.agents.business.investment import _walk, Finding
    target = next(b for b in _walk(plan) if isinstance(b, Finding) and b.basis != 'unknown')
    original = target.value
    target.claim_ids = []
    fixed = qualify_incomplete_plan_findings(plan)
    assert any(str(original) in gap and 'Incomplete finding' in gap for gap in fixed.unknowns)
    assert fixed.claims == plan.claims
    assert any(b.basis == 'unknown' and b.value is None and b.unknowns for b in _walk(fixed) if isinstance(b, Finding))
    assert qualify_incomplete_plan_findings(fixed) == fixed


@pytest.mark.asyncio
async def test_explanation_domain_repair_keeps_validated_plan_and_calculations():
    from vic.config import Settings
    case, pack, ctx = inputs()
    bad = explanation_output(True)
    bad['summary'] = 'Budget increases by 20%.'
    good = explanation_output(True)
    ctx.model = SimpleNamespace(_s=Settings(_env_file=None, continue_on_node_validation_error=True),
        generate_structured=AsyncMock(side_effect=[plan_output(True), bad, good]))
    result = await analyze_investment(case, pack, ctx)
    calls = ctx.model.generate_structured.call_args_list
    assert [c.args[0] for c in calls] == ['investment_plan', 'investment', 'investment']
    assert calls[1].args[1]['fixed_plan_hash'] == calls[2].args[1]['fixed_plan_hash']
    assert calls[1].args[1]['calculated_financials'] == calls[2].args[1]['calculated_financials']
    assert 'Numeric literals are forbidden' in calls[2].args[3].feedback['investment'][-1]
    assert not ctx.feedback
    assert result.claims
    assert result.summary == good['summary']


@pytest.mark.asyncio
async def test_failed_explanation_retains_real_plan_claims_and_python_numbers():
    from vic.config import Settings
    case, pack, ctx = inputs()
    bad = explanation_output(True)
    bad['summary'] = 'Invented capital is USD 999999999.'
    ctx.model = SimpleNamespace(_s=Settings(_env_file=None, continue_on_node_validation_error=True),
        generate_structured=AsyncMock(side_effect=[plan_output(True), bad, bad]))
    result = await analyze_investment(case, pack, ctx)
    assert result.position == 'partial_assessment'
    assert result.claims and result.summary.startswith('Preliminary investment plan:')
    data = result.section_content[0].structured_data['investment']
    assert data['calculated_financials']['scenarios'][0]['capital_to_milestone'] == {
        'minimum': '400000', 'maximum': '700000'}
    assert data['explanation_recovery']['status'] == 'analysis_unavailable'
    assert '999999999' not in result.model_dump_json()
    assert len(ctx.model.generate_structured.call_args_list) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('defect', ['namespace', 'missing_claims'])
async def test_malformed_planning_risk_does_not_discard_other_valid_plan_findings(defect):
    case, pack, ctx = inputs()
    p = plan_output(True)
    # Add the concrete risk shape that formerly killed validate_prepared_plan.
    original = {'id': 'financing_gap', 'description': 'Funding may not cover the proposed work',
        'priority': 'major', 'claim_ids': [p['claims'][0]['id']],
        'impact': 'Next milestone may be delayed', 'next_check': 'Verify asset-allocated funding'}
    if defect == 'missing_claims':
        original.update(id='investment.financing_gap', claim_ids=[])
    p['risks'] = [deepcopy(original)]
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(side_effect=[p, explanation_output(True)]))
    result = await analyze_investment(case, pack, ctx)
    assert result.claims
    data = result.section_content[0].structured_data['investment']
    assert data['calculated_financials']['scenarios'][0]['capital_to_milestone'] == {
        'minimum': '400000', 'maximum': '700000'}
    if defect == 'namespace':
        risk = next(r for r in result.risks if r.id == 'investment.financing_gap')
        assert risk.description == original['description']
        assert risk.claim_ids == original['claim_ids']
    else:
        assert not any(r.id == original['id'] for r in result.risks)
        assert any(original['description'] in gap and original['next_check'] in gap
            for gap in result.unknowns)
    assert p['risks'] == [original]  # caller/model response was not mutated
