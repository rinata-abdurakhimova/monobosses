import asyncio

from vic.contracts import Claim, Importance, Provenance, RunContext, RunMode, Scope, SupportStatus
from vic.evidence import fixtures
from vic.evidence.audit_semantic import SemanticAudit, _Verdict, audit_claims_semantic

PACK = fixtures.build_baseline_pack().pack


class FakeModel:
    def __init__(self, verdicts=(), error=None):
        self.verdicts, self.error, self.calls = list(verdicts), error, []

    async def generate_structured(self, prompt_id, payload, response_model, ctx):
        self.calls.append((prompt_id, payload))
        if self.error:
            raise self.error
        return response_model(verdicts=self.verdicts)


def _ev(fragment):
    return next(e.id for e in PACK.evidence if fragment in e.excerpt)


def _claim(cid, text, ev_ids, imp=Importance.CRITICAL):
    return Claim(id=cid, text=text, provenance=Provenance.SOURCE, support_status=SupportStatus.SUPPORTED,
                 evidence_ids=list(ev_ids), assumptions=[], scope=Scope.PROGRAM, importance=imp)


def _v(cid, verdict, reason="The excerpt does not show this. [ev]"):
    return _Verdict(claim_id=cid, verdict=verdict, reason=reason, population="human",
                    candidate_match="same_candidate", evidence_type="absence_of_data", polarity="negative")


def _run(claims, model):
    ctx = RunContext(case_id="c", run_id="r", snapshot_id=None, as_of_date=None, mode=RunMode.LIVE, model=model)
    return asyncio.run(audit_claims_semantic(claims, PACK, ctx))


SAFE = "X-001 is safe in humans at the tested dose."
UNKNOWN_EV = "A safe human exposure range is unknown"


def test_absence_of_data_cited_as_safety_is_caught_by_the_llm_step():
    c = _claim("translation.human_safety", SAFE, [_ev(UNKNOWN_EV)])
    model = FakeModel([_v(c.id, "unverified", "The excerpt says safe exposure is unknown, not safe.")])
    res = _run([c], model)
    f = res.findings[0]
    assert f.verdict == SupportStatus.UNVERIFIED and f.blocking and f.reason.startswith("LLM-assisted:")
    assert res.unresolved_critical_claim_ids == [c.id]
    assert model.calls[0][0] == "audit" and "unknown" in model.calls[0][1]["audit_items"]


def test_llm_cannot_rescue_a_claim_that_already_failed():
    c = _claim("translation.human_efficacy", "X-001 lowers marker M in patients.", [_ev("mouse model, the SYN-1 inhibitor")])
    model = FakeModel([_v(c.id, "supported")])
    res = _run([c], model)
    assert res.findings[0].verdict == SupportStatus.UNVERIFIED and res.findings[0].blocking
    assert model.calls == []  # failed claims are not even sent to the model


def test_llm_agreement_keeps_supported():
    c = _claim("science.mouse_effect", "In a mouse model, X-001 lowered marker M by 48%.", [_ev("mouse model, the SYN-1 inhibitor")])
    res = _run([c], FakeModel([_v(c.id, "supported")]))
    assert res.findings[0].verdict == SupportStatus.SUPPORTED and "agrees" in res.findings[0].reason


def test_llm_failure_is_a_warning_not_a_crash():
    c = _claim("science.mouse_effect", "In a mouse model, X-001 lowered marker M by 48%.", [_ev("mouse model, the SYN-1 inhibitor")])
    res = _run([c], FakeModel(error=RuntimeError("boom")))
    assert res.findings[0].verdict == SupportStatus.SUPPORTED and not res.findings[0].blocking
    assert any("Semantic (LLM) audit unavailable" in w for w in res.warnings)


def test_missing_model_is_reported():
    c = _claim("science.mouse_effect", "In a mouse model, X-001 lowered marker M by 48%.", [_ev("mouse model, the SYN-1 inhibitor")])
    res = _run([c], None)
    assert any("no LLM adapter" in w for w in res.warnings)


def test_garbage_llm_output_is_ignored_with_warnings():
    c = _claim("translation.human_safety", SAFE, [_ev(UNKNOWN_EV)])
    res = _run([c], FakeModel([_v("chair.invented", "unverified"), _v(c.id, "maybe")]))
    assert res.findings[0].verdict == SupportStatus.SUPPORTED
    assert sum("invalid verdict" in w for w in res.warnings) == 2


def test_non_critical_downgrade_is_reported_but_not_blocking():
    c = _claim("translation.human_safety", SAFE, [_ev(UNKNOWN_EV)], imp=Importance.MAJOR)
    res = _run([c], FakeModel([_v(c.id, "unverified")]))
    assert res.findings[0].verdict == SupportStatus.UNVERIFIED and not res.findings[0].blocking
    assert res.unresolved_critical_claim_ids == []