"""Single structured LLM adapter (contract section 5):
generate_structured(prompt_id, payload, response_model, ctx)."""
import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel

from vic.config import Settings
from vic.contracts import RunContext, RunStage
from vic.failures import (
    BudgetExceeded,
    MalformedModelOutput,
    ModuleNotReady,
    ProviderAuthError,
    ProviderError,
    ProviderTimeout,
    RunFailure,
    RunTimeout,
)
from vic.prompts import load_prompt

T = TypeVar("T", bound=BaseModel)


@dataclass
class ProviderResponse:
    text: str
    input_tokens: int | None
    output_tokens: int | None


class Provider(Protocol):
    name: str

    async def complete(self, *, system: str, messages: list[dict[str, str]], model: str,
                       max_tokens: int, timeout: float) -> ProviderResponse: ...


class PlaceholderProvider:
    name = "placeholder"

    async def complete(self, **_: Any) -> ProviderResponse:
        raise ProviderAuthError("LLM provider is not configured (set LLM_PROVIDER and LLM_API_KEY)")


class AnthropicProvider:
    """Example provider (pip install -e ".[anthropic]"). Replace/add one if the team chose another."""
    name = "anthropic"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client = None

    async def complete(self, *, system, messages, model, max_tokens, timeout) -> ProviderResponse:
        import anthropic  # imported lazily so the package is optional

        if not self._api_key:
            raise ProviderAuthError("LLM_API_KEY is empty")
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key, max_retries=0)
        try:
            resp = await self._client.messages.create(model=model, max_tokens=max_tokens,
                                                      system=system, messages=messages,
                                                      timeout=timeout)
        except anthropic.APITimeoutError as exc:
            raise ProviderTimeout("The model provider timed out") from exc
        except anthropic.AuthenticationError as exc:
            raise ProviderAuthError("The model provider rejected the API key") from exc
        except (anthropic.RateLimitError, anthropic.APIConnectionError,
                anthropic.InternalServerError) as exc:
            raise ProviderError("The model provider is temporarily unavailable") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"The model provider returned HTTP {exc.status_code}",
                                code="provider_rejected", retryable=False) from exc
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return ProviderResponse(text, resp.usage.input_tokens, resp.usage.output_tokens)


class OpenAICompatibleProvider:
    """Chat Completions transport for the mentor's OpenAI-compatible gateway.

    Base URL comes from the team's wallet instructions, not from the key prefix.
    The shared StructuredLlm owns retries, schema repairs, budget and tracing.
    """
    name = "openai"

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self._api_key = settings.llm_api_key
        self._base_url = settings.llm_base_url
        self._transport = transport

    async def complete(self, *, system, messages, model, max_tokens, timeout,
                       reasoning_effort=None) -> ProviderResponse:
        if not self._api_key.strip():
            raise ProviderAuthError("LLM_API_KEY is empty")
        if not self._base_url:
            raise ProviderAuthError("Set LLM_BASE_URL to the base URL from the provider")
        if not model.strip() or model == "placeholder-model":
            raise ProviderAuthError("Set LLM_MODEL to the provider's model/deployment name")
        headers = {"Authorization": f"Bearer {self._api_key}"}
        body = {"model": model, "messages": [{"role": "system", "content": system}, *messages],
                "max_completion_tokens": max_tokens, "stream": False}
        if reasoning_effort is not None:
            body["reasoning_effort"] = reasoning_effort
        try:
            # HTTPX has no implicit retries; redirects must not forward credentials.
            async with httpx.AsyncClient(transport=self._transport, follow_redirects=False) as client:
                response = await client.post(f"{self._base_url}/chat/completions",
                                             headers=headers, json=body, timeout=timeout)
        except httpx.TimeoutException:
            raise ProviderTimeout("The model provider timed out") from None
        except httpx.RequestError:
            raise ProviderError("The model provider is temporarily unavailable") from None
        status = response.status_code
        if status in {401, 403}:
            raise ProviderAuthError("The model provider rejected the API credentials")
        if status == 429 or status >= 500:
            raise ProviderError(f"The model provider returned HTTP {status}")
        if not 200 <= status < 300:
            if status == 400:
                try:
                    message = response.json().get("error", {}).get("message", "")
                except (ValueError, AttributeError):
                    message = ""
                if isinstance(message, str) and "conservative input limit" in message.lower():
                    raise ProviderError("The configured model gateway's input limit is too small for this analysis request.",
                                        code="provider_context_limit", retryable=False)
            raise ProviderError(f"The model provider returned HTTP {status}",
                                code="provider_rejected", retryable=False)
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Missing text")
            usage = data.get("usage") or {}
            if not isinstance(usage, dict):
                raise TypeError("Invalid usage")
        except (ValueError, KeyError, IndexError, TypeError):
            # Never expose provider response bodies (they may echo secrets or user input).
            raise ProviderError("The model provider returned an invalid Chat Completions response",
                                code="provider_rejected", retryable=False) from None

        def token_count(field: str) -> int | None:
            value = usage.get(field)
            return value if type(value) is int and value >= 0 else None

        return ProviderResponse(content, token_count("prompt_tokens"), token_count("completion_tokens"))


