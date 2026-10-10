import json

from vic.api import science_test
from vic.config import Settings
from vic.failures import ProviderError
from vic.llm import ProviderResponse, StructuredLlm


class Provider:
    name = "fake"

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def complete(self, *, system, messages, model, max_tokens, timeout):
        self.calls.append(json.loads(messages[0]["content"]))
        if self.error:
            raise self.error
        return ProviderResponse(json.dumps({"thesis": "Fictional mouse data cannot establish human benefit.",
            "position": "insufficient_data", "claims": [], "supporting_arguments": [],
            "opposing_arguments": [], "risks": [], "unknowns": ["Human benefit"],
            "change_conditions": [], "limitations": ["Fictional test"]}), 100, 50)


def test_isolated_science_test_returns_actual_result_and_diagnostics(client, monkeypatch):
    provider = Provider()
    monkeypatch.setattr(science_test, "build_llm", lambda _: StructuredLlm(provider, Settings(_env_file=None)))
    response = client.post("/diagnostics/science")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["external_retrieval"] is False and data["synthetic"] is True
    assert data["result"]["role_id"] == "science"
    assert len(provider.calls) == 1
    assert science_test.EXCERPT in provider.calls[0]["evidence_items"]
    assert provider.calls[0]["evidence_count"] == 1
    assert any("size breakdown" in event["message"] for event in data["events"])
    assert {item["prompt_id"] for item in data["usage"]} == {"science"}


def test_science_test_failure_keeps_diagnostics(client, monkeypatch):
    provider = Provider(ProviderError("Rejected", code="provider_rejected", retryable=False))
    monkeypatch.setattr(science_test, "build_llm", lambda _: StructuredLlm(provider, Settings(_env_file=None)))
    data = client.post("/diagnostics/science").json()
    assert data["status"] == "failed" and data["result"] is None
    assert data["error"]["code"] == "provider_rejected"
    assert data["events"]


def test_science_test_requires_api_auth(client, monkeypatch):
    monkeypatch.setenv("API_SHARED_SECRET", "secret-test-key")
    from vic.config import get_settings
    get_settings.cache_clear()
    assert client.post("/diagnostics/science").status_code == 401
