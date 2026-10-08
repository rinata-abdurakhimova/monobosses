"""Deterministic arithmetic checks; no live LLM or factual accuracy claim."""
from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from vic.agents.business.investment_calculations import (
    InvestmentScenario, ReviewedRange, StressScenario, calculate_investment_scenarios,
)


def bounds(low=None, high=None):
    return dict(minimum=low, maximum=high, evidence_ids=["e1"] if low is not None else [],
                assumptions=[], unknowns=["Need reviewed input"] if low is None else [])


def scenario():
    return dict(id="base", name="base", milestone_id="proof", horizon="next_milestone",
        currency="USD", geography="Synthetic region", as_of_date="2026-10-08",
        assumptions=["Synthetic reviewed plan only"],
        costs=[dict(id="clinical", category="clinical", description="Synthetic study budget",
            scope="development", work_ids=["a", "b", "c"], amount=bounds("1", "2"),
            currency="USD", scale="million"),
            dict(id="diligence", category="other", description="Separate diligence",
            scope="diligence", work_ids=[], amount=bounds("50", "100"), currency="USD", scale="units")],
        cost_coverage="full", cost_unknowns=[],
        schedule=[dict(work_id="a", duration_days=bounds("10", "20"), depends_on=[]),
                  dict(work_id="b", duration_days=bounds("5", "10"), depends_on=[]),
                  dict(work_id="c", duration_days=bounds("2", "3"), depends_on=["a", "b"])],
        schedule_coverage="full", schedule_unknowns=[], allocated_asset_cash=bounds("200000", "400000"))


def stress():
    return dict(id="delay_test", base_scenario_id="base", kind="delay", assumptions=["Incremental only"],
        incremental_delay_days=bounds("2", "4"), incremental_cost=bounds("1", "2"),
        currency="USD", cost_scale="thousand", burn_per_day=bounds("100", "200"),
        cost_coverage="full", unknowns=[])


def run(data=None, stresses=None):
    return calculate_investment_scenarios([InvestmentScenario.model_validate(data or scenario())],
        [StressScenario.model_validate(s) for s in stresses or []])


def test_budget_diligence_cash_and_parallel_schedule():
    row = run()["scenarios"][0]
    assert row["capital_to_milestone"] == {"minimum": "1000000", "maximum": "2000000"}
    assert row["known_diligence_subtotal"] == {"minimum": "50", "maximum": "100"}
    assert row["time_to_milestone_days"] == {"minimum": "12", "maximum": "23"}
    assert row["funding_gap"] == {"minimum": "600000", "maximum": "1800000"}


def test_partial_budget_is_subtotal_not_total():
    data = scenario()
    data.update(cost_coverage="partial", cost_unknowns=["CMC missing"])
    row = run(data)["scenarios"][0]
    assert row["known_development_subtotal"]["minimum"] == "1000000"
    assert row["capital_to_milestone"] is None
    assert row["funding_gap"] is None


@pytest.mark.parametrize("defect", ["reversed", "one_bound", "negative", "nan", "inf", "no_evidence", "no_gap"])
def test_range_rejects_invalid_inputs(defect):
    data = bounds("1", "2")
    if defect == "reversed": data["minimum"] = "3"
    if defect == "one_bound": data["maximum"] = None
    if defect == "negative": data["minimum"] = "-1"
    if defect == "nan": data["minimum"] = "NaN"
    if defect == "inf": data["maximum"] = "Infinity"
    if defect == "no_evidence": data["evidence_ids"] = []
    if defect == "no_gap": data = bounds(); data["unknowns"] = []
    with pytest.raises(ValidationError): ReviewedRange.model_validate(data)


def test_zero_is_known_and_missing_is_not_zero():
    data = scenario()
    data["costs"][0]["amount"] = bounds("0", "0")
    row = run(data)["scenarios"][0]
    assert row["capital_to_milestone"]["minimum"] == "0"
    assert row["funding_gap"]["maximum"] == "0"
    data["costs"][0]["amount"] = bounds()
    data.update(cost_coverage="unknown", cost_unknowns=["No budget"])
    assert run(data)["scenarios"][0]["capital_to_milestone"] is None


@pytest.mark.parametrize("defect", ["currency", "scale", "cycle", "dangling", "duplicate_cost", "duplicate_task",
    "date", "full_cost_missing", "full_schedule_missing", "partial_no_gap", "self_edge", "duplicate_edge"])