def make_provider(settings: Settings) -> Provider:
    name = settings.llm_provider.lower()
    if name == "placeholder":
        return PlaceholderProvider()
    if name == "anthropic":
        return AnthropicProvider(settings.llm_api_key)
    if name == "openai":
        return OpenAICompatibleProvider(settings)
    raise ValueError(f"Unknown LLM_PROVIDER '{settings.llm_provider}'")


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def _compact_schema(value, *, mapping=False):
    """Remove display titles while preserving schema validation and field instructions."""
    if isinstance(value, dict):
        return {key: _compact_schema(child, mapping=key in ("properties", "$defs", "definitions"))
                for key, child in value.items() if mapping or key != "title"}
    if isinstance(value, list):
        return [_compact_schema(child) for child in value]
    return value


MARKET_PROMPTS = ("market_competitive", "market_commercial")


def structured_request(prompt_id, payload, response_model, ctx, *, system_override=None, compact=False):
    """Single serializer used by the planner and runtime, including audit feedback."""
    prompt = load_prompt(prompt_id)
    if compact:
        from vic.request_protocol import compact_schema
        schema = compact_schema(response_model.model_json_schema())
    else:
        schema = json.dumps(_compact_schema(response_model.model_json_schema()),
                            ensure_ascii=False, separators=(",", ":"))
    system = (f"{system_override or prompt.text}\n\n---\nReturn ONLY one JSON object (no markdown, no commentary) "
              f"that validates against this JSON Schema:\n{schema}")
    messages = [{"role": "user", "content": json.dumps(payload, ensure_ascii=False,
                                  default=str, separators=(",", ":"))}]
    owner = "investment" if prompt_id == "investment_plan" else (
        "market" if prompt_id in MARKET_PROMPTS else
        "clinical" if prompt_id in {"clinical_design", "clinical_development"} else prompt_id)
    feedback = ctx.feedback.get(owner)
    if feedback:
        messages.append({"role": "user", "content": "Correct the audit/completeness findings: "
            + json.dumps([item.model_dump(mode="json") if isinstance(item, BaseModel) else item
                          for item in feedback], ensure_ascii=False, default=str)})
    return prompt, system, messages


def request_sizes(system, messages, *, model="placeholder-model", max_tokens=4096, reasoning_effort=None):
    """UTF-8 bytes/characters, not token estimates; includes message envelopes."""
    body = {"model": model, "messages": [{"role": "system", "content": system}, *messages],
            "max_completion_tokens": max_tokens, "stream": False}
    if reasoning_effort is not None:
        body["reasoning_effort"] = reasoning_effort
    wire = json.dumps(body,
                      ensure_ascii=False, separators=(",", ":"))
    prompt, _, schema = system.partition("\n\n---\nReturn ONLY one JSON object (no markdown, no commentary) "
                                        "that validates against this JSON Schema:\n")
    return {"request_bytes": len(wire.encode("utf-8")), "request_chars": len(wire),
            "prompt_bytes": len(prompt.encode("utf-8")), "schema_bytes": len(schema.encode("utf-8")),
            "payload_bytes": len(messages[0]["content"].encode("utf-8")),
            "feedback_repair_bytes": sum(len(m["content"].encode("utf-8")) for m in messages[1:]),
            "system_bytes": len(system.encode("utf-8")),
            "messages_bytes": len(json.dumps(messages, ensure_ascii=False,
                separators=(",", ":")).encode("utf-8"))}


