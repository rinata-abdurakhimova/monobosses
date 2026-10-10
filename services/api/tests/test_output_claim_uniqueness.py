"""Duplicate output identities are repaired before final report assembly."""
import json

import pytest
from pydantic import BaseModel, ValidationError

from tests.test_clinical_subtasks import Provider
from tests.vic.agents.science.test_clinical import (
    _case,
    _pack,
    _scientific_result,
    _translation_result,
)
from vic.agents.science.clinical import _pass_model, analyze_clinical
from vic.clinical_requests import TASKS
from vic.config import Settings
from vic.contracts import RunContext, RunMode
from vic.llm import ProviderResponse, StructuredLlm, validate_output_claim_identities


@pytest.mark.asyncio
async def test_duplicate_clinical_subtask_is_repaired_before_final_assembly():
    class DuplicateProvider(Provider):
        async def complete(self, **kwargs):
            reply = await super().complete(**kwargs)
            if len(self.calls) == 1:
                data = json.loads(reply.text)
                data['claims'].append({**data['claims'][0], 'text': 'Opposing interpretation requiring reconciliation.'})
                return ProviderResponse(json.dumps(data), 10, 10)
            return reply

    provider = DuplicateProvider()
    adapter = StructuredLlm(provider, Settings(_env_file=None))
    ctx = RunContext('case', 'run', 'snap-test', None, RunMode.EVIDENCE_ONLY, model=adapter)
    result = await analyze_clinical(_case(), _pack(), _scientific_result(), _translation_result(), ctx)
    assert len(provider.calls) == 5
    assert 'duplicate key' in provider.calls[1][2][-1]['content']
    assert len({c.id for c in result.claims}) == len(result.claims)


@pytest.mark.parametrize('task', list(TASKS))
def test_every_clinical_pass_has_schema_uniqueness_validator(task):
    from tests.test_clinical_subtasks import _clinical_analysis
    from vic.agents.science.clinical import _COMMON_FIELDS

    fields, keys, _ = TASKS[task]
    data = _clinical_analysis().model_dump(mode='json')
    data = {k: v for k, v in data.items() if k in fields | _COMMON_FIELDS}
    data['claims'] = [{**data['claims'][0], 'key': min(keys)}]
    data['claims'].append({**data['claims'][0], 'text': 'Another interpretation.'})
    with pytest.raises(ValidationError, match='Duplicate clinical claim keys'):
        _pass_model(task, fields, keys).model_validate(data)


@pytest.mark.asyncio
@pytest.mark.parametrize('prompt', ['science', 'translation', 'market', 'ip_licensing',
    'partnerships', 'investment', 'investment_threshold', 'failure_miner', 'chair', 'audit'])
async def test_all_roles_repair_duplicate_claim_or_verdict_identities(prompt):
    class Result(BaseModel):
        claims: list[dict] = []
        verdicts: list[dict] = []

    collection, key = ('verdicts', 'claim_id') if prompt == 'audit' else ('claims', 'id')
    identity = f'{prompt}.test'
    invalid = {collection: [{key: identity, 'text': 'First'}, {key: identity, 'text': 'Second'}]}
    corrected = {collection: [{key: identity, 'text': 'Opposing interpretations remain unresolved.'}]}

    class ModelProvider:
        name = 'test'

        def __init__(self):
            self.calls = 0

        async def complete(self, *, system, messages, **kwargs):
            self.calls += 1
            if self.calls == 2:
                assert identity in messages[-1]['content']
                assert all(m['role'] != 'assistant' for m in messages)
            return ProviderResponse(json.dumps(invalid if self.calls == 1 else corrected), 10, 10)

    provider = ModelProvider()
    adapter = StructuredLlm(provider, Settings(_env_file=None))
    ctx = RunContext('case', 'run', 'snap', None, RunMode.EVIDENCE_ONLY, model=adapter)
    result = await adapter._generate_direct(prompt, {}, Result, ctx)
    assert len(getattr(result, collection)) == 1
    assert provider.calls == 2


def test_repeated_citations_are_allowed():
    validate_output_claim_identities({'claims': [{'id': 'a', 'evidence_ids': ['e1']},
        {'id': 'b', 'evidence_ids': ['e1']}]})
