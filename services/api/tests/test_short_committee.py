import dataclasses
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_pipeline import CASE, Env
from vic.config import Settings
from vic.contracts import Claim, EvidencePack, RoleResult, RunContext, RunMode
from vic.short_committee import synthesize_short_committee
from vic.stubs import make_stub_modules


@pytest.mark.asyncio
@pytest.mark.parametrize('status,expected', [('supported', 'Invest'), ('unknown', 'Conditional'),
    ('unverified', 'Conditional'), ('contradicted', 'Conditional')])
async def test_positive_decision_depends_on_included_critical_evidence(status, expected):
    claim = Claim(id='investment.funding', text='Funding covers the next milestone.',
        provenance='source', support_status=status, evidence_ids=['funding-evidence'],
        scope='program', importance='critical')
    mock = AsyncMock(return_value={'recommendation': 'Invest',
        'rationale': 'Invest. The supplied findings support the proposed investment.',
        'claim_ids': [claim.id]})
    ctx = RunContext('case', 'run', 'snap', None, RunMode.LIVE,
        model=SimpleNamespace(generate_structured=mock))
    inputs = [RoleResult(role_id='investment', position='positive', summary='Funding assessed.', claims=[claim]),
        RoleResult(role_id='investment_threshold', position='analysis_unavailable', summary='Excluded failure.')]
    pack = EvidencePack(snapshot_id='snap', sources=[], evidence=[], synthetic=False)
    decision, chair = await synthesize_short_committee(CASE, pack, inputs, ctx)
    assert decision.recommendation.value == expected
    assert chair.position == expected
    assert chair.section_content[0].claim_ids == [claim.id]
    assert len(mock.call_args.args[1]['specialists']) == 1


def test_short_pipeline_completes_without_disabled_modules_or_audit(tmp_path):
    base = make_stub_modules()
    async def forbidden(*args, **kwargs):
        raise AssertionError('Disabled module must never run')
    env = Env(tmp_path, dataclasses.replace(base, analyze_investment_threshold=forbidden,
        analyze_failure_miner=forbidden, audit_claims=forbidden, synthesize_committee=forbidden),
        short_committee=True)
    run = env.run()
    assert run.status.value == 'completed', run.error
    report = env.repo.get_report(env.case_id, 1)
    ids = {r.role_id.value for r in report.roles}
    assert ids == {'science', 'translation', 'clinical', 'market', 'ip_licensing', 'partnerships', 'investment', 'chair'}
    assert len(report.sections) == 11
    assert report.recommendation.value == 'Conditional'
    assert len(report.diligence_questions) == 5
    assert len(report.rationale) <= 700


@pytest.mark.asyncio
async def test_short_chair_excludes_disabled_input_even_if_supplied():
    mock = AsyncMock(return_value={'recommendation': 'Do Not Invest',
        'rationale': 'Do not pursue the proposed investment. Available findings show unresolved material barriers.', 'claim_ids': []})
    ctx = RunContext('case', 'run', 'snap', None, RunMode.LIVE, model=SimpleNamespace(generate_structured=mock))
    inputs = [RoleResult(role_id=r, summary='Do not pass this content', position='unknown')
        for r in ['audit', 'failure_miner', 'investment_threshold']]
    pack = EvidencePack(snapshot_id='snap', sources=[], evidence=[], synthetic=False)
    decision, chair = await synthesize_short_committee(CASE, pack, inputs, ctx)
    assert mock.call_args.args[1]['specialists'] == []
    assert decision.recommendation.value == 'Do Not Invest'
    assert chair.summary == decision.rationale


def test_short_mode_is_default(monkeypatch):
    monkeypatch.delenv('SHORT_COMMITTEE')
    assert Settings(_env_file=None).short_committee


def test_short_resume_reuses_seven_nodes_and_skips_old_failed_threshold(tmp_path):
    import asyncio

    from vic.pipeline import Pipeline
    base = make_stub_modules()

    async def threshold_failure(*args, **kwargs):
        from vic.failures import ProviderError
        raise ProviderError('Threshold failed', retryable=False)

    env = Env(tmp_path, dataclasses.replace(base, analyze_investment_threshold=threshold_failure),
        short_committee=False)
    run = env.run()
    assert run.status.value == 'failed'
    pipeline = Pipeline(env.repo, env.settings.model_copy(update={'short_committee': True}),
        lambda: env.modules, lambda: None)
    result = asyncio.run(pipeline.execute(run, resume=True))
    assert result.status.value == 'completed', result.error
    assert env.repo.get_report(env.case_id, 1)
    nodes = {n.role_id.value: n for n in env.repo.get_nodes(run.id)}
    assert nodes['investment'].attempt == 1
    assert nodes['investment_threshold'].attempt == 1
    assert nodes['chair'].status == 'completed'


def test_short_mode_does_not_require_disabled_modules(monkeypatch):
    import vic.modules as module_registry
    from vic.modules import REQUIRED, get_modules
    base = make_stub_modules()
    disabled = {'analyze_investment_threshold', 'analyze_failure_miner', 'audit_claims', 'synthesize_committee'}
    found = {name: [('test', getattr(base, name))] for name in REQUIRED if name not in disabled}
    monkeypatch.setattr(module_registry, 'discover', lambda: found)
    modules = get_modules(Settings(_env_file=None, dev_stubs=False, short_committee=True))
    assert modules.analyze_investment is not None
    assert modules.audit_claims is None
    assert modules.analyze_failure_miner is None