class StructuredLlm:
    """Implements the LlmAdapter protocol from vic.contracts."""

    def __init__(self, provider: Provider, settings: Settings,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self._provider = provider
        self._s = settings
        self._sleep = sleep

    @property
    def market_request_budget(self) -> int:
        return self._s.market_request_max_bytes

    def structured_request_size(self, prompt_id, payload, response_model, ctx):
        _, system, messages = structured_request(prompt_id, payload, response_model, ctx)
        return request_sizes(system, messages, model=self._s.llm_model,
                             max_tokens=self._s.llm_max_output_tokens,
                             reasoning_effort=self._reasoning_effort(prompt_id))

    def _reasoning_effort(self, prompt_id):
        if not isinstance(self._provider, OpenAICompatibleProvider):
            return None
        if prompt_id in {"clinical", "clinical_design", "clinical_development"}:
            return self._s.clinical_reasoning_effort
        if prompt_id in MARKET_PROMPTS:
            return self._s.market_reasoning_effort
        if prompt_id in {"ip_licensing", "partnerships", "investment_plan", "investment",
                         "investment_threshold", "failure_miner", "chair", "audit", "context_brief"}:
            return self._s.node_reasoning_effort
        return None

    def cost_limit_enforceable(self) -> bool:
        return (self._s.llm_price_input_per_mtok is not None
                and self._s.llm_price_output_per_mtok is not None)

    async def generate_structured(self, prompt_id: str, payload: dict[str, Any],
                                  response_model: type[T], ctx: RunContext) -> T:
        from vic.request_protocol import TASKS, generate_bounded
        if prompt_id in TASKS and self.structured_request_size(prompt_id, payload, response_model, ctx)["request_bytes"] > self._s.node_initial_request_bytes:
            return await generate_bounded(self, prompt_id, payload, response_model, ctx)
        return await self._generate_direct(prompt_id, payload, response_model, ctx)

    async def _generate_direct(self, prompt_id, payload, response_model, ctx, *, system_override=None,
                               compact=False, inverse=None):
        prompt, system, messages = structured_request(prompt_id, payload, response_model, ctx,
                                                       system_override=system_override, compact=compact)
        original_messages = messages
        repairs = 0
        while True:
            response = await self._call(prompt.prompt_id, prompt.version, system, messages, ctx)
            try:
                if inverse:
                    from vic.request_protocol import translate, validate_component_references
                    data = translate(json.loads(_extract_json(response.text)), inverse)
                    validate_component_references(prompt_id, payload, data, inverse)
                    return response_model.model_validate(data)
                return response_model.model_validate_json(_extract_json(response.text))
            except ValueError as exc:  # pydantic.ValidationError is a ValueError
                if hasattr(exc, "errors"):
                    locations = [{"type": error["type"], "loc": error["loc"]}
                                 for error in exc.errors(include_input=False, include_context=False)]
                    ctx.trace.log(RunStage.ANALYZE, f"{prompt_id} schema errors {locations}")
                if repairs >= self._s.llm_max_repairs:
                    raise MalformedModelOutput(
                        f"The model output for '{prompt_id}' did not match the required schema "
                        f"after {repairs} repair attempt(s)") from None
                repairs += 1
                if compact or prompt_id == "context_brief":
                    messages = original_messages + [{"role": "user", "content":
                        "Correct the schema error and return only valid JSON: " + str(exc)[:1000]}]
                    continue
                messages = messages + [
                    {"role": "assistant", "content": response.text},
                    {"role": "user", "content": "Your previous answer was invalid: "
                     f"{str(exc)[:1500]}\nReturn ONLY the corrected JSON object."}]

    async def _call(self, prompt_id: str, version: str, system: str,
                    messages: list[dict[str, str]], ctx: RunContext) -> ProviderResponse:
        if prompt_id not in {*MARKET_PROMPTS, "clinical", "clinical_design", "clinical_development"}:
            sizes = request_sizes(system, messages, model=self._s.llm_model,
                                  max_tokens=self._s.llm_max_output_tokens,
                                  reasoning_effort=self._reasoning_effort(prompt_id))
            ctx.trace.log(RunStage.ANALYZE, f"{prompt_id} request sizes {sizes}; budget_bytes={self._s.node_request_max_bytes}")
            if sizes["request_bytes"] > self._s.node_request_max_bytes:
                raise RunFailure("Node request exceeds the configured byte budget", code="node_request_budget")
        if prompt_id in MARKET_PROMPTS:
            sizes = request_sizes(system, messages, model=self._s.llm_model,
                                  max_tokens=self._s.llm_max_output_tokens,
                                  reasoning_effort=self._reasoning_effort(prompt_id))
            ctx.trace.log(RunStage.ANALYZE, f"{prompt_id} request sizes {sizes}; "
                          f"budget_bytes={self.market_request_budget}")
            if sizes["request_bytes"] > self.market_request_budget:
                raise RunFailure("Market request exceeds the configured byte budget; "
                                 "reduce/batch context or audit/schema repair messages",
                                 code="market_request_budget")
        attempt = 0
        while True:
            self._check_budget(ctx)
            timeout = self._timeout(ctx)
            started = time.monotonic()
            try:
                options = {}
                effort = self._reasoning_effort(prompt_id)
                if effort is not None:
                    options["reasoning_effort"] = effort
                response = await asyncio.wait_for(
                    self._provider.complete(system=system, messages=messages, model=self._s.llm_model,
                                            max_tokens=self._s.llm_max_output_tokens, timeout=timeout,
                                            **options),
                    timeout=timeout + 5)
            except TimeoutError:
                error: ProviderError = ProviderTimeout("The model provider timed out")
            except ProviderError as exc:
                error = exc
            else:
                self._record(ctx, prompt_id, version, attempt, started, response, "ok")
                return response
            self._record(ctx, prompt_id, version, attempt, started, None, error.code)
            if not error.retryable or attempt >= self._s.llm_max_retries:
                raise error
            attempt += 1
            await self._sleep(min(0.5 * 2 ** attempt, 8.0))

    def _timeout(self, ctx: RunContext) -> float:
        remaining = ctx.budget.remaining_seconds()
        if remaining is not None and remaining <= 0:
            raise RunTimeout("The run time limit was reached")
        base = self._s.llm_request_timeout_seconds
        return base if remaining is None else max(1.0, min(base, remaining))

    def _check_budget(self, ctx: RunContext) -> None:
        remaining = ctx.budget.remaining_seconds()
        if remaining is not None and remaining <= 0:
            raise RunTimeout("The run time limit was reached")
        b = ctx.budget
        if (b.max_cost_usd is not None and not b.cost_unavailable
                and b.spent_cost_usd >= b.max_cost_usd):
            raise BudgetExceeded("The approximate cost limit of this run was reached")

    def _record(self, ctx: RunContext, prompt_id: str, version: str, attempt: int, started: float,
                response: ProviderResponse | None, outcome: str) -> None:
        tin = response.input_tokens if response else None
        tout = response.output_tokens if response else None
        cost = None
        if (tin is not None and tout is not None and self._s.llm_price_input_per_mtok is not None
                and self._s.llm_price_output_per_mtok is not None):
            cost = (tin * self._s.llm_price_input_per_mtok
                    + tout * self._s.llm_price_output_per_mtok) / 1_000_000
            ctx.budget.spent_cost_usd += cost
        elif response is not None:
            ctx.budget.cost_unavailable = True  # an answered call we cannot price: never fake 0
        ctx.trace.record_usage(prompt_id, tin, tout, prompt_version=version,
                               model=self._s.llm_model, attempt=attempt, outcome=outcome,
                               latency_ms=int((time.monotonic() - started) * 1000), cost_usd=cost)


def build_llm(settings: Settings) -> StructuredLlm:
    return StructuredLlm(make_provider(settings), settings)
PROMPT_IDS = ("science", "translation", "clinical", "clinical_design", "clinical_development", "market", "market_competitive", "market_commercial", "investment_plan", "investment",
              "chair", "audit", "ip_licensing", "partnerships", "investment_threshold", "failure_miner", "context_brief")


async def generate_structured(prompt_id: str, payload: dict[str, Any], response_model: type[T],
                              ctx: RunContext) -> T:
    """Module-level convenience: delegates to the adapter held by the RunContext."""
    if ctx.model is None:
        raise ModuleNotReady("The RunContext has no model adapter")
    return await ctx.model.generate_structured(prompt_id, payload, response_model, ctx)
