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


@pytest.mark.parametrize('audit_invalid', [False, True])
def test_audit_blockers_go_to_chair_without_rerunning_specialists(tmp_path, audit_invalid):
    from vic.contracts import AuditFinding, AuditResult
    base = make_stub_modules()
    calls = {'science': 0, 'audit': 0, 'chair': 0}
    async def science(*args):
        calls['science'] += 1
        return await base.analyze_science(*args)
    async def audit(claims, pack, ctx):
        calls['audit'] += 1
        if audit_invalid:
            raise ValueError('Invalid audit output')
        return AuditResult(findings=[AuditFinding(claim_id=c.id, verdict=c.support_status,
            reason='Unresolved evidence', evidence_ids=c.evidence_ids,
            blocking=c.id == 'science.target_validation') for c in claims])
    async def chair(results, audit, ctx):
        calls['chair'] += 1
        science_result = next(r for r in results if r.role_id.value == 'science')
        claim = next(c for c in science_result.claims if c.id == 'science.target_validation')
        assert claim.support_status.value == 'unverified'
        return await base.synthesize_committee(results, audit, ctx)
    env = Env(tmp_path, dataclasses.replace(base, analyze_science=science,
        audit_claims=audit, synthesize_committee=chair), continue_on_node_validation_error=True)
    run = env.run()
    assert run.status.value == 'completed', run.error
    assert calls == {'science': 1, 'audit': 1, 'chair': 1}
    nodes = env.repo.get_nodes(run.id)
    assert all(n.status != 'stale' for n in nodes)
    assert next(n for n in nodes if n.role_id.value == 'chair').status == 'completed'


def test_program_claim_in_approach_assessment_does_not_block_chair(tmp_path):
    from tests.test_pipeline import CASE
    from vic.contracts import Scope
    base = make_stub_modules()
    seen = []
    async def wrong_scope(case, pack, ctx):
        result = await base.analyze_science(case, pack, ctx)
        claims = [c.model_copy(update={'scope': 'program'}) for c in result.claims]
        assert claims
        return result.model_copy(update={'claims': claims})
    async def chair(results, audit, ctx):
        seen.extend(results)
        assert all(c.scope.value == 'approach' for r in results for c in r.claims)
        return await base.synthesize_committee(results, audit, ctx)
    env = Env(tmp_path, dataclasses.replace(base, analyze_science=wrong_scope,
        synthesize_committee=chair), continue_on_node_validation_error=True)
    case_id = env.repo.create_case(CASE.model_copy(update={'scope': Scope.APPROACH}))
    run = env.run(case_id=case_id)
    assert run.status.value == 'completed', run.error
    science = next(r for r in seen if r.role_id.value == 'science')
    assert science.claims == []
    assert science.section_content[0].structured_data['node_recovery']['error_code'] == 'scope_mismatch'
    assert next(n for n in env.repo.get_nodes(run.id) if n.role_id.value == 'chair').status == 'completed'


def test_scope_mismatch_regenerates_translation_before_discarding_output(tmp_path):
    from tests.test_pipeline import CASE
    from vic.contracts import Scope
    base = make_stub_modules()
    calls = []

    async def translation(case, pack, ctx):
        result = await base.analyze_translation(case, pack, ctx)
        calls.append(list(ctx.feedback.get('translation', [])))
        if len(calls) == 1:
            return result.model_copy(update={'claims': [
                c.model_copy(update={'scope': Scope.PROGRAM}) for c in result.claims]})
        assert calls[-1]
        assert 'approach' in calls[-1][0].reason
        return result.model_copy(update={'claims': [
            c.model_copy(update={'scope': Scope.APPROACH}) for c in result.claims]})

    env = Env(tmp_path, dataclasses.replace(base, analyze_translation=translation),
        continue_on_node_validation_error=True)
    case_id = env.repo.create_case(CASE.model_copy(update={'scope': Scope.APPROACH}))
    run = env.run(case_id=case_id)
    assert run.status.value == 'completed', run.error
    node = next(n for n in env.repo.get_nodes(run.id) if n.role_id.value == 'translation')
    assert len(calls) == 2
    assert node.result.claims
    assert all(c.scope == Scope.APPROACH for c in node.result.claims)
    assert not any('node_recovery' in (s.structured_data or {}) for s in node.result.section_content)
    assert not any('translation analysis unavailable' in w for w in run.warnings)


def test_recovery_exposes_validation_reason_without_secrets(tmp_path):
    async def rejected(*args, **kwargs):
        raise ValueError('Invalid finding: test-secret-value')
    env = Env(tmp_path, dataclasses.replace(make_stub_modules(), analyze_investment=rejected),
        continue_on_node_validation_error=True, api_shared_secret='test-secret-value')
    run = env.run()
    assert run.status.value == 'completed', run.error
    node = next(n for n in env.repo.get_nodes(run.id) if n.role_id.value == 'investment')
    recovery = node.result.section_content[0].structured_data['node_recovery']
    assert 'Invalid finding' in recovery['validation_reason']
    assert 'test-secret-value' not in node.result.model_dump_json()


def test_domain_validation_gets_one_targeted_regeneration(tmp_path):
    base = make_stub_modules()
    calls = []

    async def investment(*args, **kwargs):
        ctx = args[-1]
        calls.append(list(ctx.feedback.get('investment', [])))
        if len(calls) == 1:
            raise ValueError('Plan finding requires value and claims')
        assert 'Plan finding requires value and claims' in calls[-1][0].reason
        return await base.analyze_investment(*args, **kwargs)

    env = Env(tmp_path, dataclasses.replace(base, analyze_investment=investment),
        continue_on_node_validation_error=True)
    run = env.run()
    assert run.status.value == 'completed', run.error
    node = next(n for n in env.repo.get_nodes(run.id) if n.role_id.value == 'investment')
    assert len(calls) == 2
    assert node.result.claims
    assert not any('node_recovery' in (s.structured_data or {}) for s in node.result.section_content)


@pytest.mark.parametrize('role', ['clinical', 'market', 'partnerships'])
def test_evidence_backed_insufficient_position_becomes_partial_assessment(role):
    from vic.contracts import Claim, RoleResult, SectionContent
    from vic.pipeline import Pipeline
    claim = Claim(id=role + '.finding', text='Evidence-backed finding', provenance='ai',
        support_status='supported', evidence_ids=['ev-1'], scope='approach', importance='major')
    result = RoleResult(role_id=role, position='insufficient_data', summary='Specific preliminary conclusion',
        claims=[claim], unknowns=['Licensing terms are unknown'],
        section_content=[SectionContent(key='critical_unknowns', summary='Specific conclusion',
            claim_ids=[claim.id])])
    output = Pipeline._partial_assessment(None, result)
    assert output.position == 'partial_assessment'
    assert output.summary == result.summary
    assert output.claims == result.claims
    assert output.unknowns == result.unknowns
    assert output.section_content[0].structured_data['assessment_coverage']['original_position'] == 'insufficient_data'
    unknown = claim.model_copy(update={'support_status': 'unknown', 'evidence_ids': []})
    assert Pipeline._partial_assessment(None, result.model_copy(update={'claims': [unknown]})).position == 'insufficient_data'
    rejected = result.model_copy(update={'section_content': [result.section_content[0].model_copy(
        update={'structured_data': {'node_recovery': {'status': 'analysis_unavailable'}}})]})
    assert Pipeline._partial_assessment(None, rejected).position == 'insufficient_data'
