import dataclasses

import pytest

from tests.test_pipeline import Env
from vic.stubs import make_stub_modules


@pytest.mark.parametrize('name', ['analyze_science', 'analyze_translation', 'analyze_clinical',
    'analyze_market', 'analyze_ip_licensing', 'analyze_partnerships', 'analyze_investment',
    'analyze_investment_threshold', 'analyze_failure_miner'])
def test_validation_failure_is_visible_and_chair_still_runs(tmp_path, name):
    async def rejected(*args, **kwargs):
        raise ValueError('Plan finding requires value and claims')
    modules = dataclasses.replace(make_stub_modules(), **{name: rejected})
    env = Env(tmp_path, modules, continue_on_node_validation_error=True)
    run = env.run()
    assert run.status.value == 'completed', run.error
    nodes = {n.role_id.value: n for n in env.repo.get_nodes(run.id)}
    role = name.removeprefix('analyze_')
    assert nodes[role].result.position == 'insufficient_data'
    assert nodes[role].result.claims == []
    assert nodes[role].result.section_content[0].structured_data['node_recovery']['status'] == 'analysis_unavailable'
    assert nodes['chair'].status == 'completed'
    report = env.repo.get_report(env.case_id, 1)
    assert report.recommendation.value != 'Invest'


def test_provider_authentication_error_is_not_hidden(tmp_path):
    from vic.failures import ProviderAuthError
    async def rejected(*args, **kwargs):
        raise ProviderAuthError('Provider rejected key')
    env = Env(tmp_path, dataclasses.replace(make_stub_modules(), analyze_investment=rejected),
        continue_on_node_validation_error=True)
    run = env.run()
    assert run.status.value == 'failed'
    assert run.error.code == 'provider_auth_error'


def test_missing_specialist_blocks_unconditional_invest_recommendation(tmp_path):
    from vic.contracts import Recommendation
    base = make_stub_modules()
    async def rejected(*args, **kwargs):
        raise ValueError('Invalid output')
    async def optimistic(results, audit, ctx):
        decision = await base.synthesize_committee(results, audit, ctx)
        return decision.model_copy(update={'recommendation': Recommendation.INVEST})
    modules = dataclasses.replace(base, analyze_investment=rejected,
        analyze_investment_threshold=rejected, analyze_failure_miner=rejected,
        synthesize_committee=optimistic)
    env = Env(tmp_path, modules, continue_on_node_validation_error=True)
    run = env.run()
    assert run.status.value == 'completed', run.error
    report = env.repo.get_report(env.case_id, 1)
    assert report.recommendation == Recommendation.CONDITIONAL


def test_shared_recovery_is_enabled_by_default(monkeypatch):
    from vic.config import Settings
    monkeypatch.delenv('CONTINUE_ON_NODE_VALIDATION_ERROR')
    assert Settings(_env_file=None).continue_on_node_validation_error
