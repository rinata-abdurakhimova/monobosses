"""Regression for the live unknown/unverified Partnerships claim failure."""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from tests.vic.agents.business.test_partnerships import inputs, output
from vic.agents.business.partnerships import PartnershipsAnalysis, analyze_partnerships


@pytest.mark.parametrize("status", ["unknown", "unverified"])
@pytest.mark.parametrize("assumptions", [[], ["  "]])
def test_uncertain_claim_requires_own_nonblank_gap_during_schema_validation(status, assumptions):
    data = output()
    data["claims"][0].update(support_status=status, assumptions=assumptions)
    # Global and finding-level gaps already exist; they cannot replace the claim's own basis.
    with pytest.raises(ValidationError, match="nonblank"):
        PartnershipsAnalysis.model_validate(data)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["unknown", "unverified"])
@pytest.mark.parametrize("component", [False, True])
async def test_live_style_uncertain_claim_gets_one_compact_repair(status, component):
    import json

    from pydantic import create_model

    from vic.config import Settings
    from vic.llm import ProviderResponse, StructuredLlm

    invalid = output()
    invalid["claims"][0].update(support_status=status, assumptions=[])
    corrected = deepcopy(invalid)
    corrected["claims"][0]["assumptions"] = ["Partner category fit has not been verified against a reviewed portfolio."]
    model = PartnershipsAnalysis
    if component:
        # Bounded requests retain the nested claim model and its validators.
        model = create_model("PartnershipsClaimsComponent", claims=(
            PartnershipsAnalysis.model_fields["claims"].annotation, ...))
        invalid = {"claims": invalid["claims"]}
        corrected = {"claims": corrected["claims"]}

    class Provider:
        name = "test"

        def __init__(self):
            self.calls = []

        async def complete(self, *, system, messages, model, max_tokens, timeout):
            self.calls.append(messages)
            if len(self.calls) == 1:
                return ProviderResponse(json.dumps(invalid), 10, 10)
            feedback = messages[-1]["content"]
            assert "partnerships.fit" in feedback
            assert "nonblank" in feedback
            assert "missing-data gap" in feedback
            return ProviderResponse(json.dumps(corrected), 10, 10)

    case, pack, ctx = inputs()
    provider = Provider()
    adapter = StructuredLlm(provider, Settings(_env_file=None, provider_input_limit_test=True))
    if component:
        result = await adapter.generate_structured("partnerships", {}, model, ctx)
    else:
        ctx.model = adapter
        result = await analyze_partnerships(case, pack, ctx)
    assert result.claims[0].support_status == status
    assert result.claims[0].assumptions == corrected["claims"][0]["assumptions"]
    assert len(provider.calls) == 2
    assert all(m["role"] != "assistant" for m in provider.calls[1])
    assert len(provider.calls[1][-1]["content"].encode()) < 512


@pytest.mark.asyncio
async def test_uncertain_claim_still_invalid_after_repair_is_controlled_failure():
    import json

    from vic.config import Settings
    from vic.failures import MalformedModelOutput
    from vic.llm import ProviderResponse, StructuredLlm

    invalid = output()
    invalid["claims"][0]["assumptions"] = []

    class Provider:
        name = "test"
        calls = 0

        async def complete(self, **kwargs):
            self.calls += 1
            return ProviderResponse(json.dumps(invalid), 10, 10)

    case, pack, ctx = inputs()
    provider = Provider()
    ctx.model = StructuredLlm(provider, Settings(_env_file=None, provider_input_limit_test=True))
    with pytest.raises(MalformedModelOutput):
        await analyze_partnerships(case, pack, ctx)
    assert provider.calls == 2
