import asyncio
import time

import pytest
from pydantic import BaseModel

from vic import llm as llm_module
from vic.config import Settings
from vic.contracts import RunBudget, RunContext, RunMode
from vic.failures import (BudgetExceeded, MalformedModelOutput, ProviderAuthError, ProviderTimeout,
                          RunTimeout)
from vic.llm import ProviderResponse, StructuredLlm
from vic.prompts import LoadedPrompt
from vic.tracing import scrub


class Out(BaseModel):
    answer: str


class FakeProvider:
    name = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def complete(self, *, system, messages, model, max_tokens, timeout):
        self.calls.append(messages)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return ProviderResponse(text=item, input_tokens=100, output_tokens=50)


async def _no_sleep(_):
    return None


@pytest.fixture(autouse=True)
def _fake_prompt(monkeypatch):
    monkeypatch.setattr(llm_module, "load_prompt",
                        lambda pid: LoadedPrompt(pid, "SYSTEM PROMPT", "v123", None))


def _settings(**kw):
    return Settings(_env_file=None, llm_max_retries=2, llm_max_repairs=1, **kw)


def _ctx(**budget):
    return RunContext(case_id="c", run_id="r", snapshot_id=None, as_of_date=None,
                      mode=RunMode.LIVE, budget=RunBudget(**budget))


def _run(provider, settings, ctx):
    adapter = StructuredLlm(provider, settings, sleep=_no_sleep)
    return asyncio.run(adapter.generate_structured("science", {"x": 1}, Out, ctx))


def test_valid_answer_records_usage_and_version():
    ctx = _ctx()
    out = _run(FakeProvider(['{"answer": "ok"}']), _settings(), ctx)
    assert out.answer == "ok"
    usage = ctx.trace.usage[0]
    assert usage["prompt_version"] == "v123" and usage["input_tokens"] == 100
    assert usage["cost_usd"] is None and ctx.budget.cost_unavailable  # no prices configured


def test_markdown_fences_are_stripped():
    out = _run(FakeProvider(['```json\n{"answer": "ok"}\n```']), _settings(), _ctx())
    assert out.answer == "ok"


def test_one_repair_round_fixes_invalid_json():
    provider = FakeProvider(["not json", '{"answer": "fixed"}'])
    assert _run(provider, _settings(), _ctx()).answer == "fixed"
    assert len(provider.calls) == 2 and "invalid" in provider.calls[1][-1]["content"]


def test_repairs_are_bounded():
    provider = FakeProvider(["bad", "still bad", '{"answer": "never reached"}'])
    with pytest.raises(MalformedModelOutput):
        _run(provider, _settings(), _ctx())
    assert len(provider.calls) == 2


def test_provider_errors_are_retried_then_succeed():
    provider = FakeProvider([ProviderTimeout("t"), '{"answer": "ok"}'])
    assert _run(provider, _settings(), _ctx()).answer == "ok"
    assert len(provider.calls) == 2


def test_retries_are_bounded():
    provider = FakeProvider([ProviderTimeout("t")] * 5)
    with pytest.raises(ProviderTimeout):
        _run(provider, _settings(), _ctx())
    assert len(provider.calls) == 3  # first try + 2 retries


def test_auth_errors_are_not_retried():
    provider = FakeProvider([ProviderAuthError("bad key")] * 3)
    with pytest.raises(ProviderAuthError):
        _run(provider, _settings(), _ctx())
    assert len(provider.calls) == 1


def test_cost_is_computed_when_prices_are_known():
    ctx = _ctx()
    settings = _settings(llm_price_input_per_mtok=1000.0, llm_price_output_per_mtok=1000.0)
    _run(FakeProvider(['{"answer": "ok"}']), settings, ctx)
    assert ctx.budget.spent_cost_usd == pytest.approx(0.15) and not ctx.budget.cost_unavailable


def test_cost_limit_stops_the_next_call():
    ctx = _ctx(max_cost_usd=0.1)
    settings = _settings(llm_price_input_per_mtok=1000.0, llm_price_output_per_mtok=1000.0)
    adapter = StructuredLlm(FakeProvider(['{"answer": "a"}', '{"answer": "b"}']), settings,
                            sleep=_no_sleep)
    asyncio.run(adapter.generate_structured("science", {}, Out, ctx))
    with pytest.raises(BudgetExceeded):
        asyncio.run(adapter.generate_structured("science", {}, Out, ctx))


def test_cost_limit_is_not_applied_without_prices():
    ctx = _ctx(max_cost_usd=0.0001)
    adapter = StructuredLlm(FakeProvider(['{"answer": "a"}', '{"answer": "b"}']), _settings(),
                            sleep=_no_sleep)
    asyncio.run(adapter.generate_structured("science", {}, Out, ctx))
    asyncio.run(adapter.generate_structured("science", {}, Out, ctx))  # must not raise
    assert not adapter.cost_limit_enforceable()


def test_expired_deadline_stops_the_call():
    ctx = _ctx(deadline=time.monotonic() - 1)
    with pytest.raises(RunTimeout):
        _run(FakeProvider(['{"answer": "ok"}']), _settings(), ctx)


def test_scrub_removes_secrets():
    cleaned = scrub({"LLM_API_KEY": "abc", "max_output_tokens": 10, "note": "key sk-secret-123456 end"},
                    ["sk-secret-123456"])
    assert cleaned["LLM_API_KEY"] == "[redacted]"
    assert cleaned["max_output_tokens"] == 10
    assert "sk-secret-123456" not in cleaned["note"]