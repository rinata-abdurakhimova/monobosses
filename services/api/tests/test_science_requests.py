import json

import pytest
from pydantic import BaseModel

from vic.config import Settings
from vic.contracts import RunBudget, RunContext, RunMode
from vic.llm import ProviderResponse, StructuredLlm, request_sizes


class Result(BaseModel):
    answer: str


class Provider:
    name = "fake"

    def __init__(self):
        self.requests = []
        self.segments = []

    async def complete(self, *, system, messages, model, max_tokens, timeout):
        self.requests.append(request_sizes(system, messages, model=model, max_tokens=max_tokens)["request_bytes"])
        data = json.loads(messages[0]["content"])
        if "evidence_segment" in data:
            self.segments.append(data)
            return ProviderResponse('{"observations":"Animal finding [ev1].", "uncertainties":"No human evidence."}', None, None)
        assert data["reviewed_characters"] == sum(len(row["evidence_segment"]) for row in self.segments)
        return ProviderResponse('{"answer":"accepted"}', None, None)


@pytest.mark.asyncio
async def test_science_reviews_every_character_with_bounded_wire_requests():
    provider = Provider()
    adapter = StructuredLlm(provider, Settings(_env_file=None, science_request_target_bytes=10000))
    ctx = RunContext(case_id="c", run_id="r", snapshot_id=None, as_of_date=None,
                     mode=RunMode.LIVE, budget=RunBudget())
    evidence = '[ev1] "Quoted" animal evidence 🧬\n' * 700
    result = await adapter.generate_structured("science", {
        "indication": "X", "mechanism": "Y", "evidence_items": evidence}, Result, ctx)
    assert result.answer == "accepted"
    assert len(provider.segments) > 1
    assert "".join(row["evidence_segment"] for row in provider.segments) == evidence
    assert provider.segments[0]["segment_start"] == 0
    assert provider.segments[-1]["segment_end"] == len(evidence)
    assert max(provider.requests) <= 10000 - 512
    assert any("raw_schema_bytes=" in event["message"] for event in ctx.trace.events)
