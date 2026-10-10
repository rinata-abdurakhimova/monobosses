import json
from itertools import pairwise

import pytest

from tests.vic.agents.science.test_clinical import (
    _case,
    _clinical_analysis,
    _pack,
    _scientific_result,
    _translation_result,
)
from vic.agents.science.clinical import _COMMON_FIELDS, analyze_clinical
from vic.clinical_requests import TASKS, CombinedContextReview, ContextReview, scoped_records
from vic.config import Settings
from vic.contracts import Importance, RunContext, RunMode
from vic.failures import RunFailure
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
async def test_large_utf8_context_is_reviewed_completely_with_bounded_repairs_and_original_results_unchanged():
    provider = Provider(invalid_once=True)
    adapter = StructuredLlm(provider, Settings(_env_file=None))
    pack, science, translation = _pack(), _scientific_result(), _translation_result()
    pack.evidence[0].excerpt = 'Суперечливі результати 🧬 safety gap. ' * 800
    science.summary = 'Unknown human translation. ' * 800
    original = science.model_dump_json()
    ctx = RunContext('case', 'run', pack.snapshot_id, None, RunMode.EVIDENCE_ONLY, model=adapter)
    ctx.feedback['clinical'] = [{'reason': 'Negative safety result must survive.'}]
    result = await analyze_clinical(_case(), pack, science, translation, ctx)
    assert science.model_dump_json() == original
    assert result.role_id == 'clinical'
    assert any('AI reviews' in text for text in result.section_content[0].limitations)
    for task in TASKS:
        segments = [data for data, _, _, _ in provider.calls if 'exact_input_segment' in data
                    and data['claim_keys'] == sorted(TASKS[task][1])]
        # The first malformed-response repair repeats its exact input, not its invalid answer.
        unique = {data['segment_start']: data for data in segments}
        assert unique
        sequence = [unique[start] for start in sorted(unique)]
        assert sequence[0]['segment_start'] == 0
        assert all(left['segment_end'] == right['segment_start'] for left, right in pairwise(sequence))
        text = ''.join(data['exact_input_segment'] for data in sequence)
        if task != 'clinical_planning':
            assert json.loads(text) == scoped_records(_case(), pack, science, translation, task)
        assert pack.evidence[0].excerpt in text
        assert science.summary in text
    for _, system, messages, max_tokens in provider.calls:
        assert request_sizes(system, messages)['request_bytes'] <= 10000
        assert max_tokens == 4096
        assert 'Negative safety result' in messages[1]['content']
        assert all(message['role'] != 'assistant' for message in messages)
    assert 'bad output' not in json.dumps(provider.calls[1][2])


@pytest.mark.asyncio
async def test_indivisible_case_metadata_fails_before_any_paid_call():
    provider = Provider()
    adapter = StructuredLlm(provider, Settings(_env_file=None, clinical_request_target_bytes=2000))
    case = _case()
    case.mechanism = 'Unbounded mechanism ' * 1000
    ctx = RunContext('case', 'run', 'snap', None, RunMode.EVIDENCE_ONLY, model=adapter)
    with pytest.raises(RunFailure, match='metadata'):
        await analyze_clinical(case, _pack(), _scientific_result(), _translation_result(), ctx)
    assert not provider.calls


def test_noncritical_prior_claims_are_scoped_but_critical_risks_and_gaps_are_shared():
    science, translation = _scientific_result(), _translation_result()
    claim = translation.claims[0].model_copy(update={'id': 'translation.human_exposure', 'importance': Importance.MAJOR})
    translation.claims = [claim]
    population = scoped_records(_case(), _pack(), science, translation, 'clinical_population')
    safety = scoped_records(_case(), _pack(), science, translation, 'clinical_safety')
    assert not any(row.get('id') == claim.id for row in population)
    assert any(row.get('id') == claim.id for row in safety)
    assert all(any(row.get('id') == risk.id for row in population) for risk in translation.risks)


@pytest.mark.asyncio
@pytest.mark.parametrize("schema, limit", [(ContextReview, 400), (CombinedContextReview, 1000)])
async def test_review_length_repair_names_exact_limit_and_preserves_safety(schema, limit):
    class LongReviewProvider(Provider):
        async def complete(self, *, system, messages, model, max_tokens, timeout):
            self.calls.append((system, messages, max_tokens))
            if len(self.calls) == 1:
                return ProviderResponse(json.dumps({
                    'observations': 'Limited evidence.',
                    'gaps_and_conflicts': 'Unresolved safety. ' * limit}), 10, 10)
            assert 'Shorten' in messages[-1]['content']
            assert f'at most {limit} characters' in messages[-1]['content']
            return ProviderResponse(json.dumps({
                'observations': 'Limited evidence.',
                'gaps_and_conflicts': 'Safety concern unresolved; opposing findings require review.'}), 10, 10)

    provider = LongReviewProvider()
    adapter = StructuredLlm(provider, Settings(_env_file=None))
    ctx = RunContext('case', 'run', 'snap', None, RunMode.EVIDENCE_ONLY, model=adapter)
    result = await adapter._generate_direct('clinical_population', {'exact_input_segment': 'Safety concern.'},
        schema, ctx, compact=True)
    assert 'Safety concern unresolved' in result.gaps_and_conflicts
    assert len(provider.calls) == 2
    for system, messages, max_tokens in provider.calls:
        assert request_sizes(system, messages)['request_bytes'] <= 10000
        assert max_tokens == 4096
        assert all(message['role'] != 'assistant' for message in messages)


def test_combined_review_retains_more_conflicts_than_segment_review():
    text = 'Safety gap and contradictory results. ' * 20
    result = CombinedContextReview(observations='Limited evidence.', gaps_and_conflicts=text)
    assert result.gaps_and_conflicts == text
