"""Offline synthetic checks, not model accuracy or live pipeline evaluation."""
from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from vic.agents.business.partnerships import (
    PartnershipsAnalysis,
    analyze_partnerships, identify_partnerships_gaps,
    prepare_partnerships_inputs, validate_partnerships_result,
)
from vic.contracts import CaseInput, EvidencePack, RoleResult, RunContext


def inputs(empty=False):
    case = CaseInput(indication="Synthetic disease", mechanism="Synthetic target", scope="approach")
    pack = EvidencePack(snapshot_id="snapshot-test", synthetic=True,
        sources=[] if empty else [dict(id="s1", title="Synthetic portfolio", type="synthetic",
            synthetic=True, retrieved_at="2026-10-06T00:00:00Z", content_hash="sha256:" + "a" * 64)],
        evidence=[] if empty else [dict(id="e1", source_id="s1", scope="approach",
            locator="portfolio", excerpt="Fictional Partner A researches synthetic target X.")])
    ctx = RunContext(case_id="case-test", run_id="run-test", snapshot_id="snapshot-test",
                     as_of_date=None, mode="evidence_only")
    return case, pack, ctx


def output(empty=False):
    def finding(basis="hypothesis"):
        return dict(value=None if basis == "unknown" else "Synthetic category fit to verify",
            basis=basis, claim_ids=[] if basis == "unknown" else ["partnerships.fit"],
            assumptions=["Synthetic proposal only"] if basis == "hypothesis" else [],
            unknowns=["Need confirmation"] if basis == "unknown" else [])
    return dict(summary="Synthetic candidate; interest unknown.", position="insufficient_data",
        claims=[dict(id="partnerships.fit", text="Synthetic partner category may fit",
            provenance="ai", support_status="unverified", evidence_ids=[],
            assumptions=["Synthetic category proposal"], scope="approach", importance="major")],
        candidates=[dict(id="partner_a", kind="category", identity=finding(),
            fit={k: finding() for k in ("work_direction", "portfolio", "capabilities", "partner_needs", "rationale")},
            required_competencies_and_resources=[finding()],
            collaboration_options=[dict(format=f, assessment="insufficient_data",
                rationale=finding("unknown"), prerequisites=["Verify rights and milestone"],
                unknowns=["Fit of format unknown"]) for f in
                ("joint_research", "co_development", "licensing", "acquisition")],
            project_offer=finding(), discussion_gaps=[dict(missing_result_or_data="Human relevance data",
                why_needed_for_discussion="Confirm rationale", evidence_needed="Reviewed R4 study")],
            timing=dict(stage=finding("unknown"), milestone=finding("unknown"),
                readiness="insufficient_data", conditions=["Review human relevance"]),
            dependencies=[dict(kind="ip_licensing", finding=finding("unknown"),
                impact="Rights uncertainty may block transfer", next_check="Review ownership")],
            risk_ids=["partnerships.rights"],
            next_checks=[dict(question="Does category fit?", evidence_needed="Reviewed portfolio",
                decision_if_positive="Retain candidate", decision_if_negative="Remove candidate", claim_ids=[])],
            investment_implications=[dict(finding=finding(), scenario_effect="Resources may affect financing",
                conditions=["Confirm actual resources"], next_check="Obtain resource plan")],
            partner_interest=finding("unknown"), deal_readiness=finding("unknown"))],
        candidate_search_unknowns=["Search not complete"],
        risks=[dict(id="partnerships.rights", description="Rights unknown", priority="major",
            claim_ids=["partnerships.fit"], impact="Transfer may be blocked", next_check="Review IP")],
        unknowns=["Synthetic case"],
        next_checks=[dict(question="Which candidates fit?", evidence_needed="Partner portfolio",
            decision_if_positive="Assess candidate", decision_if_negative="Seek another category", claim_ids=[])],
        change_conditions=["Verified fit changes shortlist"], limitations=["Synthetic test only"])


def validate(data, empty=False):
    case, pack, _ = inputs(empty)
    analysis = PartnershipsAnalysis.model_validate(data)
    validate_partnerships_result(analysis, case, pack)
    return analysis


