import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from vic import synthetic
from vic.contracts import CaseInput, EvidenceCreate, Run, RunStage, RunStatus
from vic.storage import ReportExistsError, SnapshotExistsError, SqliteRepository, new_id

CASE = CaseInput(indication="X", mechanism="Y", scope="approach")


@pytest.fixture()
def repo(tmp_path):
    r = SqliteRepository(str(tmp_path / "t.sqlite3"))
    r.startup()
    return r


def _factory(case_id):
    tpl1, tpl2 = synthetic.build_report(1), synthetic.build_report(2)

    def factory(version):
        return tpl1.model_copy(update={"id": new_id("rep"), "case_id": case_id, "version": version,
                                       "revision": tpl2.revision if version > 1 else None})
    return factory


def test_versions_are_allocated_atomically(repo):
    case_id = repo.create_case(CASE)
    with ThreadPoolExecutor(8) as pool:
        versions = list(pool.map(lambda _: repo.save_next_report(case_id, _factory(case_id)).version,
                                 range(8)))
    assert sorted(versions) == list(range(1, 9))
    assert [r.version for r in repo.list_reports(case_id)] == list(range(1, 9))


def test_reports_are_immutable(repo):
    case_id = repo.create_case(CASE)
    report = repo.save_next_report(case_id, _factory(case_id))
    conn = sqlite3.connect(repo.path)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE reports SET data='x' WHERE id=?", (report.id,))
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM reports WHERE id=?", (report.id,))
    finally:
        conn.close()
    with pytest.raises(ReportExistsError):
        repo.save_report(report)
    assert repo.get_report(case_id, 1) == report


def test_data_survives_a_restart(tmp_path):
    path = str(tmp_path / "p.sqlite3")
    first = SqliteRepository(path)
    case_id = first.create_case(CASE)
    report = first.save_next_report(case_id, _factory(case_id))
    second = SqliteRepository(path)
    assert second.get_case(case_id) == CASE
    assert second.get_report(case_id, 1) == report
    assert second.get_latest_report(case_id) == report


def test_interrupted_runs_become_failed_after_restart(tmp_path):
    path = str(tmp_path / "r.sqlite3")
    first = SqliteRepository(path)
    case_id = first.create_case(CASE)
    first.create_run(Run(id="run-x", case_id=case_id, status=RunStatus.RUNNING,
                         stage=RunStage.ANALYZE, trace_id="trace-x"))
    restarted = SqliteRepository(path)
    assert restarted.startup() == 1
    run = restarted.get_run("run-x")
    assert run.status == RunStatus.FAILED and run.stage == RunStage.ANALYZE
    assert run.error.code == "run_interrupted" and run.error.retryable
    # the fixture run must keep its "running" status for the UI developers
    assert restarted.get_run("run-synthetic-running").status == RunStatus.RUNNING
    assert restarted.startup() == 0


def test_seed_is_idempotent(repo):
    assert repo.get_report("case-synthetic-01", 1) is not None
    assert repo.get_report("case-synthetic-01", 2) is not None
    repo.startup()
    assert len(repo.list_reports("case-synthetic-01")) == 2


def test_snapshot_roundtrip_and_immutability(repo):
    case_id = repo.create_case(CASE)
    pack = synthetic.build_pack_v1()
    repo.save_snapshot(case_id, pack)
    assert repo.get_snapshot(pack.snapshot_id) == pack
    with pytest.raises(SnapshotExistsError):
        repo.save_snapshot(case_id, pack)


def test_user_evidence_is_stored(repo):
    case_id = repo.create_case(CASE)
    created = repo.add_evidence(case_id, EvidenceCreate(title="Нотатка", text="Синтетичний текст"))
    sources, evidence = repo.list_user_evidence(case_id)
    assert [s.id for s in sources] == [created.source_id]
    assert [e.id for e in evidence] == created.evidence_ids
    assert sources[0].content_hash.startswith("sha256:")


def test_active_run_count_ignores_fixtures(repo):
    case_id = repo.create_case(CASE)
    assert repo.count_active_runs() == 0
    repo.create_run(Run(id="run-a", case_id=case_id, status=RunStatus.QUEUED, trace_id="trace-a"))
    assert repo.count_active_runs() == 1