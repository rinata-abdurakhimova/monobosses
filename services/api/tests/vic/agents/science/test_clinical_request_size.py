"""Budget regression with full upstream context and contradictory evidence intact."""
import json
from unittest.mock import AsyncMock

import pytest

from tests.vic.agents.science.test_clinical import (
    _case,
    _clinical_analysis,
    _pack,
    _scientific_result,
    _translation_result,
)
from vic.agents.science.clinical import (
    ClinicalPlanAnalysis,
    _build_payload,
    analyze_clinical,
)
from vic.config import Settings
from vic.contracts import RunContext, RunMode
from vic.llm import ProviderResponse, StructuredLlm, request_sizes, structured_request


def test_clinical_request_fits_small_context_without_truncating_input():
    pack = _pack()
    pack.evidence[0].excerpt = (
        "Candidate-specific liver toxicity contradicts safe exposure; "
        "another chemotype has no comparable safety data."
    )
    science, translation = _scientific_result(), _translation_result()
    translation.unknowns.append("No demonstrated safe human exposure or patient benefit.")
    payload = _build_payload(_case(), pack, science, translation)
    ctx = RunContext("case", "run", pack.snapshot_id, None, RunMode.EVIDENCE_ONLY)
    _, system, messages = structured_request("clinical", payload, ClinicalPlanAnalysis, ctx)
    sizes = request_sizes(system, messages, model="gpt-6-luna", max_tokens=4096)
    # An application regression bound, not an asserted provider token limit.
    assert sizes["request_bytes"] < 14000
    assert sizes["prompt_bytes"] < 3500
    assert pack.evidence[0].excerpt in payload["evidence_items"]
    assert pack.evidence[0].id in payload["evidence_items"]
    for prior in (science, translation):
        for claim in prior.claims:
            assert claim.id in payload["prior_analysis"]
            assert claim.text in payload["prior_analysis"]
        for risk in prior.risks:
            assert risk.id in payload["prior_analysis"]
            assert risk.description in payload["prior_analysis"]
        for text in prior.unknowns + prior.change_conditions:
            assert text in payload["prior_analysis"]


@pytest.mark.asyncio
async def test_scoped_clinical_subtasks_preserve_fields_and_share_safety_gaps():
    from vic.agents.science.clinical import _COMMON_FIELDS
    from vic.clinical_requests import TASKS
    raw = _clinical_analysis().model_dump(mode="json")
    outputs = []
    for fields, keys, _ in TASKS.values():
        output = {key: value for key, value in raw.items() if key in fields | _COMMON_FIELDS}
        output['claims'] = [c for c in raw['claims'] if c['key'] in keys]
        outputs.append(ProviderResponse(json.dumps(output), 100, 100))
    provider = type("Provider", (), {"name": "test", "complete": AsyncMock(side_effect=outputs)})()
    adapter = StructuredLlm(provider, Settings(_env_file=None))
    science, translation = _scientific_result(), _translation_result()
    ctx = RunContext("case", "run", "snapshot", None, RunMode.EVIDENCE_ONLY, model=adapter)
    ctx.feedback['clinical'] = [{'reason': 'Carry forward the negative safety result.'}]
    result = await analyze_clinical(_case(), _pack(), science, translation, ctx)
    assert provider.complete.await_count == 4
    assert [u['prompt_id'] for u in ctx.trace.usage] == list(TASKS)
    for call in provider.complete.await_args_list:
        data = json.loads(call.kwargs['messages'][0]['content'])
        assert 'prior_analysis' not in data
        assert translation.unknowns[0] in json.dumps(data)
        assert 'negative safety result' in call.kwargs['messages'][1]['content']
        assert 'scoped_records' in data
    assert {c.id for c in result.claims} == {c['key'] for c in raw['claims']}
    section = result.section_content[0].structured_data
    for key in ('target_population', 'primary_endpoint', 'next_milestone', 'study_sequence', 'regulatory_context'):
        assert section[key] == raw[key]