def test_scenario_rejects_invalid_structure(defect):
    d = scenario()
    if defect == "currency": d["costs"][0]["currency"] = "EUR"
    if defect == "scale": d["costs"][0]["scale"] = "billions"
    if defect == "cycle": d["schedule"][0]["depends_on"] = ["c"]
    if defect == "dangling": d["schedule"][0]["depends_on"] = ["missing"]
    if defect == "duplicate_cost": d["costs"].append(deepcopy(d["costs"][0]))
    if defect == "duplicate_task": d["schedule"].append(deepcopy(d["schedule"][0]))
    if defect == "date": d["as_of_date"] = "2026-02-30"
    if defect == "full_cost_missing": d["costs"][0]["amount"] = bounds()
    if defect == "full_schedule_missing": d["schedule"][0]["duration_days"] = bounds()
    if defect == "partial_no_gap": d["cost_coverage"] = "partial"
    if defect == "self_edge": d["schedule"][0]["depends_on"] = ["a"]
    if defect == "duplicate_edge": d["schedule"][2]["depends_on"] = ["a", "a"]
    with pytest.raises(ValueError): run(d)


def test_missing_parallel_duration_does_not_make_full_time():
    d = scenario()
    d["schedule"][0]["duration_days"] = bounds()
    d.update(schedule_coverage="partial", schedule_unknowns=["Duration missing"])
    assert run(d)["scenarios"][0]["time_to_milestone_days"] is None


def test_stress_budget_time_and_financing():
    row = run(stresses=[stress()])["stress_scenarios"][0]
    assert row["incremental_budget"] == {"minimum": "1200", "maximum": "2800"}
    assert row["stressed_capital"] == {"minimum": "1001200", "maximum": "2002800"}
    assert row["stressed_time_days"] == {"minimum": "14", "maximum": "27"}
    assert row["stressed_funding_gap"] == {"minimum": "601200", "maximum": "1802800"}


def test_partial_stress_keeps_budget_unknown():
    s = stress()
    s.update(cost_coverage="partial", unknowns=["Study costs missing"])
    row = run(stresses=[s])["stress_scenarios"][0]
    assert row["incremental_budget"] is None and row["stressed_capital"] is None
    assert row["stressed_time_days"]["minimum"] == "14"


@pytest.mark.parametrize("defect", ["currency", "unknown_base", "duplicate", "incomplete_full"])
def test_invalid_stress(defect):
    s = stress()
    if defect == "currency": s["currency"] = "EUR"
    if defect == "unknown_base": s["base_scenario_id"] = "missing"
    if defect == "incomplete_full": s["burn_per_day"] = bounds()
    with pytest.raises(ValueError): run(stresses=[s, s] if defect == "duplicate" else [s])


def test_grouped_ranges_exclude_missing_and_preserve_currency_date_horizon():
    a = scenario()
    b = deepcopy(a); b.update(id="upside", name="upside"); b["costs"][0]["amount"] = bounds("0.5", "1")
    c = deepcopy(a); c.update(id="eur", currency="EUR")
    for cost in c["costs"]: cost["currency"] = "EUR"
    d = deepcopy(a); d.update(id="future", horizon="future_milestone", milestone_id="later")
    e = deepcopy(a); e.update(id="dated", as_of_date="2026-10-07")
    f = deepcopy(a); f.update(id="partial", name="downside", cost_coverage="partial", cost_unknowns=["Missing"])
    rows = calculate_investment_scenarios([InvestmentScenario.model_validate(s) for s in (a,b,c,d,e,f)])
    assert len(rows["scenario_ranges"]) == 4
    group = rows["scenario_ranges"][0]
    assert group["capital_to_milestone"] == {"minimum": "500000.0", "maximum": "2000000"}
    assert group["capital_to_milestone_scenario_ids"] == ["base", "upside"]


def test_duplicate_scenario_ids_and_names_rejected():
    a = InvestmentScenario.model_validate(scenario())
    with pytest.raises(ValueError): calculate_investment_scenarios([a, a])
    b = a.model_copy(update={"id": "other"})
    with pytest.raises(ValueError): calculate_investment_scenarios([a, b])


def test_mixed_scales_are_normalized_without_float_rounding():
    d = scenario()
    d["costs"][0].update(scale="units", amount=bounds("0.1", "0.2"))
    other = deepcopy(d["costs"][0]); other.update(id="other", scale="thousand", amount=bounds("0.0002", "0.0003"))
    d["costs"].append(other)
    capital = run(d)["scenarios"][0]["capital_to_milestone"]
    assert Decimal(capital["minimum"]) == Decimal("0.3")
    assert Decimal(capital["maximum"]) == Decimal("0.5")


def test_high_precision_decimal_inputs_remain_exact():
    d = scenario()
    value = "123456789012345678901234567890.123456789"
    d["costs"][0].update(scale="units", amount=bounds(value, value))
    assert run(d)["scenarios"][0]["capital_to_milestone"]["minimum"] == value
