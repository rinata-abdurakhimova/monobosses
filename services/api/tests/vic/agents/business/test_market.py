import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from vic.agents.business.calculations import MarketScenario, estimate_market_scenarios
from vic.agents.business.market import (
    MarketAnalysis,
    CompetitiveAnalysis,
    CommercialAnalysis,
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



def split_output(output, task):
    schema = CompetitiveAnalysis if task == "market_competitive" else CommercialAnalysis
    result = {key: output[key] for key in schema.model_fields if key in output}
    if task == "market_commercial":
        result["summary"] = output["commercial_summary"]
    return result


def split_adapter(output):
    adapter = type("Adapter", (), {})()
    adapter.generate_structured = AsyncMock(side_effect=lambda task, payload, schema, ctx:
                                            split_output(output, task))
    return adapter

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
async def test_two_adapter_calls_and_both_sections():
    case, pack, output = fixture()
    adapter = split_adapter(output)
    result = await analyze_market(case, pack, run_context(adapter))
    assert adapter.generate_structured.await_count == 2
    assert {c.args[0] for c in adapter.generate_structured.call_args_list} == {"market_competitive", "market_commercial"}
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
    adapter = split_adapter(output)
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
    adapter = split_adapter(output)
    result = await analyze_market(case, pack, run_context(adapter))
    commercial = result.section_content[1].model_dump(mode="json")
    population = commercial["structured_data"]["target_population"]
    assert population["description"] == "Adults with disease X"
    assert population["claim_ids"][0].startswith("market.competitive_population_")
    assert "Reimbursement unknown" in result.unknowns
    assert population["claim_ids"][0] in commercial["claim_ids"]


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
    adapter = split_adapter(output)
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
    assert result.section_content[0].structured_data["prompt_version"] == "2.1.0"


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
    adapter = split_adapter(output)
    upstream = await analyze_market(case, pack, run_context(adapter))
    from vic.contracts import RoleId

    upstream.role_id = RoleId.CLINICAL
    payload = prepare_market_inputs(case, pack, clinical=upstream)
    assert "role_id" not in payload["clinical_input"]
    assert payload["clinical_input"]["claims"]
    result = await analyze_market(case, pack, run_context(adapter), clinical=upstream)
    assert not any("alignment with R4 is pending" in gap for gap in result.unknowns)
    assert (
        "reconcile eligibility" in result.section_content[1].structured_data["clinical_alignment"]
    )
    upstream.claims[0].evidence_ids = ["different_snapshot"]
    with pytest.raises(ValueError, match="Clinical input"):
        prepare_market_inputs(case, pack, clinical=upstream)


# Split/batching regressions: exercise behavior, not only class construction.
import asyncio
import copy
import json
from vic.agents.business.market import (
    PASS_MODELS, merge_market_results, namespace_pass, plan_market_batches,
    prepare_pass_inputs, project_clinical_context, _pass_context,
)
from vic.config import Settings
from vic.contracts import AuditFinding, Claim, RoleResult
from vic.failures import RunFailure
from vic.llm import ProviderResponse, StructuredLlm, request_sizes, structured_request
from vic.prompts import available_prompts


@pytest.mark.asyncio
async def test_split_calls_overlap_and_have_distinct_schemas():
    case, pack, output = fixture()
    both_started = asyncio.Event()
    calls = []
    class Adapter:
        async def generate_structured(self, task, payload, schema, ctx):
            calls.append((task, payload, schema))
            if len(calls) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), 1)
            return split_output(output, task)
    result = await analyze_market(case, pack, run_context(Adapter()), scenarios=[scenario()])
    assert [c[2] for c in calls] == [CompetitiveAnalysis, CommercialAnalysis]
    assert calls[0][1]["calculated_scenarios"] == []
    assert calls[1][1]["calculated_scenarios"]
    assert "target_population" not in calls[0][2].model_fields
    assert "competitors" not in calls[1][2].model_fields
    assert len(result.claims) == 1  # exact shared fact deduplicated with links remapped
    assert set(available_prompts()) >= set(PASS_MODELS)
    assert result.section_content[1].structured_data["pricing_unknowns"]


def test_r4_projection_preserves_safety_and_drops_nested_results():
    case, pack, _ = fixture()
    def claim(key, importance="major"):
        return Claim(id=key, text=key, provenance="ai", support_status="supported",
                     evidence_ids=["e1"], scope="approach", importance=importance)
    clinical = RoleResult(role_id="clinical", summary="do not copy full thesis", position="unknown",
        claims=[claim("clinical.target_population"), claim("clinical.comparator_choice"),
                claim("clinical.safety_requirements", "critical"), claim("clinical.study_sequence")])
    payload = prepare_market_inputs(case, pack, clinical=clinical)
    for task in PASS_MODELS:
        data = prepare_pass_inputs(payload, clinical, task, payload["evidence"])
        text = json.dumps(data, default=str)
        assert "section_content" not in text and "do not copy full thesis" not in text
        assert "clinical.safety_requirements" in [c["id"] for c in data["clinical_input"]["claims"]]
        assert "clinical.study_sequence" in data["clinical_input"]["excluded_claim_ids"]
        assert data["sources"]["s1"]["synthetic"]
        assert data["evidence"][0]["excerpt"] == pack.evidence[0].excerpt
        assert "source_title" not in data["evidence"][0]


