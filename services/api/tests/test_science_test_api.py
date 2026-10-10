import json
from datetime import UTC, datetime

import pytest

from vic.api import science_test
from vic.config import Settings
from vic.contracts import Evidence, EvidencePack, RunMode, Source
from vic.failures import ProviderError
from vic.llm import ProviderResponse, StructuredLlm

INPUT = {"indication": "Disease", "mechanism": "Target inhibition", "scope": "approach"}
EXCERPT = "Retrieved record excerpt retained in full."


@pytest.fixture(autouse=True)
def retrieval(monkeypatch):
    async def retrieve(case, ctx):
        assert ctx.mode == RunMode.LIVE
        assert case.indication == INPUT["indication"]
        return EvidencePack(snapshot_id="test-snapshot", synthetic=False,
            sources=[Source(id="source-1", title="Retrieved source", type="peer_reviewed",
                            retrieved_at=datetime.now(UTC), content_hash="sha256:"+"a"*64, synthetic=False)],
            evidence=[Evidence(id="evidence-1", source_id="source-1", excerpt=EXCERPT,
                               locator="Abstract", scope="approach")])
    monkeypatch.setattr(science_test, "build_evidence_pack", retrieve)


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
    response = client.post("/diagnostics/science", json=INPUT)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["external_retrieval"] is True and data["synthetic"] is False
    assert data["result"]["role_id"] == "science"
    assert len(provider.calls) == 1
    assert EXCERPT in provider.calls[0]["evidence_items"]
    assert data["evidence_pack"]["evidence"][0]["excerpt"] == EXCERPT
    assert provider.calls[0]["evidence_count"] == 1
    assert any("size breakdown" in event["message"] for event in data["events"])
    assert {item["prompt_id"] for item in data["usage"]} == {"science"}


def test_science_test_failure_keeps_diagnostics(client, monkeypatch):
    provider = Provider(ProviderError("Rejected", code="provider_rejected", retryable=False))
    monkeypatch.setattr(science_test, "build_llm", lambda _: StructuredLlm(provider, Settings(_env_file=None)))
    data = client.post("/diagnostics/science", json=INPUT).json()
    assert data["status"] == "failed" and data["result"] is None
    assert data["error"]["code"] == "provider_rejected"
    assert data["events"]


def test_empty_real_retrieval_never_substitutes_synthetic_data(client, monkeypatch):
    async def empty(case, ctx):
        return EvidencePack(snapshot_id="empty", synthetic=False, sources=[], evidence=[], retrieval_warnings=["Unavailable"])
    monkeypatch.setattr(science_test, "build_evidence_pack", empty)
    provider = Provider()
    monkeypatch.setattr(science_test, "build_llm", lambda _: StructuredLlm(provider, Settings(_env_file=None)))
    data = client.post("/diagnostics/science", json=INPUT).json()
    assert data["error"]["code"] == "no_real_evidence"
    assert data["evidence_pack"]["retrieval_warnings"] == ["Unavailable"]
    assert provider.calls == []


def test_science_test_requires_api_auth(client, monkeypatch):
    monkeypatch.setenv("API_SHARED_SECRET", "secret-test-key")
    from vic.config import get_settings
    get_settings.cache_clear()
    assert client.post("/diagnostics/science").status_code == 401
