import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from vic.agents.business.calculations import MarketScenario, estimate_market_scenarios
from vic.agents.business.market import (
    MarketAnalysis,
    analyze_market,
    prepare_market_inputs,
    validate_market_result,
)
from vic.contracts import CaseInput, Evidence, EvidencePack, RunContext, Source


def run_context(model=None):
    return RunContext(
        case_id="case-test",
        run_id="run-test",
        snapshot_id="snapshot-test",
        as_of_date=None,
        mode="evidence_only",
        model=model,
    )


def empty_pack():
    return EvidencePack(sources=[], evidence=[], snapshot_id="snapshot-test", synthetic=True)


def fixture():
    case = CaseInput(indication="Synthetic disease", mechanism="Synthetic target", scope="approach")
    pack = EvidencePack(
        sources=[
            Source(
                id="s1",
                title="Synthetic",
                type="synthetic",
                synthetic=True,
                retrieved_at=datetime(2026, 10, 6, tzinfo=UTC),
                content_hash="sha256:"
                + hashlib.sha256(b"Synthetic comparator is approved.").hexdigest(),
            )
        ],
        evidence=[
            Evidence(
                id="e1",
                source_id="s1",
                excerpt="Synthetic comparator is approved.",
                scope="approach",
                locator="results",
            )
        ],
        snapshot_id="snapshot-test",
        synthetic=True,
    )
    output = {
        "summary": "Synthetic comparator exists.",
        "commercial_summary": "Price unknown.",
        "position": "insufficient_data",
        "claims": [
            {
                "id": "market.comparator",
                "text": "Synthetic comparator is approved.",
                "support_status": "supported",
                "evidence_ids": ["e1"],
                "assumptions": [],
                "scope": "approach",
                "importance": "major",
            }
        ],
        "competitors": [
            {
                "name": "Synthetic comparator",
                "categories": ["approved", "same_target"],
                "development_status": "approved",
                "discontinuation_reason": None,
                "discontinuation_reason_claim_ids": [],
                "discontinuation_unknowns": [],
                "claim_ids": ["market.comparator"],
            }
        ],
        "target_population": {
            "description": None,
            "indication": None,
            "eligibility": [],
            "geography": None,
            "access_limitations": [],
            "claim_ids": [],
            "unknowns": ["Patient population not provided"],
        },
        "competitive_coverage": {
            k: {
                "status": "documented" if k in ("approved", "same_target") else "insufficient_data",
                "claim_ids": ["market.comparator"] if k in ("approved", "same_target") else [],
                "unknowns": [] if k in ("approved", "same_target") else [f"No evidence for {k}"],
            }
            for k in (
                "standard_of_care",
                "approved",
                "clinical_stage",
                "same_target",
                "alternative_mechanism",
                "discontinued",
            )
        },
        "pricing_analogues": [],
        "pricing_unknowns": ["Pricing analogues unknown"],
        "access": {
            "reimbursement": [],
            "prescribing": [],
            "other_access": [],
            "claim_ids": [],
            "unknowns": ["Access unknown"],
        },
        "commercial_value": {
            "assessment": "insufficient_data",
            "rationale": "Commercial value unknown",
            "unmet_need": None,
            "willingness_to_pay": None,
            "claim_ids": [],
            "unknowns": ["Willingness to pay unknown"],
        },
        "diligence_questions": [
            {
                "question": "What price and reimbursement can be supported?",
                "why_it_matters": "Determines access",
                "evidence_needed": "Pricing and payer evidence",
                "decision_if_positive": "Reassess opportunity",
                "decision_if_negative": "Review commercial viability",
                "claim_ids": [],
            }
        ],
        "differentiation": [],
        "risks": [],
        "unknowns": ["Price unknown"],
        "change_conditions": ["Obtain pricing evidence"],
        "limitations": ["Synthetic only"],
    }
    return case, pack, output


def scenario(**overrides):
    values = {
        "name": "base",
        "population": "1000",
        "eligible_fraction": "0.5",
        "access_fraction": "0.2",
        "annual_price": "100",
        "currency": "USD",
        "geography": "Synthetic region",
        "as_of_date": "2026-10-06",
        "assumptions": ["Synthetic illustration"],
        "input_evidence_ids": {
            k: ["e1"]
            for k in ("population", "eligible_fraction", "access_fraction", "annual_price")
        },
    }
    return MarketScenario(**(values | overrides))


