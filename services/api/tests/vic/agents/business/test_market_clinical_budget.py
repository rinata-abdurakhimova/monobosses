"""Oversized R4 context must fit without losing safety, provenance or audit feedback."""
import copy
import json

import pytest

from tests.vic.agents.business.test_market import fixture, run_context, split_output
from vic.agents.business.market import (
    PASS_MODELS,
    analyze_market,
    plan_market_batches,
    prepare_market_inputs,
    project_clinical_context,
    run_market_pass,
)
from vic.config import Settings
from vic.contracts import AuditFinding, Claim, Evidence, Risk, RoleResult
from vic.failures import RunFailure
from vic.llm import ProviderResponse, StructuredLlm, request_sizes, structured_request


def large_clinical():
    return RoleResult(role_id="clinical", summary="Clinical summary", position="insufficient_data",
        claims=[Claim(id=f"clinical.context_{i}", text=f"Context {i}: " + "Unresolved clinical premise. " * 30,
                      provenance="ai", support_status="contradicted" if i == 0 else "unknown",
                      evidence_ids=["e1"], scope="approach", importance="critical") for i in range(10)],
        risks=[Risk(id="clinical.risk.safety", description="Decisive liver safety concern. " * 20,
                    priority="critical", claim_ids=["clinical.context_0"], impact="Patient harm",
                    next_check="Review tolerated exposure")],
        unknowns=[f"Unknown {i}: " + "Long-term safety remains unknown. " * 15 for i in range(8)],
        change_conditions=["Relevant safe-exposure evidence is needed."])


@pytest.mark.asyncio
async def test_clinical_and_evidence_batches_preserve_all_exact_records_and_conflicts():
    case, pack, output = fixture()
    for i in range(5):
        pack.evidence.append(Evidence(id=f"extra_{i}", source_id="s1", scope="approach", locator=f"page {i}",
                                      excerpt=f"Evidence {i}: " + "Exact untrimmed source text. " * 30))
    clinical = large_clinical()
    calls = []

    class Adapter:
        market_request_budget = 18000

        async def generate_structured(self, task, payload, schema, ctx):
            calls.append((task, payload, ctx))
            raw = copy.deepcopy(split_output(output, task))
            raw["claims"][0]["evidence_ids"] = [payload["evidence"][0]["id"]]
            context = payload["clinical_input"]
            raw["claims"][0]["text"] = "Batch context: " + ", ".join(payload["coverage"]["clinical_context_ids"])
            if any(c["support_status"] == "contradicted" for c in context["claims"]):
                raw["claims"][0]["support_status"] = "contradicted"
            raw["unknowns"].extend(context["unknowns"])
            raw["risks"] = [{"id": "market.risk.context_gap", "description": raw["claims"][0]["text"],
                             "priority": "major", "claim_ids": [], "impact": "Unresolved clinical context",
                             "next_check": "Review all context batches"}]
            return raw

    ctx = run_context(Adapter())
    ctx.feedback["market"] = [AuditFinding(claim_id="market.safety", verdict="contradicted",
        reason="Preserve candidate-specific liver safety", evidence_ids=["e1"], blocking=True)]
    result = await analyze_market(case, pack, ctx, clinical=clinical)
    assert len(calls) > 2
    for task in PASS_MODELS:
        requests = [(p, c) for t, p, c in calls if t == task]
        expected = project_clinical_context(clinical, task)
        for field in ("claims", "risks", "unknowns", "change_conditions", "limitations", "unclaimed_context"):
            actual = {json.dumps(item, sort_keys=True) for p, _ in requests for item in p["clinical_input"][field]}
            assert actual == {json.dumps(item, sort_keys=True) for item in expected[field]}
        grouped = {}
        for payload, child in requests:
            _, system, messages = structured_request(task, payload, PASS_MODELS[task], child)
            assert request_sizes(system, messages)["request_bytes"] <= 13500
            assert "candidate-specific liver safety" in messages[-1]["content"]
            assert payload["coverage"]["partial_clinical_context"]
            key = tuple(payload["coverage"]["clinical_context_ids"])
            grouped.setdefault(key, set()).update(e["id"] for e in payload["evidence"])
            for evidence in payload["evidence"]:
                assert evidence["excerpt"] == next(e.excerpt for e in pack.evidence if e.id == evidence["id"])
        assert all(ids == {e.id for e in pack.evidence} for ids in grouped.values())
    assert len({c.id for c in result.claims}) == len(result.claims)
    assert len({r.id for r in result.risks}) == len(result.risks)
    assert len(result.risks) > 1
    assert any(c.support_status == "contradicted" for c in result.claims)
    assert set(clinical.unknowns) <= set(result.unknowns)
    assert result.position != "favorable"


