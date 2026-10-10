"""Status conflicts get correction, then visible partial results instead of a crash."""
import copy
import json

import pytest

from tests.vic.agents.business.test_market import fixture, run_context, split_output
from vic.agents.business.market import analyze_market
from vic.config import Settings
from vic.llm import ProviderResponse, StructuredLlm


class StatusProvider:
    name = 'test'

    def __init__(self, always_invalid=False):
        self.always_invalid = always_invalid
        self.calls = []
        self.competitive_calls = 0

    async def complete(self, *, system, messages, **kwargs):
        task = 'market_competitive' if 'competitive v2' in system else 'market_commercial'
        self.calls.append((task, messages))
        raw = copy.deepcopy(split_output(fixture()[2], task))
        if task == 'market_competitive':
            self.competitive_calls += 1
            if self.always_invalid or self.competitive_calls == 1:
                # Exact live failure: status-tag and declared development status disagree.
                raw['competitors'][0]['categories'].append('clinical_stage')
        return ProviderResponse(json.dumps(raw), 100, 50)


@pytest.mark.asyncio
async def test_status_conflict_is_repaired_before_market_final_validation():
    case, pack, _ = fixture()
    provider = StatusProvider()
    adapter = StructuredLlm(provider, Settings(_env_file=None, provider_input_limit_test=True))
    ctx = run_context(adapter)
    ctx.feedback['market'] = ['Keep the safety concern visible.']
    result = await analyze_market(case, pack, ctx)
    assert result.role_id.value == 'market'
    assert provider.competitive_calls == 2
    messages = [m for t, m in provider.calls if t == 'market_competitive'][1]
    assert 'Synthetic comparator' in messages[-1]['content']
    assert 'development_status' in messages[-1]['content']
    assert 'Keep the safety concern' in messages[-1]['content']
    assert messages[0]['content'] == [m for t, m in provider.calls if t == 'market_competitive'][0][0]['content']
    landscape = result.section_content[0].structured_data
    assert landscape['competitors']['approved']
    assert not any('Partial Market' in text for text in result.section_content[0].limitations)


@pytest.mark.asyncio
async def test_unrepaired_status_conflict_returns_visible_valid_partial_role_result():
    case, pack, _ = fixture()
    provider = StatusProvider(always_invalid=True)
    adapter = StructuredLlm(provider, Settings(_env_file=None, provider_input_limit_test=True))
    ctx = run_context(adapter)
    result = await analyze_market(case, pack, ctx)
    assert result.role_id.value == 'market'
    assert result.position == 'insufficient_data'
    assert provider.competitive_calls == 2
    assert 'Partial Market result' in result.summary
    assert any('Synthetic comparator' in gap and 'classification' in gap for gap in result.unknowns)
    assert any('Partial Market result' in text for text in result.section_content[0].limitations)
    landscape = result.section_content[0].structured_data
    assert all(not entries for entries in landscape['competitors'].values())
    for tag in ('approved', 'clinical_stage', 'same_target'):
        assert landscape['coverage'][tag]['status'] == 'insufficient_data'
        assert landscape['coverage'][tag]['unknowns']
    # Commercial output and evidence-backed claims are preserved for downstream audit.
    assert len(result.section_content) == 2
    assert result.claims and all(c.evidence_ids == ['e1'] for c in result.claims)
    assert any('partial result' in e['message'] for e in ctx.trace.events)


def test_partial_market_is_saved_and_pipeline_runs_later_nodes(tmp_path):
    import asyncio
    import dataclasses
    from tests.test_pipeline import Env
    from vic.stubs import make_stub_modules
    case, pack, _ = fixture()
    provider = StatusProvider(always_invalid=True)
    adapter = StructuredLlm(provider, Settings(_env_file=None, provider_input_limit_test=True))
    partial = asyncio.run(analyze_market(case, pack, run_context(adapter)))
    async def partial_market(*args, **kwargs):
        return partial
    base = make_stub_modules()
    async def combined_evidence(case, ctx):
        original = await base.build_evidence_pack(case, ctx)
        return original.model_copy(update={'sources': [*original.sources, *pack.sources],
            'evidence': [*original.evidence, *pack.evidence]})
    modules = dataclasses.replace(base, analyze_market=partial_market, build_evidence_pack=combined_evidence)
    env = Env(tmp_path, modules)
    run = env.run()
    assert run.status.value == 'completed', run.error
    nodes = {n.role_id.value: n for n in env.repo.get_nodes(run.id)}
    assert nodes['market'].status == 'completed'
    assert 'Partial Market result' in nodes['market'].result.summary
    for role in ('ip_licensing', 'partnerships', 'investment', 'chair'):
        assert nodes[role].status == 'completed'
        assert nodes[role].result is not None