def test_arithmetic_missing_zero_and_scale():
    assert Decimal(estimate_market_scenarios([scenario()])[0]["annual_market_opportunity"]) == 10000
    assert (
        estimate_market_scenarios([scenario(annual_price=None)])[0]["annual_market_opportunity"]
        is None
    )
    assert (
        Decimal(
            estimate_market_scenarios([scenario(annual_price="0")])[0]["annual_market_opportunity"]
        )
        == 0
    )
    assert (
        Decimal(
            estimate_market_scenarios([scenario(annual_price="100000")])[0][
                "annual_market_opportunity"
            ]
        )
        == 10000000
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"eligible_fraction": "1.1"},
        {"annual_price": "-1"},
        {"population": "NaN"},
        {"currency": "usd"},
    ],
)
def test_invalid_numeric_inputs(changes):
    with pytest.raises(ValidationError):
        scenario(**changes)


def test_input_integrity_and_provenance():
    case, pack, _ = fixture()
    payload = prepare_market_inputs(case, pack, [scenario()])
    assert payload["evidence"][0]["synthetic"]
    with pytest.raises(ValueError):
        prepare_market_inputs(case, pack, [scenario(input_evidence_ids={})])
    with pytest.raises(ValueError):
        prepare_market_inputs(case, pack, [scenario(as_of_date="2026-99-01")])
    pack.evidence[0].source_id = "absent"
    with pytest.raises(ValueError):
        prepare_market_inputs(case, pack)


@pytest.mark.parametrize(
    "defect",
    [
        "fake_evidence",
        "missing_evidence",
        "fake_claim",
        "status",
        "scope",
        "comparator",
        "duplicate",
    ],
)
def test_reject_invalid_model_output(defect):
    case, pack, output = fixture()
    if defect == "fake_evidence":
        output["claims"][0]["evidence_ids"] = ["invented"]
    if defect == "missing_evidence":
        output["claims"][0]["evidence_ids"] = []
    if defect == "fake_claim":
        output["competitors"][0]["claim_ids"] = ["market.invented"]
    if defect == "status":
        output["competitors"][0]["development_status"] = "clinical_stage"
    if defect == "scope":
        output["claims"][0]["scope"] = "program"
    if defect == "comparator":
        output["differentiation"] = [
            {
                "comparator": "invented",
                "dimension": "safety",
                "assessment": "Unknown",
                "claim_ids": ["market.comparator"],
            }
        ]
    if defect == "duplicate":
        output["claims"].append(output["claims"][0])
    with pytest.raises(ValueError):
        validate_market_result(MarketAnalysis(**output), case, pack)


@pytest.mark.asyncio
async def test_one_adapter_call_and_both_sections():
    case, pack, output = fixture()
    adapter = type("Adapter", (), {})()
    adapter.generate_structured = AsyncMock(return_value=output)
    result = await analyze_market(case, pack, run_context(adapter))
    adapter.generate_structured.assert_awaited_once()
    assert adapter.generate_structured.call_args.args[0] == "market"
    assert result.role_id == "market"
    sections = result.section_content
    assert [s.key for s in sections] == ["competitive_landscape", "commercial_opportunity"]
    assert len(sections[0].structured_data["competitors"]["same_target"]) == 1
    assert sections[1].structured_data["scenarios"] == []
    assert any("numeric inputs" in gap for gap in result.unknowns)


@pytest.mark.asyncio
async def test_empty_pack_and_missing_adapter():
    case, _, output = fixture()
    output.update(claims=[], competitors=[])
    for finding in output["competitive_coverage"].values():
        finding.update(status="insufficient_data", claim_ids=[], unknowns=["No evidence"])
    adapter = type("Adapter", (), {})()
    adapter.generate_structured = AsyncMock(return_value=output)
    result = await analyze_market(case, empty_pack(), run_context(adapter))
    assert result.position == "insufficient_data"
    with pytest.raises(RuntimeError):
        await analyze_market(case, empty_pack(), run_context())


def test_empty_pack_cannot_claim_favorable_market():
    case, _, output = fixture()
    output.update(claims=[], competitors=[], position="favorable")
    with pytest.raises(ValueError):
        validate_market_result(MarketAnalysis(**output), case, empty_pack())


def test_differentiation_retains_support_and_currency():
    from vic.agents.business.market import assess_differentiation

    case, pack, output = fixture()
    output["differentiation"] = [
        {
            "comparator": "Synthetic comparator",
            "dimension": "benefit",
            "assessment": "Superiority is unknown",
            "claim_ids": ["market.comparator"],
        }
    ]
    analysis = MarketAnalysis(**output)
    validate_market_result(analysis, case, pack)
    assert assess_differentiation(analysis)[0]["evidence_ids"] == ["e1"]
    results = estimate_market_scenarios([scenario(), scenario(name="upside", currency="EUR")])
    assert [r["inputs"]["currency"] for r in results] == ["USD", "EUR"]


