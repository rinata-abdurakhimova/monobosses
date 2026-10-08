import pytest
from fastapi.testclient import TestClient

from vic.config import get_settings
from vic.contracts import Report
from vic.main import create_app
from vic.storage import get_repository


def new_client() -> TestClient:
    get_settings.cache_clear()
    get_repository.cache_clear()
    return TestClient(create_app())

VALID = {"indication": "Синтетичне захворювання X", "mechanism": "Інгібування мішені Y",
         "scope": "approach"}
PDF = b"%PDF-1.4\n%synthetic\n"


def _assert_envelope(body, code):
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "retryable"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["retryable"], bool)


def _case(client):
    r = client.post("/cases", json=VALID)
    assert r.status_code == 201
    return r.json()["case_id"]


# ---------------------------------------------------------------- cases / validation
def test_create_case(client):
    assert _case(client)


@pytest.mark.parametrize("body", [
    {},
    {"indication": "   ", "mechanism": "Y", "scope": "approach"},
    {"indication": "X", "mechanism": "Y", "scope": "program"},
])
def test_invalid_case_returns_422_envelope(client, body):
    r = client.post("/cases", json=body)
    assert r.status_code == 422
    _assert_envelope(r.json(), "validation_error")


def test_unknown_route_404_envelope(client):
    r = client.get("/nope")
    assert r.status_code == 404
    _assert_envelope(r.json(), "not_found")


# ---------------------------------------------------------------- 404s
def test_unknown_case_run_404(client):
    r = client.post("/cases/nope/runs", json={"mode": "live"})
    assert r.status_code == 404
    _assert_envelope(r.json(), "not_found")


def test_unknown_run_and_report_404(client):
    assert client.get("/runs/nope").status_code == 404
    assert client.get("/cases/nope/reports/1").status_code == 404
    cid = _case(client)
    r = client.get(f"/cases/{cid}/reports/1")
    assert r.status_code == 404
    _assert_envelope(r.json(), "not_found")


# ---------------------------------------------------------------- mock runs
def test_mock_run_v1_then_v2(client):
    cid = _case(client)
    r = client.post(f"/cases/{cid}/runs", json={"mode": "evidence_only"})
    assert r.status_code == 202
    assert r.headers["X-VIC-Mock"] == "true"
    run = client.get(f"/runs/{r.json()['run_id']}").json()
    assert run["status"] == "completed" and run["report_version"] == 1
    assert any("MOCK" in w for w in run["warnings"])
    assert run["cost_usd"] is None

    rep1 = client.get(f"/cases/{cid}/reports/1")
    assert rep1.status_code == 200
    report1 = Report.model_validate(rep1.json())
    assert report1.case_id == cid and len(report1.sections) == 11 and report1.synthetic
    assert report1.recommendation.value == "Conditional"

    r2 = client.post(f"/cases/{cid}/runs", json={"mode": "live", "parent_report_id": report1.id})
    assert r2.status_code == 202
    report2 = Report.model_validate(client.get(f"/cases/{cid}/reports/2").json())
    assert report2.recommendation.value == "Do Not Invest"
    assert report2.revision.parent_report_id == report1.id
    # v1 is unchanged after v2
    assert Report.model_validate(client.get(f"/cases/{cid}/reports/1").json()) == report1

    r3 = client.post(f"/cases/{cid}/runs", json={"mode": "live", "parent_report_id": report1.id})
    assert r3.status_code == 409
    _assert_envelope(r3.json(), "mock_limitation")


def test_parent_from_other_case_is_409(client):
    a, b = _case(client), _case(client)
    client.post(f"/cases/{a}/runs", json={"mode": "live"})
    rep_a = client.get(f"/cases/{a}/reports/1").json()
    r = client.post(f"/cases/{b}/runs", json={"mode": "live", "parent_report_id": rep_a["id"]})
    assert r.status_code == 409
    _assert_envelope(r.json(), "incompatible_parent_report")


def test_unknown_parent_is_404(client):
    cid = _case(client)
    r = client.post(f"/cases/{cid}/runs", json={"mode": "live", "parent_report_id": "rep-nope"})
    assert r.status_code == 404


def test_invalid_run_mode_422(client):
    cid = _case(client)
    r = client.post(f"/cases/{cid}/runs", json={"mode": "magic"})
    assert r.status_code == 422
    _assert_envelope(r.json(), "validation_error")


def test_seeded_fixtures_are_served(client):
    assert client.get("/runs/run-synthetic-running").json()["status"] == "running"
    failed = client.get("/runs/run-synthetic-failed").json()
    assert failed["status"] == "failed" and failed["error"]["code"] == "run_interrupted"
    v1 = client.get("/cases/case-synthetic-01/reports/1").json()
    v2 = client.get("/cases/case-synthetic-01/reports/2").json()
    assert v1["recommendation"] == "Conditional" and v2["recommendation"] == "Do Not Invest"


# ---------------------------------------------------------------- evidence / documents
def test_add_evidence(client):
    cid = _case(client)
    r = client.post(f"/cases/{cid}/evidence", json={"title": "Нотатка", "text": "Синтетичний текст"})
    assert r.status_code == 201
    body = r.json()
    assert body["source_id"] and len(body["evidence_ids"]) == 1
    assert client.post("/cases/nope/evidence", json={"title": "t", "text": "x"}).status_code == 404
    assert client.post(f"/cases/{cid}/evidence", json={"title": "t"}).status_code == 422


def _upload(client, cid, name, content, ctype):
    return client.post(f"/cases/{cid}/documents", files={"file": (name, content, ctype)},
                       data={"title": "Doc", "synthetic": "true"})


def test_document_wrong_type_415(client):
    cid = _case(client)
    r = _upload(client, cid, "a.txt", b"hello", "text/plain")
    assert r.status_code == 415
    _assert_envelope(r.json(), "unsupported_media_type")


def test_document_valid_pdf_is_501_until_r3(client):
    cid = _case(client)
    r = _upload(client, cid, "a.pdf", PDF, "application/pdf")
    assert r.status_code == 501
    _assert_envelope(r.json(), "not_implemented")


def test_document_unknown_case_404(client):
    assert _upload(client, "nope", "a.pdf", PDF, "application/pdf").status_code == 404


def test_document_too_large_413(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "50")
    with new_client() as c:
        cid = _case(c)
        r = _upload(c, cid, "a.pdf", PDF + b"x" * 500, "application/pdf")
        assert r.status_code == 413
        _assert_envelope(r.json(), "payload_too_large")
    get_settings.cache_clear()
    get_repository.cache_clear()


def test_api_key_is_required_when_a_secret_is_configured(monkeypatch):
    monkeypatch.setenv("API_SHARED_SECRET", "s3cret-value")
    with new_client() as c:
        assert c.get("/health").status_code == 200          # health stays open
        r = c.post("/cases", json=VALID)
        assert r.status_code == 401
        _assert_envelope(r.json(), "unauthorized")
        assert c.post("/cases", json=VALID, headers={"X-API-Key": "wrong"}).status_code == 401
        assert c.post("/cases", json=VALID, headers={"X-API-Key": "s3cret-value"}).status_code == 201


def test_production_refuses_an_unsafe_configuration(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")   # secret is empty
    with pytest.raises(RuntimeError):
        with new_client():
            pass
