import asyncio
import dataclasses

import pytest

from tests.test_pipeline import Env
from vic.contracts import RunStatus
from vic.errors import ApiError
from vic.failures import RunFailure
from vic.pipeline import Pipeline
from vic.runner import RunManager
from vic.stubs import make_stub_modules


def failed_ip(tmp_path):
    base = make_stub_modules()
    async def fail(*args, **kwargs):
        raise RunFailure('IP failed')
    env = Env(tmp_path, dataclasses.replace(base, analyze_ip_licensing=fail))
    run = env.run()
    assert run.status == RunStatus.FAILED
    return env, run, base


def test_resume_reuses_snapshot_and_completed_nodes_then_finishes(tmp_path):
    env, run, base = failed_ip(tmp_path)
    before = env.repo.get_nodes(run.id)
    snapshot = env.repo.get_trace(run.id)['snapshot_id']
    async def must_not_run(*args, **kwargs):
        raise AssertionError('Completed upstream work must not repeat')
    modules = dataclasses.replace(base, build_evidence_pack=must_not_run,
        analyze_science=must_not_run, analyze_translation=must_not_run,
        analyze_clinical=must_not_run, analyze_market=must_not_run)
    pipeline = Pipeline(env.repo, env.settings, lambda: modules, lambda: None)
    queued = run.model_copy(update={'status': RunStatus.QUEUED, 'error': None})
    env.repo.update_run(queued)
    result = asyncio.run(pipeline.execute(queued, resume=True))
    assert result.status == RunStatus.COMPLETED, result.error
    assert result.id == run.id
    assert env.repo.get_trace(run.id)['snapshot_id'] == snapshot
    after = {n.role_id.value: n for n in env.repo.get_nodes(run.id)}
    for node in before:
        if node.role_id.value in ('science', 'translation', 'clinical', 'market'):
            assert after[node.role_id.value].result == node.result
            assert after[node.role_id.value].attempt == node.attempt
    assert after['ip_licensing'].attempt == 2
    assert after['partnerships'].status == 'completed'
    assert any('Resume reused' in e['message'] for e in env.repo.get_trace(run.id)['events'])


@pytest.mark.asyncio
async def test_resume_manager_rejects_duplicate_and_preserves_run_id(tmp_path, monkeypatch):
    from vic import runner
    # Construct the failed run outside this running event loop.
    env, run, base = await asyncio.to_thread(failed_ip, tmp_path)
    monkeypatch.setattr(runner, 'get_repository', lambda: env.repo)
    manager = RunManager(env.settings)
    started = asyncio.Event()
    release = asyncio.Event()
    async def execute(queued, *, resume=False):
        assert queued.id == run.id and resume
        started.set()
        await release.wait()
    monkeypatch.setattr(manager, '_execute', execute)
    queued = await manager.resume(run.id)
    assert queued.id == run.id and queued.status == RunStatus.QUEUED
    await started.wait()
    with pytest.raises(ApiError) as error:
        await manager.resume(run.id)
    assert error.value.status == 409
    release.set()
    await manager.shutdown()


@pytest.mark.asyncio
async def test_resume_without_snapshot_is_rejected_without_changing_failed_run(tmp_path, monkeypatch):
    from vic import runner
    env, run, _ = await asyncio.to_thread(failed_ip, tmp_path)
    env.repo.save_trace(run.id, {'snapshot_id': 'snapshot-missing'})
    monkeypatch.setattr(runner, 'get_repository', lambda: env.repo)
    manager = RunManager(env.settings)
    with pytest.raises(ApiError) as error:
        await manager.resume(run.id)
    assert error.value.status == 409
    assert env.repo.get_run(run.id).status == RunStatus.FAILED
    assert not manager._tasks