@pytest.mark.parametrize("empty", [False, True])
def test_category_hypothesis_and_all_eight_outputs(empty):
    p = validate(output(empty), empty).candidates[0]
    assert p.identity and p.fit and len(p.collaboration_options) == 4
    assert p.project_offer and p.discussion_gaps and p.timing
    assert p.dependencies and p.risk_ids and p.next_checks


def test_documented_organization():
    data = output()
    data["claims"][0].update(support_status="supported", evidence_ids=["e1"], assumptions=[])
    p = data["candidates"][0]
    p["kind"] = "organization"
    def document(value):
        if isinstance(value, dict):
            if value.get("basis") == "hypothesis":
                value.update(basis="documented", assumptions=[])
            for child in value.values():
                document(child)
        elif isinstance(value, list):
            for child in value:
                document(child)
    document(p)
    p["identity"]["value"] = "Fictional Partner A"
    validate(data)


@pytest.mark.parametrize("defect", ["duplicate_claim", "evidence", "scope", "claim_ref",
    "documented", "hypothesis", "unknown_value", "unknown_gap", "organization", "formats",
    "format_gap", "risk_ref", "ip", "interest", "deal", "milestone", "duplicate_partner",
    "duplicate_risk", "risk_namespace", "risk_claim", "no_candidates", "blank", "extra"])
def test_reject_invalid_output(defect):
    d = output()
    p = d["candidates"][0]
    if defect == "duplicate_claim": d["claims"].append(deepcopy(d["claims"][0]))
    if defect == "evidence": d["claims"][0]["evidence_ids"] = ["missing"]
    if defect == "scope": d["claims"][0]["scope"] = "program"
    if defect == "claim_ref": p["identity"]["claim_ids"] = ["market.fit"]
    if defect == "documented": p["identity"]["basis"] = "documented"
    if defect == "hypothesis": p["identity"]["assumptions"] = []
    if defect == "unknown_value": p["partner_interest"]["value"] = "Interested"
    if defect == "unknown_gap": p["partner_interest"]["unknowns"] = []
    if defect == "organization": p["kind"] = "organization"
    if defect == "formats": p["collaboration_options"][0]["format"] = "licensing"
    if defect == "format_gap": p["collaboration_options"][0]["unknowns"] = []
    if defect == "risk_ref": p["risk_ids"] = ["missing"]
    if defect == "ip": p["dependencies"][0]["kind"] = "market"
    if defect in ("interest", "deal"):
        p["partner_interest" if defect == "interest" else "deal_readiness"] = deepcopy(p["identity"])
    if defect == "milestone": p["timing"]["readiness"] = "conditional"
    if defect == "duplicate_partner": d["candidates"].append(deepcopy(p))
    if defect == "duplicate_risk": d["risks"].append(deepcopy(d["risks"][0]))
    if defect == "risk_namespace": d["risks"][0]["id"] = "market.risk"
    if defect == "risk_claim": d["risks"][0]["claim_ids"] = []
    if defect == "no_candidates": d.update(candidates=[], candidate_search_unknowns=[])
    if defect == "blank": d["summary"] = "  "
    if defect == "extra": d["price"] = 100
    with pytest.raises((ValueError, ValidationError)):
        validate(d)


@pytest.mark.parametrize("field", ["identity", "fit", "collaboration_options", "project_offer",
    "discussion_gaps", "timing", "dependencies", "risk_ids", "next_checks"])
def test_missing_required_output(field):
    data = output()
    del data["candidates"][0][field]
    with pytest.raises(ValidationError): validate(data)


def test_no_candidates_has_actionable_gap():
    data = output()
    data["candidates"] = []
    validate(data, True)


