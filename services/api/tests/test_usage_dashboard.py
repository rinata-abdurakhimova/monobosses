import pytest
from pydantic import ValidationError
from vic.config import Settings
from vic.contracts import Run
from vic.storage import get_repository


def test_runs_and_trace_preserve_unknown_usage_and_hide_private_config(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret-test-key")
    from vic.config import get_settings
    get_settings.cache_clear()
    repo = get_repository()
    run = Run(id="run-usage-test", case_id="case-usage-test", status="running",
              trace_id="trace-usage-test", mode="live")
    repo.create_run(run)
    assert client.get("/runs").status_code == 200
    data = next(item for item in client.get("/runs").json() if item["id"] == run.id)
    assert data["cost_usd"] is None and data["usage"]["input_tokens"] is None
    assert client.get(f"/runs/{run.id}/trace").json()["available"] is False
    repo.save_trace(run.id, {"run_id": run.id, "trace_id": run.trace_id,
        "config": {"llm_api_key": "secret-test-key", "llm_base_url": "private-host",
                   "llm_price_input_per_mtok": 2, "llm_price_output_per_mtok": 10,
                   "llm_price_date": "2026-10-10"},
        "events": [{"stage": "analyze", "message": "failure secret-test-key"}],
        "usage": [{"prompt_id": "science", "input_tokens": None, "output_tokens": None}],
        "raw_prompt": "private prompt"})
    response = client.get(f"/runs/{run.id}/trace")
    assert response.status_code == 200
    trace = response.json()
    assert trace["available"] and trace["pricing"]["llm_price_date"] == "2026-10-10"
    assert "secret-test-key" not in response.text
    assert "private-host" not in response.text and "private prompt" not in response.text
    assert client.get("/runs/run-missing/trace").status_code == 404


@pytest.mark.parametrize("setting,value", [
    ("llm_price_input_per_mtok", -1), ("llm_price_output_per_mtok", float("inf")),
    ("llm_price_date", "2026-99-99"), ("llm_price_date", "20261010")])
def test_invalid_pricing_is_rejected(setting, value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{setting: value})


def test_usage_endpoints_require_existing_api_auth(client, monkeypatch):
    from vic.config import get_settings
    monkeypatch.setenv("API_SHARED_SECRET", "usage-auth-secret")
    get_settings.cache_clear()
    for path in ("/runs", "/runs/run-missing/trace"):
        assert client.get(path).status_code == 401
    assert client.get("/runs", headers={"X-API-Key": "usage-auth-secret"}).status_code == 200
