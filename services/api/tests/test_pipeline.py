"""Pipeline tests with synthetic stub modules (no network, no model)."""
import asyncio
import dataclasses
import json
from datetime import date

import pytest

from vic import synthetic
from vic.config import Settings
from vic.contracts import (AuditFinding, AuditResult, CaseInput, EvidenceCreate, EvidencePack,
                           Recommendation, Run, RunMode, RunStatus)
from vic.failures import MalformedModelOutput, ModuleNotReady, ProviderTimeout
from vic.modules import call_clinical, get_modules
from vic.pipeline import Pipeline
from vic.storage import SqliteRepository, new_id
from vic.stubs import make_stub_modules

CASE = CaseInput(indication="Синтетичне X", mechanism="Інгібування Y", scope="program",
                 program_data="Синтетична програма: пероральна мала молекула, дані обмежені, без клінічних даних.")

def real_looking(modules=None):
    """Modules that do not claim to be stubs (as if all agents were real)."""
    return dataclasses.replace(modules or make_stub_modules(), origin={})

class Env:
    def __init__(self, tmp_path, modules=None, **kw):
        kw.setdefault("dev_stubs", True)
        self.settings = Settings(_env_file=None, llm_api_key="sk-very-secret-key", **kw)
        self.repo = SqliteRepository(str(tmp_path / "p.sqlite3"), seed=False)
        self.case_id = self.repo.create_case(CASE)
        self.modules = modules or make_stub_modules()

    def run(self, parent_report_id=None, mode=RunMode.LIVE, case_id=None, modules_factory=None) -> Run:
        run = Run(id=new_id("run"), case_id=case_id or self.case_id, status=RunStatus.QUEUED,
                  trace_id=new_id("trace"), mode=mode, parent_report_id=parent_report_id)
        self.repo.create_run(run)
        pipeline = Pipeline(self.repo, self.settings, modules_factory or (lambda: self.modules),
                            llm_factory=lambda: None)
        return asyncio.run(pipeline.execute(run))


def test_happy_path_saves_a_valid_report_and_trace(tmp_path):
    env = Env(tmp_path)
    run = env.run()
    assert run.status == RunStatus.COMPLETED and run.report_version == 1
    report = env.repo.get_report(env.case_id, 1)
    assert len(report.sections) == 11 and 5 <= len(report.diligence_questions) <= 10
    assert report.synthetic and report.recommendation == Recommendation.CONDITIONAL
    assert set(run.latency_ms) == {"validate", "retrieve", "analyze", "audit", "synthesize",
                                   "finalize", "total"}
    assert run.cost_usd is None                       # unavailable is never 0
    assert any("SYNTHETIC" in w for w in run.warnings)
    trace = env.repo.get_trace(run.id)
    assert trace["snapshot_id"] == report.snapshot_id and trace["config_version"]
    assert "sk-very-secret-key" not in json.dumps(trace)
    assert env.repo.get_snapshot(report.snapshot_id) is not None


def test_rerun_with_new_evidence_creates_a_revision_and_keeps_v1(tmp_path):
    env = Env(tmp_path)
    env.run()
    v1 = env.repo.get_report(env.case_id, 1)
    created = env.repo.add_evidence(env.case_id, EvidenceCreate(
        title="Synthetic note", text="Синтетичний результат безпеки", synthetic=True))
    run2 = env.run(parent_report_id=v1.id)
    assert run2.status == RunStatus.COMPLETED and run2.report_version == 2
    v2 = env.repo.get_report(env.case_id, 2)
    assert v2.revision.parent_report_id == v1.id
    assert v2.revision.new_evidence_ids == created.evidence_ids
    assert created.evidence_ids[0] in v2.revision.explanation
    assert env.repo.get_report(env.case_id, 1) == v1  # v1 is unchanged


def test_agent_crash_fails_the_run_without_a_report(tmp_path):
    async def boom(case, pack, ctx):
        raise RuntimeError("secret internal detail")
    env = Env(tmp_path, dataclasses.replace(make_stub_modules(), analyze_science=boom))
    run = env.run()
    assert run.status == RunStatus.FAILED and run.error.code == "agent_error"
    assert "secret internal detail" not in run.error.message
    assert run.stage.value == "analyze" and env.repo.get_report(env.case_id, 1) is None


@pytest.mark.parametrize("exc,code,retryable", [
    (ProviderTimeout("slow"), "provider_timeout", True),
    (MalformedModelOutput("bad json"), "malformed_model_output", False)])
def test_provider_and_malformed_output_failures(tmp_path, exc, code, retryable):
    async def fail(case, pack, ctx):
        raise exc
    env = Env(tmp_path, dataclasses.replace(make_stub_modules(), analyze_market=fail))
    run = env.run()
    assert run.status == RunStatus.FAILED and run.error.code == code and run.error.retryable == retryable
    assert env.repo.get_report(env.case_id, 1) is None  # malformed output never becomes a report