@pytest.mark.parametrize("defect", ["snapshot", "date", "source", "duplicate_source", "role", "upstream_evidence", "upstream_snapshot"])
def test_invalid_inputs(defect):
    case, pack, ctx = inputs()
    market = None
    if defect == "snapshot": ctx.snapshot_id = "different"
    if defect == "date":
        case.as_of_date = date(2026, 10, 6)
        ctx.as_of_date = date(2026, 10, 7)
    if defect == "source": pack.evidence[0].source_id = "missing"
    if defect == "duplicate_source": pack.sources.append(pack.sources[0])
    if defect in ("role", "upstream_evidence", "upstream_snapshot"):
        market = RoleResult(role_id="clinical" if defect == "role" else "market", summary="Synthetic", position="unknown")
        if defect == "upstream_evidence":
            market.claims = [dict()]
            from vic.contracts import Claim
            market.claims = [Claim(id="market.fit", text="Synthetic", provenance="source",
                support_status="supported", evidence_ids=["missing"], scope="approach", importance="major")]
        if defect == "upstream_snapshot":
            market.section_content = [dict()]
            from vic.contracts import SectionContent
            market.section_content = [SectionContent(key="commercial_opportunity", summary="Synthetic",
                structured_data={"market": {"snapshot_id": "different"}})]
    with pytest.raises(ValueError): prepare_partnerships_inputs(case, pack, ctx, market=market)


def test_synthetic_ip_context_from_serialized_role_result():
    case, pack, ctx = inputs()
    ip = RoleResult(role_id="ip_licensing", summary="Synthetic IP: ownership unknown", position="insufficient_data",
        unknowns=["Ownership requires review"], section_content=[dict(key="critical_unknowns",
        summary="Synthetic", structured_data={"ip_licensing": {"snapshot_id": pack.snapshot_id}})])
    payload = prepare_partnerships_inputs(case, pack, ctx, ip_licensing=ip.model_dump(mode="json"))
    assert payload["upstream_context"]["ip_licensing"]["unknowns"] == ip.unknowns
    assert payload["context_availability"]["ip_licensing"] is True
    assert payload["sources"][0]["content_hash"] == pack.sources[0].content_hash
    assert payload["evidence"][0]["excerpt"] == pack.evidence[0].excerpt


def test_upstream_unknown_claim_preserved_without_partnership_output_assumptions():
    case, pack, ctx = inputs()
    clinical = RoleResult(role_id="clinical", summary="Endpoint unknown", position="insufficient_data",
        claims=[dict(id="clinical.endpoint", text="Endpoint not established", provenance="ai",
                     support_status="unknown", evidence_ids=[], assumptions=[], scope="approach",
                     importance="major")], unknowns=["Endpoint evidence missing"])
    payload = prepare_partnerships_inputs(case, pack, ctx, clinical=clinical)
    assert payload["upstream_context"]["clinical"] == clinical.model_dump(mode="json")
    own = output()
    own["claims"][0]["assumptions"] = []
    with pytest.raises(ValueError, match="assumptions"):
        validate(own)


@pytest.mark.asyncio
@pytest.mark.parametrize("empty", [False, True])
async def test_one_call_and_complete_result(empty):
    case, pack, ctx = inputs(empty)
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(return_value=output(empty)))
    result = await analyze_partnerships(case, pack, ctx)
    assert type(result) is RoleResult
    assert RoleResult.model_validate(result.model_dump(mode="json")) == result
    assert result.role_id == "partnerships"
    ctx.model.generate_structured.assert_awaited_once()
    args = ctx.model.generate_structured.call_args.args
    assert args[0] == "partnerships" and args[2] is PartnershipsAnalysis
    data = result.section_content[0].structured_data["partnerships"]
    assert data["synthetic"] and data["snapshot_id"] == pack.snapshot_id
    assert len(data["candidates"][0]["collaboration_options"]) == 4
    assert any("ip_licensing context absent" in x for x in result.unknowns)
    assert data["claim_evidence_links"] == {"partnerships.fit": []}


@pytest.mark.asyncio
async def test_missing_adapter_and_invalid_model_output():
    case, pack, ctx = inputs()
    with pytest.raises(RuntimeError): await analyze_partnerships(case, pack, ctx)
    data = output()
    data["candidates"][0]["partner_interest"]["value"] = "Invented interest"
    ctx.model = SimpleNamespace(generate_structured=AsyncMock(return_value=data))
    with pytest.raises(ValueError): await analyze_partnerships(case, pack, ctx)


def test_gap_collection_deduplicates():
    analysis = validate(output())
    gaps = identify_partnerships_gaps(analysis)
    assert gaps.count("Need confirmation") == 1
    assert any("Human relevance data" in g for g in gaps)
