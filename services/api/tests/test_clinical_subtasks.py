import json

import pytest

from tests.vic.agents.science.test_clinical import (
    _case,
    _clinical_analysis,
    _pack,
    _scientific_result,
    _translation_result,
)
from vic.agents.science.clinical import _COMMON_FIELDS, analyze_clinical
from vic.clinical_requests import TASKS, scoped_records
from vic.config import Settings
from vic.contracts import Importance, RunContext, RunMode
from vic.failures import ProviderError
from vic.llm import ProviderResponse, StructuredLlm, request_sizes


class Provider:
    name = 'test'

    def __init__(self, invalid_once=False):
        self.calls = []
        self.invalid_once = invalid_once

    async def complete(self, *, system, messages, model, max_tokens, timeout):
        data = json.loads(messages[0]['content'])
        self.calls.append((data, system, messages, max_tokens))
        if self.invalid_once:
            self.invalid_once = False
            return ProviderResponse('bad output ' * 1000, 10, 10)
        if 'exact_input_segment' in data or 'adjacent_reviews' in data:
            return ProviderResponse(json.dumps({'observations': 'Limited animal observations, not demonstrated human benefit.',
                'gaps_and_conflicts': 'Negative safety finding remains unresolved; human exposure unknown.'}), 10, 10)
        task = next(task for task, (_, keys, _) in TASKS.items() if sorted(keys) == data['claim_keys'])
        fields, keys, _ = TASKS[task]
        raw = _clinical_analysis().model_dump(mode='json')
        raw = {key: value for key, value in raw.items() if key in fields | _COMMON_FIELDS}
        raw['claims'] = [c for c in raw['claims'] if c['key'] in keys]
        return ProviderResponse(json.dumps(raw), 10, 10)


@pytest.mark.asyncio
async def test_large_inputs_and_repairs_reach_provider_without_application_budget():
    provider = Provider(invalid_once=True)
    adapter = StructuredLlm(provider, Settings(_env_file=None,
        enforce_node_request_budget=True, node_request_max_bytes=1000))
    case, pack, science, translation = _case(), _pack(), _scientific_result(), _translation_result()
    pack.evidence[0].excerpt = '\u0421\U0001f9ec safety gap. ' * 2000
    science.summary = 'Unknown human translation. ' * 800
    case.mechanism = 'Large mechanism ' * 1000
    original = science.model_dump_json()
    ctx = RunContext('case', 'run', pack.snapshot_id, None, RunMode.EVIDENCE_ONLY, model=adapter)
    ctx.feedback['clinical'] = [{'reason': 'Negative safety result must survive.'}]
    result = await analyze_clinical(case, pack, science, translation, ctx)
    assert science.model_dump_json() == original
    assert result.role_id == 'clinical'
    assert len(provider.calls) == 5
    for task in TASKS:
        calls = [data for data, _, _, _ in provider.calls
                 if data['claim_keys'] == sorted(TASKS[task][1])]
        records = calls[0]['scoped_records']
        expected = scoped_records(case, pack, science, translation, task)
        assert records[:len(expected)] == expected
        if task == 'clinical_planning':
            assert len([r for r in records if r['kind'] == 'clinical_subtask_result']) == 3
    for _, system, messages, max_tokens in provider.calls:
        assert request_sizes(system, messages)['request_bytes'] > 10000
        assert max_tokens == 4096
        assert 'Negative safety result' in messages[1]['content']
        assert all(message['role'] != 'assistant' for message in messages)
    assert 'bad output' not in json.dumps(provider.calls[1][2])


@pytest.mark.asyncio
async def test_provider_context_limit_propagates_without_shrinking_input():
    class RejectingProvider(Provider):
        async def complete(self, **kwargs):
            self.calls.append(kwargs)
            raise ProviderError('Provider input too large', code='provider_context_limit', retryable=False)
    provider = RejectingProvider()
    adapter = StructuredLlm(provider, Settings(_env_file=None))
    ctx = RunContext('case', 'run', 'snap', None, RunMode.EVIDENCE_ONLY, model=adapter)
    with pytest.raises(ProviderError) as failure:
        await analyze_clinical(_case(), _pack(), _scientific_result(), _translation_result(), ctx)
    assert failure.value.code == 'provider_context_limit'
    assert len(provider.calls) == 1


def test_noncritical_prior_claims_are_scoped_but_critical_risks_and_gaps_are_shared():
    science, translation = _scientific_result(), _translation_result()
    claim = translation.claims[0].model_copy(update={'id': 'translation.human_exposure', 'importance': Importance.MAJOR})
    translation.claims = [claim]
    population = scoped_records(_case(), _pack(), science, translation, 'clinical_population')
    safety = scoped_records(_case(), _pack(), science, translation, 'clinical_safety')
    assert not any(row.get('id') == claim.id for row in population)
    assert any(row.get('id') == claim.id for row in safety)
    assert all(any(row.get('id') == risk.id for row in population) for risk in translation.risks)