def test_source_outage_is_not_a_confirmed_absence_of_data(tmp_path):
    async def down(case, ctx):
        raise ConnectionError("registry unreachable")
    env = Env(tmp_path, dataclasses.replace(make_stub_modules(), build_evidence_pack=down))
    run = env.run()
    assert run.error.code == "source_outage" and "NOT a confirmed absence" in run.error.message


def test_empty_pack_with_warnings_is_an_outage(tmp_path):
    async def empty(case, ctx):
        return EvidencePack(sources=[], evidence=[], retrieval_warnings=["PubMed timeout"],
                            snapshot_id="x", synthetic=False)
    env = Env(tmp_path, dataclasses.replace(make_stub_modules(), build_evidence_pack=empty))
    assert env.run().error.code == "source_outage"


def test_blocking_audit_triggers_exactly_one_repair(tmp_path):
    base, calls, feedback = make_stub_modules(), {"science": 0, "audit": 0}, {}

    async def science(case, pack, ctx):
        calls["science"] += 1
        feedback["science"] = list(ctx.feedback.get("science", []))
        return await base.analyze_science(case, pack, ctx)

    async def audit(claims, pack, ctx):
        calls["audit"] += 1
        blocking = calls["audit"] == 1
        findings = [AuditFinding(claim_id=c.id, verdict=c.support_status, reason="check",
                                 evidence_ids=list(c.evidence_ids),
                                 blocking=blocking and c.id == "science.target_validation") for c in claims]
        return AuditResult(findings=findings)
    env = Env(tmp_path, dataclasses.replace(base, analyze_science=science, audit_claims=audit))
    run = env.run()
    assert run.status == RunStatus.COMPLETED
    assert calls["science"] == 2 and calls["audit"] == 2
    assert feedback["science"] and feedback["science"][0].claim_id == "science.target_validation"


def test_persistent_blocking_downgrades_claims_and_never_invests(tmp_path):
    base = make_stub_modules()

    async def audit(claims, pack, ctx):
        return AuditResult(findings=[AuditFinding(claim_id=c.id, verdict=c.support_status, reason="no",
                                                  evidence_ids=list(c.evidence_ids),
                                                  blocking=c.id == "science.target_validation")
                                     for c in claims],
                           unresolved_critical_claim_ids=["science.target_validation"])
    env = Env(tmp_path, dataclasses.replace(base, audit_claims=audit))
    run = env.run()
    assert run.status == RunStatus.COMPLETED
    claim = next(c for c in env.repo.get_report(env.case_id, 1).claims if c.id == "science.target_validation")
    assert claim.support_status.value == "unverified"
    assert any("unverified" in w for w in run.warnings)


def test_invest_on_a_critical_unknown_is_rejected_by_validation(tmp_path):
    base = make_stub_modules()

    async def chair(results, audit, ctx):
        d = await base.synthesize_committee(results, audit, ctx)
        return d.model_copy(update={"recommendation": Recommendation.INVEST})
    env = Env(tmp_path, dataclasses.replace(base, synthesize_committee=chair))
    run = env.run()
    assert run.status == RunStatus.FAILED and run.error.code == "validation_failed"
    assert env.repo.get_report(env.case_id, 1) is None


def test_incomplete_chair_output_gets_one_repair_then_fails(tmp_path):
    base, seen = make_stub_modules(), []

    async def chair(results, audit, ctx):
        seen.append(list(ctx.feedback.get("chair", [])))
        d = await base.synthesize_committee(results, audit, ctx)
        return d.model_copy(update={"questions": d.questions[:3]})
    env = Env(tmp_path, dataclasses.replace(base, synthesize_committee=chair))
    run = env.run()
    assert run.error.code == "incomplete_committee_output" and len(seen) == 2 and seen[1]


def test_chair_repair_can_succeed(tmp_path):
    base, calls = make_stub_modules(), {"n": 0}

    async def chair(results, audit, ctx):
        calls["n"] += 1
        d = await base.synthesize_committee(results, audit, ctx)
        return d.model_copy(update={"questions": d.questions[:3]}) if calls["n"] == 1 else d
    env = Env(tmp_path, dataclasses.replace(base, synthesize_committee=chair))
    assert env.run().status == RunStatus.COMPLETED and calls["n"] == 2


def test_run_timeout(tmp_path):
    async def slow(case, pack, ctx):
        await asyncio.sleep(5)
    env = Env(tmp_path, dataclasses.replace(make_stub_modules(), analyze_science=slow), max_run_seconds=1)
    run = env.run()
    assert run.status == RunStatus.FAILED and run.error.code == "run_timeout" and run.error.retryable