def test_stable_claim_ids_deduplication_and_collisions():
    _, _, output = fixture()
    raw = CompetitiveAnalysis(**split_output(output, "market_competitive"))
    first = namespace_pass(raw, "market_competitive")
    assert namespace_pass(raw, "market_competitive").claims[0].id == first.claims[0].id
    commercial = namespace_pass(CommercialAnalysis(**split_output(output, "market_commercial")), "market_commercial")
    assert len(merge_market_results([first, first], [commercial]).claims) == 1
    changed = first.model_copy(deep=True)
    changed.claims[0].text = "Different content under the same stable ID"
    with pytest.raises(ValueError, match="Conflicting Market ID"):
        merge_market_results([first, changed], [commercial])
    raw.claims.append(raw.claims[0].model_copy(update={"text": "collision"}))
    with pytest.raises(ValueError, match="Conflicting claim ID"):
        namespace_pass(raw, "market_competitive")


def test_missing_categories_fail_and_positive_position_is_conservative():
    _, _, output = fixture()
    competitive = namespace_pass(CompetitiveAnalysis(**split_output(output, "market_competitive")), "market_competitive")
    commercial = namespace_pass(CommercialAnalysis(**split_output(output, "market_commercial")), "market_commercial")
    competitive.position = commercial.position = "favorable"
    assert merge_market_results([competitive], [commercial]).position == "insufficient_data"


@pytest.mark.asyncio
async def test_large_pack_batches_and_keeps_last_decisive_contradiction():
    case, pack, output = fixture()
    for n in range(30):
        pack.evidence.append(Evidence(id=f"extra_{n}", source_id="s1", scope="approach",
            locator=f"page {n}", excerpt="Synthetic background detail. " * 35,
            limitations=["Synthetic; population uncertain"]))
    pack.evidence.append(Evidence(id="last_contradiction", source_id="s1", scope="approach",
        locator="final safety finding", excerpt="Synthetic decisive safety contradiction: comparator not approved."))
    calls = []
    class Adapter:
        market_request_budget = 15000
        async def generate_structured(self, task, payload, schema, ctx):
            calls.append((task, payload, ctx))
            raw = copy.deepcopy(split_output(output, task))
            visible = {e["id"] for e in payload["evidence"]}
            raw["claims"] = []
            if task == "market_competitive":
                raw["competitors"] = []
                for finding in raw["competitive_coverage"].values():
                    finding.update(status="insufficient_data", claim_ids=[], unknowns=["Batch-local gap"])
            if "last_contradiction" in visible:
                claim = copy.deepcopy(output["claims"][0])
                claim.update(id="market.safety", text="Decisive safety contradiction",
                             evidence_ids=["last_contradiction"], support_status="contradicted", importance="critical")
                raw["claims"] = [claim]
                raw["unknowns"].append("Resolve decisive safety contradiction")
            return raw
    context = run_context(Adapter())
    result = await analyze_market(case, pack, context)
    assert len(calls) > 2
    for task in PASS_MODELS:
        seen = [e["id"] for t, payload, _ in calls if t == task for e in payload["evidence"]]
        assert set(seen) == {e.id for e in pack.evidence}
        assert len(seen) == len(pack.evidence)
    assert any(c.support_status == "contradicted" and c.evidence_ids == ["last_contradiction"] for c in result.claims)
    for task, payload, child in calls:
        _, system, messages = structured_request(task, payload, PASS_MODELS[task], child)
        assert request_sizes(system, messages)["request_bytes"] <= 15000 * .75
    assert all(set(c.evidence_ids) <= {e.id for e in pack.evidence} for c in result.claims)
    assert result.position != "favorable"


@pytest.mark.asyncio
async def test_oversized_single_excerpt_fails_before_any_call():
    case, pack, output = fixture()
    pack.evidence[0].excerpt = "Synthetic intact quotation " * 2000
    adapter = split_adapter(output)
    with pytest.raises(RunFailure, match="One exact Market excerpt"):
        await analyze_market(case, pack, run_context(adapter))
    adapter.generate_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_cannot_cite_unseen_evidence():
    case, pack, output = fixture()
    output["claims"][0]["evidence_ids"] = ["not_in_batch"]
    with pytest.raises(ValueError, match="outside its batch"):
        await analyze_market(case, pack, run_context(split_adapter(output)))


@pytest.mark.asyncio
async def test_failing_stream_cancels_sibling():
    case, pack, _ = fixture()
    started, cancelled = asyncio.Event(), asyncio.Event()
    class Adapter:
        async def generate_structured(self, task, *args):
            if task == "market_competitive":
                await started.wait()
                raise ValueError("competitive failed")
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
    with pytest.raises(ValueError, match="competitive failed"):
        await analyze_market(case, pack, run_context(Adapter()))
    assert cancelled.is_set()


