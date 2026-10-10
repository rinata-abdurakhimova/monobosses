"""Provider-limit diagnostics must reach the gateway with complete inputs."""
import json
import time

import httpx
import pytest
from pydantic import BaseModel

from vic.config import Settings
from vic.contracts import RunBudget, RunContext, RunMode
from vic.failures import ProviderError
from vic.llm import OpenAICompatibleProvider, ProviderResponse, StructuredLlm


class Answer(BaseModel):
    answer: str


def settings(**kwargs):
    return Settings(_env_file=None, provider_input_limit_test=True,
        enforce_node_request_budget=True, node_request_max_bytes=1,
        node_initial_request_bytes=1, market_request_max_bytes=1,
        max_run_cost_usd=0.01, max_run_seconds=1,
        llm_request_timeout_seconds=0.001, **kwargs)


def context(adapter):
    return RunContext('case', 'run', 'snapshot', None, RunMode.EVIDENCE_ONLY,
        model=adapter, budget=RunBudget(max_cost_usd=0.01, spent_cost_usd=100,
            deadline=time.monotonic() - 100))


def test_diagnostics_are_default(monkeypatch):
    monkeypatch.delenv('PROVIDER_INPUT_LIMIT_TEST')
    assert Settings(_env_file=None).provider_input_limit_test is True


@pytest.mark.asyncio
@pytest.mark.parametrize('task', ['science', 'translation', 'market_commercial',
    'market_competitive', 'audit', 'investment_plan', 'chair', 'clinical_population'])
async def test_large_inputs_and_repairs_ignore_old_size_time_and_cost_limits(task):
    calls = []
    class Provider:
        name = 'test'
        async def complete(self, **kwargs):
            calls.append(kwargs)
            return ProviderResponse('invalid' if len(calls) == 1 else '{"answer":"ok"}', 10, 10)
    adapter = StructuredLlm(Provider(), settings())
    ctx = context(adapter)
    text = '\u0421\U0001f9ec unresolved safety. ' * 5000
    payload = {'evidence_items': text, 'prior_analysis': text}
    result = await adapter.generate_structured(task, payload, Answer, ctx)
    assert result.answer == 'ok'
    assert len(calls) == 2
    for call in calls:
        assert json.loads(call['messages'][0]['content']) == payload
        assert call['timeout'] is None
        assert call['max_tokens'] is None
    assert any('actual request sizes' in event['message'] for event in ctx.trace.events)


@pytest.mark.asyncio
async def test_actual_http_request_omits_output_cap_and_keeps_full_input():
    captured = []
    async def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(400, json={'error': {'message': 'conservative input limit'}})
    s = settings(llm_provider='openai', llm_model='test-model', llm_api_key='test-key',
        llm_base_url='https://gateway.example/v1')
    adapter = StructuredLlm(OpenAICompatibleProvider(s, transport=httpx.MockTransport(handle)), s)
    payload = {'evidence_items': 'Exact untrimmed evidence. ' * 5000}
    with pytest.raises(ProviderError) as failure:
        await adapter.generate_structured('science', payload, Answer, context(adapter))
    assert failure.value.code == 'provider_context_limit'
    assert len(captured) == 1
    assert 'max_completion_tokens' not in captured[0]
    assert json.loads(captured[0]['messages'][1]['content']) == payload


def test_market_sends_one_complete_context_and_all_feedback():
    from tests.vic.agents.business.test_market import fixture, run_context
    from tests.vic.agents.business.test_market_clinical_budget import large_clinical
    from vic.agents.business.market import (PASS_MODELS, plan_market_batches,
        prepare_market_inputs, project_clinical_context)
    from vic.llm import structured_request
    adapter = StructuredLlm(type('Provider', (), {'name': 'test'})(), settings())
    ctx = run_context(adapter)
    ctx.feedback['market'] = [{'reason': 'Unresolved safety. ' * 5000}]
    case, pack, _ = fixture()
    pack.evidence[0].excerpt = 'Evidence. ' * 5000
    clinical = large_clinical()
    for task in PASS_MODELS:
        batches = plan_market_batches(prepare_market_inputs(case, pack), clinical, task, ctx)
        assert len(batches) == 1
        batch = batches[0]
        assert batch['clinical_input'] == project_clinical_context(clinical, task)
        assert batch['evidence'][0]['excerpt'] == pack.evidence[0].excerpt
        assert batch['coverage']['partial_batch'] is False
        _, _, messages = structured_request(task, batch, PASS_MODELS[task], ctx)
        assert ctx.feedback['market'][0]['reason'] in messages[-1]['content']


def test_retrieved_records_are_not_sampled_or_clipped():
    from vic.evidence.retrieval import _bounded_external
    from vic.evidence.importer import parse_text
    docs = [parse_text(f'Source {i}', f'Source {i}: ' + 'Untrimmed evidence. ' * 1000) for i in range(5)]
    assert _bounded_external([docs[:3], docs[3:]], settings()) == docs


def test_pipeline_has_no_run_deadline_even_with_legacy_limit_configured(tmp_path):
    from tests.test_pipeline import Env
    env = Env(tmp_path, provider_input_limit_test=True, max_run_seconds=1, max_run_cost_usd=0.01)
    run = env.run()
    assert run.status.value == 'completed'
    trace = env.repo.get_trace(run.id)
    assert trace['config']['provider_input_limit_test'] is True