def test_unconfigured_provider_fails_early_outside_dev_mode(tmp_path):
    env = Env(tmp_path, real_looking(), dev_stubs=False, llm_provider="placeholder")
    run = env.run()
    assert run.error.code == "provider_auth_error" and run.stage.value == "validate"


def test_missing_modules_fail_with_an_explained_error(tmp_path):
    env = Env(tmp_path)

    def not_ready():
        raise ModuleNotReady("Required functions are not available yet: analyze_science")
    run = env.run(modules_factory=not_ready)
    assert run.error.code == "module_not_ready" and "analyze_science" in run.error.message


def test_evidence_only_without_evidence_is_refused(tmp_path):
    env = Env(tmp_path, real_looking(), dev_stubs=False, llm_provider="anthropic")
    # no model call happens: the evidence check comes before the analysis
    run = env.run(mode=RunMode.EVIDENCE_ONLY)
    assert run.status == RunStatus.FAILED and run.error.code == "no_evidence"


def test_dev_stubs_reject_real_user_evidence(tmp_path):
    env = Env(tmp_path)
    env.repo.add_evidence(env.case_id, EvidenceCreate(title="Real", text="Real data", synthetic=False))
    assert env.run().error.code == "dev_stubs_requires_synthetic_evidence"


def test_as_of_date_drops_undated_evidence(tmp_path):
    env = Env(tmp_path)
    case = CASE.model_copy(update={"as_of_date": date(2030, 1, 1)})
    case_id = env.repo.create_case(case)
    env.repo.add_evidence(case_id, EvidenceCreate(title="Undated", text="No date", synthetic=True))
    run = env.run(case_id=case_id)
    assert run.status == RunStatus.COMPLETED
    report = env.repo.get_report(case_id, 1)
    assert all(s.title.startswith("[SYNTHETIC]") for s in report.sources)  # the undated note is out
    assert any("excluded" in w for w in run.warnings)


def test_synthetic_report_matches_fixture_shape(tmp_path):
    env = Env(tmp_path)
    env.run()
    report = env.repo.get_report(env.case_id, 1)
    assert {c.id for c in report.claims} == {c.id for c in synthetic.build_report(1).claims}

def test_stubs_are_refused_outside_dev_mode(tmp_path):
    env = Env(tmp_path, dev_stubs=False, llm_provider="anthropic")  # stub modules, no dev mode
    run = env.run()
    assert run.status == RunStatus.FAILED and run.error.code == "stubs_not_allowed"


def test_call_clinical_supports_both_signatures():
    async def contract_form(case, pack, scientific, ctx):
        return ("list", scientific)

    async def r4_form(case, pack, scientific_result, translation_result, ctx):
        return ("two", scientific_result, translation_result)
    assert asyncio.run(call_clinical(contract_form, 1, 2, "S", "T", 3)) == ("list", ["S", "T"])
    assert asyncio.run(call_clinical(r4_form, 1, 2, "S", "T", 3)) == ("two", "S", "T")


def test_partial_stub_mode_uses_the_real_agents_that_exist():
    settings = Settings(_env_file=None, dev_stubs=True,
                        stub_modules="build_evidence_pack,audit_claims,analyze_investment,synthesize_committee")
    mods = get_modules(settings)
    assert mods.origin["analyze_science"].startswith("vic.agents.science")
    assert mods.origin["analyze_market"].startswith("vic.agents.business")
    assert mods.origin["build_evidence_pack"] == "vic.stubs"


def test_unknown_stub_names_are_rejected():
    with pytest.raises(ModuleNotReady):
        get_modules(Settings(_env_file=None, dev_stubs=True, stub_modules="nonsense"))


def test_stub_chair_reuses_questions_and_filters_dangling_risk_claims():
    from vic.contracts import DiligenceQuestion, Risk, RoleId, RoleResult, SectionContent
    from vic.stubs import synthesize_committee
    q = DiligenceQuestion(question="Real question?", why_it_matters="w", evidence_needed="e",
                          decision_if_positive="p", decision_if_negative="n")
    role = RoleResult(
        role_id=RoleId.CLINICAL, summary="s", position="p",
        risks=[Risk(id="r1", description="d", priority="major", claim_ids=["gone.claim"],
                    impact="i", next_check="n")],
        section_content=[SectionContent(key="clinical_development_plan", summary="s",
                                        structured_data={"diligence_questions": [q.model_dump()]})])
    decision = asyncio.run(synthesize_committee([role], AuditResult(), None))
    assert decision.questions[0].question == "Real question?" and 5 <= len(decision.questions) <= 10
    assert decision.risks[0].claim_ids == [] and decision.recommendation == Recommendation.CONDITIONAL