def test_conflicting_population_and_value_are_retained_as_gaps():
    _, _, output = fixture()
    first = CommercialAnalysis(**split_output(output, "market_commercial"))
    second = first.model_copy(deep=True)
    first.target_population.description = "Adults"
    second.target_population.description = "Children"
    competitive = CompetitiveAnalysis(**split_output(output, "market_competitive"))
    result = merge_market_results([competitive], [first, second])
    assert "Adults" in result.target_population.description
    assert "Children" in result.target_population.description
    assert any("differs across batches" in gap for gap in result.unknowns)


def test_shared_audit_feedback_reaches_both_passes_with_ids_normalized():
    context = run_context()
    context.feedback["market"] = [AuditFinding(claim_id=f"market.{part}_safety_abcdef012345",
        verdict="contradicted", reason=part, evidence_ids=["e1"], blocking=True)
        for part in ("competitive", "commercial")]
    for task in PASS_MODELS:
        child = _pass_context(context, task)
        assert len(child.feedback["market"]) == 2
        assert child.feedback["market"][0].claim_id == "market.safety"
        assert {f.reason for f in child.feedback["market"]} == {"competitive", "commercial"}
    assert context.feedback["market"][0].claim_id.startswith("market.competitive_")


@pytest.mark.asyncio
async def test_real_adapter_repairs_and_unknown_cost_without_network():
    case, pack, output = fixture()
    calls = []
    class Provider:
        async def complete(self, *, system, messages, **kwargs):
            calls.append((system, messages))
            if len(messages) == 1:
                return ProviderResponse("not json", None, None)
            task = "market_competitive" if "competitive v2" in system else "market_commercial"
            return ProviderResponse(json.dumps(split_output(output, task)), None, None)
    adapter = StructuredLlm(Provider(), Settings(_env_file=None, llm_max_retries=0))
    context = run_context(adapter)
    result = await analyze_market(case, pack, context)
    assert result.role_id == "market" and len(calls) == 4
    assert context.budget.cost_unavailable
    assert all(u["cost_usd"] is None for u in context.trace.usage)
    assert {u["prompt_id"] for u in context.trace.usage} == set(PASS_MODELS)
    assert all(request_sizes(s, m)["request_bytes"] <= adapter.market_request_budget for s, m in calls)
    assert all("not json" not in e["message"] for e in context.trace.events)


@pytest.mark.asyncio
async def test_adapter_rejects_oversized_schema_repair_before_second_call():
    calls = []
    class Provider:
        async def complete(self, **kwargs):
            calls.append(kwargs)
            return ProviderResponse("invalid private text " * 2000, None, None)
    adapter = StructuredLlm(Provider(), Settings(_env_file=None, market_request_max_bytes=18000))
    context = run_context(adapter)
    with pytest.raises(RunFailure, match="configured byte budget"):
        await adapter.generate_structured("market_competitive", {}, CompetitiveAnalysis, context)
    assert len(calls) == 1
    assert "private text" not in json.dumps(context.trace.events)


@pytest.mark.asyncio
async def test_adapter_checks_audit_feedback_size_and_full_envelope():
    class Provider:
        async def complete(self, **kwargs):
            raise AssertionError("must not call provider")
    adapter = StructuredLlm(Provider(), Settings(_env_file=None))
    context = run_context(adapter)
    context.feedback["market"] = ["very large audit feedback " * 2000]
    with pytest.raises(RunFailure, match="configured byte budget"):
        await adapter.generate_structured("market_commercial", {}, CommercialAnalysis, context)
    sizes = adapter.structured_request_size("market_commercial", {}, CommercialAnalysis, context)
    assert sizes["feedback_repair_bytes"] > 18000
    assert sizes["request_bytes"] > sizes["system_bytes"] + sizes["messages_bytes"]


@pytest.mark.asyncio
async def test_audited_split_rerun_preserves_stable_ids_and_feedback():
    case, pack, output = fixture()
    calls = []
    class Provider:
        async def complete(self, *, system, messages, **kwargs):
            task = "market_competitive" if "competitive v2" in system else "market_commercial"
            calls.append((task, messages))
            return ProviderResponse(json.dumps(split_output(output, task)), 100, 50)
    adapter = StructuredLlm(Provider(), Settings(_env_file=None))
    context = run_context(adapter)
    first = await analyze_market(case, pack, context)
    context.feedback["market"] = [AuditFinding(claim_id=first.claims[0].id,
        verdict="mixed", reason="Review synthetic evidence", evidence_ids=["e1"], blocking=True)]
    second = await analyze_market(case, pack, context)
    assert [c.id for c in first.claims] == [c.id for c in second.claims]
    repaired = [(task, messages) for task, messages in calls[2:] if len(messages) > 1]
    assert {task for task, _ in repaired} == set(PASS_MODELS)
    assert "market.comparator" in repaired[0][1][-1]["content"]
    assert all(u["prompt_version"] for u in context.trace.usage)