@pytest.mark.asyncio
async def test_target_population_survives_with_evidence_and_unknowns():
    case, pack, output = fixture()
    pack.evidence.append(
        Evidence(
            id="e2",
            source_id="s1",
            excerpt="Synthetic intended population: adults with disease X in region Y.",
            scope="approach",
            locator="population",
        )
    )
    output["claims"].append(
        {
            "id": "market.population",
            "text": "Adults with disease X in region Y.",
            "support_status": "supported",
            "evidence_ids": ["e2"],
            "assumptions": [],
            "scope": "approach",
            "importance": "major",
        }
    )
    output["target_population"] = {
        "description": "Adults with disease X",
        "indication": "Disease X",
        "eligibility": ["Adult"],
        "geography": "Region Y",
        "access_limitations": [],
        "claim_ids": ["market.population"],
        "unknowns": ["Reimbursement unknown"],
    }
    adapter = type("Adapter", (), {})()
    adapter.generate_structured = AsyncMock(return_value=output)
    result = await analyze_market(case, pack, run_context(adapter))
    commercial = result.section_content[1].model_dump(mode="json")
    population = commercial["structured_data"]["target_population"]
    assert population["description"] == "Adults with disease X"
    assert population["claim_ids"] == ["market.population"]
    assert "Reimbursement unknown" in result.unknowns
    assert "market.population" in commercial["claim_ids"]


@pytest.mark.parametrize(
    "defect", ["missing_block", "missing_link", "unknown_link", "silent_unknown"]
)
def test_target_population_invalid_or_missing(defect):
    case, pack, output = fixture()
    if defect == "missing_block":
        del output["target_population"]
    elif defect == "missing_link":
        output["target_population"]["description"] = "Adults"
    elif defect == "unknown_link":
        output["target_population"]["claim_ids"] = ["market.absent"]
    elif defect == "silent_unknown":
        output["target_population"]["unknowns"] = []
    with pytest.raises(ValueError):
        validate_market_result(MarketAnalysis(**output), case, pack)


def test_unknown_population_is_explicit():
    from vic.agents.business.market import identify_market_gaps

    _, _, output = fixture()
    gaps = identify_market_gaps(MarketAnalysis(**output), [])
    assert "Patient population not provided" in gaps
    assert any("patient population is unknown" in gap for gap in gaps)
    assert any("geography is unknown" in gap for gap in gaps)


@pytest.mark.parametrize(
    "defect",
    [
        "coverage_missing",
        "coverage_silent",
        "pricing_silent",
        "pricing_link",
        "pricing_date",
        "access_link",
        "access_silent",
        "value_link",
        "value_silent",
        "question_link",
        "questions_missing",
        "reason_silent",
        "reason_link",
        "active_reason",
    ],
)
def test_new_blocks_reject_broken_links_and_silent_gaps(defect):
    case, pack, output = fixture()
    if defect == "coverage_missing":
        del output["competitive_coverage"]["discontinued"]
    if defect == "coverage_silent":
        output["competitive_coverage"]["discontinued"]["unknowns"] = []
    if defect == "pricing_silent":
        output["pricing_unknowns"] = []
    if defect in ("pricing_link", "pricing_date"):
        output["pricing_analogues"] = [
            {
                "name": "Synthetic comparator",
                "price_description": "Price not supplied",
                "geography": "Region Y",
                "as_of_date": "2026-10-06" if defect == "pricing_link" else "2026-99-01",
                "comparability": "Duration differs",
                "limitations": [],
                "unknowns": [],
                "claim_ids": ["market.absent"]
                if defect == "pricing_link"
                else ["market.comparator"],
            }
        ]
    if defect == "access_link":
        output["access"]["reimbursement"] = ["Restriction"]
    if defect == "access_silent":
        output["access"]["unknowns"] = []
    if defect == "value_link":
        output["commercial_value"]["assessment"] = "potential_value"
    if defect == "value_silent":
        output["commercial_value"]["unknowns"] = []
    if defect == "question_link":
        output["diligence_questions"][0]["claim_ids"] = ["market.absent"]
    if defect == "questions_missing":
        output["diligence_questions"] = []
    if defect in ("reason_silent", "reason_link"):
        output["competitors"][0].update(
            categories=["discontinued"], development_status="discontinued"
        )
        for finding in output["competitive_coverage"].values():
            finding.update(
                status="insufficient_data", claim_ids=[], unknowns=["Incomplete coverage"]
            )
        if defect == "reason_link":
            output["competitors"][0]["discontinuation_reason"] = "Synthetic reason"
    if defect == "active_reason":
        output["competitors"][0]["discontinuation_reason"] = "Not applicable"
    with pytest.raises(ValueError):
        validate_market_result(MarketAnalysis(**output), case, pack)


