"""HTTP flow of the background run (synthetic development mode)."""
import time

import pytest

from tests.conftest import new_client

CASE = {"indication": "Синтетичне X", "mechanism": "Інгібування Y", "scope": "program",
        "program_data": "Синтетична програма: пероральна мала молекула, дані обмежені, без клінічних даних."}


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch):
    monkeypatch.setenv("RUN_BACKEND", "pipeline")
    monkeypatch.setenv("DEV_STUBS", "true")
    monkeypatch.setenv("STUB_DELAY_SECONDS", "0")


def _wait(client, run_id, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        run = client.get(f"/runs/{run_id}").json()
        if run["status"] in ("completed", "failed"):
            return run
        time.sleep(0.05)
    raise AssertionError("the run did not finish")


def _case(client):
    return client.post("/cases", json=CASE).json()["case_id"]


def test_run_returns_202_then_completes_with_a_saved_report(client):
    cid = _case(client)
    r = client.post(f"/cases/{cid}/runs", json={"mode": "live"})
    assert r.status_code == 202 and "X-VIC-Mock" not in r.headers
    run = _wait(client, r.json()["run_id"])
    assert run["status"] == "completed" and run["report_version"] == 1 and run["trace_id"]
    report = client.get(f"/cases/{cid}/reports/1").json()
    assert len(report["sections"]) == 11 and report["synthetic"] is True
    assert run["cost_usd"] is None and set(run["latency_ms"]) >= {"analyze", "total"}


def test_second_run_needs_a_parent_and_creates_v2(client):
    cid = _case(client)
    _wait(client, client.post(f"/cases/{cid}/runs", json={"mode": "live"}).json()["run_id"])
    r = client.post(f"/cases/{cid}/runs", json={"mode": "live"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "parent_report_required"
    v1 = client.get(f"/cases/{cid}/reports/1").json()
    client.post(f"/cases/{cid}/evidence", json={"title": "Нотатка", "text": "Синтетичний результат", "synthetic": True})
    r2 = client.post(f"/cases/{cid}/runs", json={"mode": "live", "parent_report_id": v1["id"]})
    run2 = _wait(client, r2.json()["run_id"])
    assert run2["status"] == "completed" and run2["report_version"] == 2
    v2 = client.get(f"/cases/{cid}/reports/2").json()
    assert v2["revision"]["parent_report_id"] == v1["id"] and v2["revision"]["new_evidence_ids"]
    assert client.get(f"/cases/{cid}/reports/1").json() == v1


def test_parent_of_another_case_is_409(client):
    a, b = _case(client), _case(client)
    _wait(client, client.post(f"/cases/{a}/runs", json={"mode": "live"}).json()["run_id"])
    rep = client.get(f"/cases/{a}/reports/1").json()
    r = client.post(f"/cases/{b}/runs", json={"mode": "live", "parent_report_id": rep["id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "incompatible_parent_report"


def test_one_active_run_per_case_and_a_global_limit(monkeypatch):
    monkeypatch.setenv("STUB_DELAY_SECONDS", "1")
    monkeypatch.setenv("MAX_CONCURRENT_RUNS", "1")
    with new_client() as c:
        a, b = _case(c), _case(c)
        first = c.post(f"/cases/{a}/runs", json={"mode": "live"})
        assert first.status_code == 202
        same = c.post(f"/cases/{a}/runs", json={"mode": "live"})
        assert same.status_code == 409 and same.json()["error"]["code"] == "run_in_progress"
        other = c.post(f"/cases/{b}/runs", json={"mode": "live"})
        assert other.status_code == 429 and other.json()["error"]["retryable"] is True
        assert c.get(f"/runs/{first.json()['run_id']}").json()["status"] in ("queued", "running")