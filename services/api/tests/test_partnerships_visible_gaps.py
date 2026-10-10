import asyncio
import dataclasses
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from tests.vic.agents.business.test_partnerships import inputs, output
from vic.agents.business.partnerships import (PartnershipsAnalysis, analyze_partnerships,
    qualify_missing_claim_basis, validate_partnerships_result)


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['unknown', 'unverified'])
async def test_missing_basis_becomes_visible_gap_without_changing_claim_status(status):
    case, pack, ctx = inputs()
    raw = output()
    raw['claims'][0]['support_status'] = status
    raw['claims'][0]['assumptions'] = []
    original = deepcopy(raw)
    ctx.model = type('Adapter', (), {'generate_structured': AsyncMock(return_value=raw)})()
    result = await analyze_partnerships(case, pack, ctx)
    assert result.position == 'insufficient_data'
    assert result.claims[0].support_status.value == status
    assert result.claims[0].text == original['claims'][0]['text']
    assert result.claims[0].evidence_ids == []
    assert 'no assumptions' in result.claims[0].assumptions[0]
    assert any('Unverified basis' in gap for gap in result.unknowns)
    assert any('Partial Partnerships' in limitation for limitation in result.section_content[0].limitations)
    assert raw == original
    fixed = qualify_missing_claim_basis(PartnershipsAnalysis.model_validate(raw))
    assert qualify_missing_claim_basis(fixed) == fixed


def test_factual_claim_missing_evidence_still_fails():
    case, pack, _ = inputs()
    raw = output()
    raw['claims'][0]['support_status'] = 'supported'
    raw['claims'][0]['evidence_ids'] = []
    with pytest.raises(ValueError, match='requires evidence_ids'):
        qualify_missing_claim_basis(PartnershipsAnalysis.model_validate(raw))


def test_saved_partnerships_result_allows_investment_and_chair_to_run(tmp_path):
    from tests.test_pipeline import Env
    from vic.stubs import make_stub_modules
    case, pack, ctx = inputs()
    raw = output()
    raw['claims'][0]['assumptions'] = []
    raw['candidates'][0]['fit']['rationale']['assumptions'] = []
    ctx.model = type('Adapter', (), {'generate_structured': AsyncMock(return_value=raw)})()
    result = asyncio.run(analyze_partnerships(case, pack, ctx))
    async def partnerships(*args, **kwargs):
        return result
    env = Env(tmp_path, dataclasses.replace(make_stub_modules(), analyze_partnerships=partnerships))
    run = env.run()
    assert run.status.value == 'completed', run.error
    nodes = {n.role_id.value: n for n in env.repo.get_nodes(run.id)}
    for role in ('partnerships', 'investment', 'investment_threshold', 'failure_miner', 'chair'):
        assert nodes[role].status == 'completed'
        assert nodes[role].result is not None
    assert 'Partial Partnerships' in nodes['partnerships'].result.summary


def test_hypothesis_linked_to_supported_fact_becomes_unknown_without_downgrading_fact():
    from vic.agents.business.partnerships import qualify_inconsistent_hypotheses
    case, pack, _ = inputs()
    raw = output()
    raw['claims'][0]['support_status'] = 'supported'
    raw['claims'][0]['evidence_ids'] = ['e1']
    original = deepcopy(raw)
    fixed = qualify_inconsistent_hypotheses(PartnershipsAnalysis.model_validate(raw))
    validate_partnerships_result(fixed, case, pack)
    assert fixed.claims[0].support_status.value == 'supported'
    assert fixed.claims[0].evidence_ids == ['e1']
    assert fixed.candidates == []  # Its identity was also an inconsistent hypothesis.
    assert fixed.position == 'insufficient_data'
    assert fixed.candidate_search_unknowns
    assert any('Unresolved hypothesis' in gap for gap in fixed.unknowns)
    assert raw == original
    assert qualify_inconsistent_hypotheses(fixed) == fixed