@pytest.mark.asyncio
async def test_full_market_outputs_survive_assembly():
    case, pack, output = fixture()
    pack.evidence[0].excerpt = (
        "Synthetic comparator approved; a second program discontinued for unknown reason. "
        "Synthetic analogue annual list price is USD 100 in region Y on 2026-10-06; "
        "specialist prescription and reimbursement review required. Commercial value remains uncertain."
    )
    output["competitors"].append(
        {
            "name": "Stopped program",
            "categories": ["discontinued"],
            "development_status": "discontinued",
            "discontinuation_reason": None,
            "discontinuation_reason_claim_ids": [],
            "discontinuation_unknowns": ["Reason not reported"],
            "claim_ids": ["market.comparator"],
        }
    )
    output["competitive_coverage"]["discontinued"] = {
        "status": "documented",
        "claim_ids": ["market.comparator"],
        "unknowns": [],
    }
    output["pricing_analogues"] = [
        {
            "name": "Synthetic analogue",
            "price_description": "Annual list price USD 100",
            "geography": "Region Y",
            "as_of_date": "2026-10-06",
            "comparability": "Illustrative only; indication differs",
            "limitations": ["List price is not net reimbursement"],
            "claim_ids": ["market.comparator"],
            "unknowns": [],
        }
    ]
    output["access"].update(
        reimbursement=["Review required"],
        prescribing=["Specialist prescription"],
        claim_ids=["market.comparator"],
    )
    adapter = type("Adapter", (), {})()
    adapter.generate_structured = AsyncMock(return_value=output)
    result = await analyze_market(
        case,
        pack,
        run_context(adapter),
        scenarios=[scenario(), scenario(name="upside", annual_price="200")],
    )
    competitive, commercial = [s.structured_data for s in result.section_content]
    assert competitive["competitors"]["discontinued"][0]["discontinuation_reason"] is None
    assert "Reason not reported" in result.unknowns
    assert commercial["pricing_analogues"][0]["comparability"].startswith("Illustrative")
    assert commercial["access"]["prescribing"] == ["Specialist prescription"]
    assert commercial["commercial_value"]["assessment"] == "insufficient_data"
    assert commercial["addressable_patients"][0]["eligible_patients"] == "500.0"
    assert Decimal(commercial["addressable_patients"][0]["accessible_patients"]) == 100
    assert Decimal(commercial["scenario_ranges"][0]["minimum"]) == 10000
    assert Decimal(commercial["scenario_ranges"][0]["maximum"]) == 20000
    assert commercial["diligence_questions"][0]["evidence_needed"]
    assert result.section_content[0].structured_data["prompt_version"] == "1.2.0"


def test_ranges_keep_contexts_separate_and_preserve_zero():
    from vic.agents.business.calculations import summarize_market_ranges

    values = estimate_market_scenarios(
        [
            scenario(annual_price="0"),
            scenario(name="upside", currency="EUR"),
            scenario(name="downside", annual_price=None),
        ]
    )
    ranges = summarize_market_ranges(values)
    assert len(ranges) == 2
    assert Decimal(ranges[0]["minimum"]) == 0
    assert ranges[0]["scenario_names"] == ["base"]
    assert ranges[1]["currency"] == "EUR"
    assert summarize_market_ranges([]) == []
    partial = estimate_market_scenarios([scenario(access_fraction=None)])[0]
    assert Decimal(partial["eligible_patients"]) == 500
    assert partial["addressable_patients"] is None


@pytest.mark.asyncio
async def test_explicit_r4_context_and_pending_alignment():
    case, pack, output = fixture()
    adapter = type("Adapter", (), {})()
    adapter.generate_structured = AsyncMock(return_value=output)
    upstream = await analyze_market(case, pack, run_context(adapter))
    from vic.contracts import RoleId

    upstream.role_id = RoleId.CLINICAL
    payload = prepare_market_inputs(case, pack, clinical=upstream)
    assert payload["clinical_input"]["role_id"] == "clinical"
    result = await analyze_market(case, pack, run_context(adapter), clinical=upstream)
    assert not any("alignment with R4 is pending" in gap for gap in result.unknowns)
    assert (
        "reconcile eligibility" in result.section_content[1].structured_data["clinical_alignment"]
    )
    upstream.claims[0].evidence_ids = ["different_snapshot"]
    with pytest.raises(ValueError, match="Clinical input"):
        prepare_market_inputs(case, pack, clinical=upstream)
