import asyncio
import json

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from vic.config import Settings
from vic.contracts import RunBudget, RunContext, RunMode
from vic.failures import ProviderAuthError, ProviderError, ProviderTimeout
from vic.llm import OpenAICompatibleProvider, StructuredLlm, make_provider

BASE_URL = "https://mentor.example/v1"
KEY = "sk_team_test_only"


def settings(**kwargs):
    return Settings(_env_file=None, **{
        "llm_provider": "openai", "llm_api_key": KEY,
        "llm_base_url": BASE_URL, "llm_model": "gpt-6-luna", **kwargs,
    })


def reply(content='{"answer":"ok"}', usage=None):
    return {"choices": [{"message": {"content": content}}], "usage": usage}


def call(provider, **kwargs):
    return asyncio.run(provider.complete(system="Return JSON", messages=[
        {"role": "user", "content": "hello"}], model="gpt-6-luna", max_tokens=256,
        timeout=3, **kwargs))


def test_gateway_request_and_token_usage():
    def handler(request):
        assert str(request.url) == BASE_URL + "/chat/completions"
        assert request.headers["authorization"] == "Bearer " + KEY
        assert request.extensions["timeout"]["read"] == 3
        assert json.loads(request.content) == {
            "model": "gpt-6-luna", "max_completion_tokens": 256, "stream": False,
            "messages": [{"role": "system", "content": "Return JSON"},
                         {"role": "user", "content": "hello"}],
        }
        return httpx.Response(200, json=reply(usage={"prompt_tokens": 20, "completion_tokens": 10}))

    provider = OpenAICompatibleProvider(settings(llm_base_url=BASE_URL + "/"),
                                        transport=httpx.MockTransport(handler))
    result = call(provider)
    assert (result.text, result.input_tokens, result.output_tokens) == ('{"answer":"ok"}', 20, 10)
    assert isinstance(make_provider(settings()), OpenAICompatibleProvider)


def test_gateway_context_limit_is_actionable_without_exposing_provider_body():
    provider = OpenAICompatibleProvider(settings(), transport=httpx.MockTransport(
        lambda _: httpx.Response(400, json={"error": {"message":
            "Input exceeds the conservative input limit. " + KEY}})))
    with pytest.raises(ProviderError) as exc:
        call(provider)
    assert exc.value.code == "provider_context_limit" and not exc.value.retryable
    assert KEY not in str(exc.value)


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": -1, "completion_tokens": "20"},
                                   {"prompt_tokens": True}])
def test_unavailable_usage_is_not_reported_as_zero(usage):
    provider = OpenAICompatibleProvider(settings(), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=reply(usage=usage))))
    result = call(provider)
    assert result.input_tokens is None and result.output_tokens is None


@pytest.mark.parametrize("status,kind,retryable", [
    (401, ProviderAuthError, False), (403, ProviderAuthError, False),
    (429, ProviderError, True), (503, ProviderError, True),
    (400, ProviderError, False), (404, ProviderError, False), (302, ProviderError, False),
])
def test_errors_are_sanitized_and_redirects_are_not_followed(status, kind, retryable):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=KEY, headers={"location": "https://other.example/"})

    provider = OpenAICompatibleProvider(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(kind) as exc:
        call(provider)
    assert KEY not in str(exc.value) and exc.value.retryable is retryable
    assert len(calls) == 1


@pytest.mark.parametrize("error,kind", [(httpx.ReadTimeout, ProviderTimeout),
                                       (httpx.ConnectError, ProviderError)])
def test_network_errors_do_not_expose_credentials(error, kind):
    def handler(request):
        raise error(KEY, request=request)

    with pytest.raises(kind) as exc:
        call(OpenAICompatibleProvider(settings(), transport=httpx.MockTransport(handler)))
    assert KEY not in str(exc.value) and exc.value.__cause__ is None


@pytest.mark.parametrize("body", ["not json", "{}", '{"choices":[]}',
                                  json.dumps(reply(content=None)), json.dumps(reply(content="")),
                                  json.dumps(reply(usage=[1]))])
def test_invalid_provider_envelope_is_typed(body):
    provider = OpenAICompatibleProvider(settings(), transport=httpx.MockTransport(
        lambda _: httpx.Response(200, text=body)))
    with pytest.raises(ProviderError) as exc:
        call(provider)
    assert exc.value.code == "provider_rejected" and not exc.value.retryable


@pytest.mark.parametrize("kwargs", [{"llm_api_key": ""}, {"llm_base_url": ""},
                                    {"llm_model": "placeholder-model"}])
def test_missing_configuration_never_sends_a_request(kwargs):
    def handler(_):
        pytest.fail("Missing configuration must not send credentials")

    provider = OpenAICompatibleProvider(settings(**kwargs), transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderAuthError):
        asyncio.run(provider.complete(system="s", messages=[], model=settings(**kwargs).llm_model,
                                      max_tokens=10, timeout=1))


@pytest.mark.parametrize("url", ["http://remote.example/v1", "https://key@remote.example/v1",
                                "https://remote.example/v1?api_key=secret",
                                "https://remote.example/v1#fragment", "not-a-url"])
def test_unsafe_base_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        settings(llm_base_url=url)


def test_shared_adapter_retries_repairs_and_records_usage(monkeypatch):
    from vic import llm
    from vic.prompts import LoadedPrompt

    class Out(BaseModel):
        answer: str

    monkeypatch.setattr(llm, "load_prompt", lambda _: LoadedPrompt("science", "s", "v1", None))
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(429, text=KEY)
        content = "bad JSON" if len(requests) == 2 else '{"answer":"repaired"}'
        return httpx.Response(200, json=reply(content, {"prompt_tokens": 20, "completion_tokens": 10}))

    async def no_sleep(_):
        pass

    ctx = RunContext(case_id="c", run_id="r", snapshot_id=None, as_of_date=None,
                     mode=RunMode.LIVE, budget=RunBudget())
    adapter = StructuredLlm(OpenAICompatibleProvider(settings(), transport=httpx.MockTransport(handler)),
                            settings(), sleep=no_sleep)
    result = asyncio.run(adapter.generate_structured("science", {}, Out, ctx))
    assert result.answer == "repaired" and len(requests) == 3
    assert requests[2]["messages"][-2] == {"role": "assistant", "content": "bad JSON"}
    assert [item["outcome"] for item in ctx.trace.usage] == ["provider_error", "ok", "ok"]
    assert ctx.trace.usage[-1]["model"] == "gpt-6-luna"
    assert KEY not in json.dumps(ctx.trace.usage)