def test_indivisible_clinical_record_fails_without_truncation():
    case, pack, _ = fixture()
    clinical = large_clinical()
    clinical.claims[0].text = "Critical safety detail. " * 2000
    payload = prepare_market_inputs(case, pack, clinical=clinical)
    with pytest.raises(RunFailure, match="One exact Clinical context record"):
        plan_market_batches(payload, clinical, "market_commercial", run_context())


@pytest.mark.asyncio
async def test_reference_repair_keeps_original_context_and_audit_without_large_output_history():
    case, pack, output = fixture()
    calls = []

    class Provider:
        async def complete(self, *, system, messages, **kwargs):
            task = "market_competitive" if "Market competitive" in system else "market_commercial"
            calls.append((task, messages))
            raw = copy.deepcopy(split_output(output, task))
            if task == "market_competitive" and "Differentiation must reference" not in messages[-1]["content"]:
                raw["differentiation"] = [{"comparator": "Unidentified standard of care", "dimension": "safety",
                                          "assessment": "Unknown", "claim_ids": ["market.comparator"]}]
            return ProviderResponse(json.dumps(raw), 100, 100)

    adapter = StructuredLlm(Provider(), Settings(_env_file=None))
    ctx = run_context(adapter)
    ctx.feedback["market"] = ["Original audit: preserve the safety gap."]
    result = await analyze_market(case, pack, ctx)
    competitive = [messages for task, messages in calls if task == "market_competitive"]
    assert len(competitive) == 2
    assert competitive[0][0] == competitive[1][0]
    assert len(competitive[1]) == 2
    assert all(m["role"] != "assistant" for m in competitive[1])
    assert "Original audit" in competitive[1][1]["content"]
    assert "Differentiation must reference" in competitive[1][1]["content"]
    assert result.role_id == "market"


@pytest.mark.asyncio
async def test_invalid_reference_repair_is_bounded():
    case, pack, output = fixture()
    count = 0

    class Adapter:
        async def generate_structured(self, *args):
            nonlocal count
            count += 1
            raw = copy.deepcopy(split_output(output, "market_competitive"))
            raw["differentiation"] = [{"comparator": "Unknown comparator", "dimension": "safety",
                                      "assessment": "Unknown", "claim_ids": ["market.comparator"]}]
            return raw

    ctx = run_context(Adapter())
    batches = plan_market_batches(prepare_market_inputs(case, pack), None, "market_competitive", ctx)
    with pytest.raises(ValueError, match="Differentiation must reference"):
        await run_market_pass("market_competitive", batches, ctx)
    assert count == 2


@pytest.mark.asyncio
async def test_context_only_supported_claim_gets_one_fresh_bounded_correction():
    case, pack, output = fixture()
    contexts = []

    class Adapter:
        async def generate_structured(self, task, payload, model, ctx):
            contexts.append(ctx)
            raw = copy.deepcopy(split_output(output, task))
            if len(contexts) == 1:
                raw["claims"][0].update(support_status="supported", evidence_ids=[])
            return raw

    ctx = run_context(Adapter())
    ctx.feedback["market"] = ["Preserve the safety gap"]
    batches = plan_market_batches(prepare_market_inputs(case, pack), None, "market_competitive", ctx)
    result = await run_market_pass("market_competitive", batches, ctx)
    assert result and len(contexts) == 2
    assert contexts[1].feedback["market"][0] == "Preserve the safety gap"
    assert "require supplied evidence IDs" in contexts[1].feedback["market"][-1]


def test_large_market_audit_feedback_is_partitioned_losslessly_with_measured_requests():
    case, pack, _ = fixture()
    adapter = StructuredLlm(type('Provider', (), {'name': 'fake'})(), Settings(_env_file=None))
    ctx = run_context(adapter)
    findings = [AuditFinding(claim_id=f'market.claim_{i}', verdict='unverified',
                reason=f'Finding {i}: ' + 'Missing safety information. ' * 18,
                evidence_ids=['e1'], blocking=True) for i in range(12)]
    ctx.feedback['market'] = findings
    batches = plan_market_batches(prepare_market_inputs(case, pack), None, 'market_competitive', ctx)
    groups = {batch['coverage']['audit_feedback_batch_id']: batch['_market_audit_feedback'] for batch in batches}
    assert len(groups) > 1
    assert sorted(item['claim_id'] for group in groups.values() for item in group) == sorted(f.claim_id for f in findings)
    assert all(item['blocking'] for group in groups.values() for item in group)
    for batch in batches:
        _, system, messages = structured_request('market_competitive', batch, PASS_MODELS['market_competitive'], ctx)
        assert request_sizes(system, messages)['request_bytes'] <= 13500
        assert '_market_audit_feedback' not in messages[0]['content']
        assert all(item['reason'] in json.loads(messages[1]['content'].split(': ', 1)[1])[i]['reason']
                   for i, item in enumerate(batch['_market_audit_feedback']))
