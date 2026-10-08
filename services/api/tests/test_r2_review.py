"""Regression checks for R2 integration boundaries; no provider or network calls."""
import asyncio
import dataclasses
import io
import json
import runpy
import sys
from pathlib import Path

import pytest

from vic import synthetic
from vic.config import Settings
from vic.contracts import AuditResult, RunStatus
from vic.evidence.audit import audit_claims
from vic.main import check_production_settings
from vic.modules import call_audit, call_investment, compatible_signature, discover
from vic.stubs import make_stub_modules
from tests.test_pipeline import Env


def test_discovery_finds_real_auditor_and_investment():
    found = discover()
    assert any(fn is audit_claims for _, fn in found["audit_claims"])
    for name in ("audit_claims", "analyze_investment"):
        assert found[name] and compatible_signature(name, found[name][0][1])
    assert all(module != "vic.stubs" for items in found.values() for module, _ in items)


def test_r3_sync_audit_runs_through_r2_adapter():
    pack = synthetic.build_pack_v1()
    claims = synthetic.build_report(1).claims
    result = asyncio.run(call_audit(audit_claims, claims, pack, None))
    assert result == audit_claims(claims, pack)


def test_keyword_investment_receives_upstream_inputs():
    async def investment(case, pack, ctx, *, clinical=None, market=None):
        return case, pack, ctx, clinical, market
    assert asyncio.run(call_investment(investment, "case", "pack", "clinical", "market", "ctx")) == (
        "case", "pack", "ctx", "clinical", "market")


def test_pipeline_accepts_current_audit_and_investment_interfaces(tmp_path):
    base = make_stub_modules()
    seen = []

    def audit(claims, pack):
        seen.append("audit")
        return AuditResult()

    async def investment(case, pack, ctx, *, clinical=None, market=None):
        assert clinical.role_id.value == "clinical" and market.role_id.value == "market"
        seen.append("investment")
        return await base.analyze_investment(case, pack, clinical, market, ctx)

    env = Env(tmp_path, dataclasses.replace(base, audit_claims=audit, analyze_investment=investment))
    assert env.run().status == RunStatus.COMPLETED
    assert seen == ["investment", "audit"]


def test_chair_subset_preserves_all_specialist_risks(tmp_path):
    base = make_stub_modules()

    async def chair(results, audit, ctx):
        decision = await base.synthesize_committee(results, audit, ctx)
        return decision.model_copy(update={"risks": decision.risks[:1]})

    env = Env(tmp_path, dataclasses.replace(base, synthesize_committee=chair))
    assert env.run().status == RunStatus.COMPLETED
    report = env.repo.get_report(env.case_id, 1)
    assert {r.id for r in report.risks} == {r.id for role in report.roles for r in role.risks}


def test_conflicting_risk_records_fail_without_saving_report(tmp_path):
    base = make_stub_modules()

    async def chair(results, audit, ctx):
        decision = await base.synthesize_committee(results, audit, ctx)
        risk = decision.risks[0].model_copy(update={"description": "Conflicting description"})
        return decision.model_copy(update={"risks": [risk]})

    env = Env(tmp_path, dataclasses.replace(base, synthesize_committee=chair))
    run = env.run()
    assert run.status == RunStatus.FAILED and run.error.code == "risk_id_conflict"
    assert env.repo.get_report(env.case_id, 1) is None


def test_invalid_evidence_pack_fails_before_agents(tmp_path):
    base = make_stub_modules()

    async def retrieval(case, ctx):
        return synthetic.build_pack_v1().model_copy(update={"sources": []})

    env = Env(tmp_path, dataclasses.replace(base, build_evidence_pack=retrieval))
    run = env.run()
    assert run.status == RunStatus.FAILED and run.stage.value == "retrieve"
    assert run.error.code == "validation_failed"


def test_production_refuses_mock_backend():
    with pytest.raises(RuntimeError, match="RUN_BACKEND must be pipeline"):
        check_production_settings(Settings(_env_file=None, app_env="production",
                                          api_shared_secret="test-secret", run_backend="mock"))


@pytest.mark.parametrize("field,value", [("max_run_seconds", 0), ("max_concurrent_runs", 0),
    ("llm_max_retries", -1), ("llm_max_repairs", -1), ("run_backend", "typo"),
    ("app_env", "Production")])
def test_invalid_runtime_settings_are_rejected(field, value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})


def test_trace_script_prints_unicode_on_windows(monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "show_trace.py"
    namespace = runpy.run_path(str(script))
    trace = {"warnings": ["Синтетичні докази"], "status": "completed"}
    class Repo:
        def get_trace(self, run_id):
            assert run_id == "run-test"
            return trace
    namespace["main"].__globals__["get_repository"] = lambda: Repo()
    output = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", output)
    monkeypatch.setattr(sys, "argv", [str(script), "run-test"])
    assert namespace["main"]() == 0
    output.flush()
    assert json.loads(output.buffer.getvalue().decode("utf-8")) == trace
