"""HTTP integration with every real node and adapter; deterministic provider, no paid calls."""
import json
import sys
import time
from contextvars import ContextVar
from pathlib import Path

from vic.config import Settings
from vic.contracts import Report
from vic.llm import ProviderResponse, StructuredLlm, _compact_schema
from vic.storage import get_repository
from tests.conftest import new_client

BUSINESS = Path(__file__).parent / "vic" / "agents" / "business"
sys.path.insert(0, str(BUSINESS))
from test_chair import output as chair_output
from test_failure_miner import output as failure_output
from test_investment import plan_output, explanation_output
from test_investment_threshold import output as threshold_output
from test_ip_licensing import fixture as ip_fixture
from test_market import fixture as market_fixture
from test_partnerships import output as partnerships_output
from tests.vic.agents.science.test_translation import _analysis as translation_output
from tests.vic.agents.science.test_clinical import _clinical_analysis as clinical_output

CURRENT = ContextVar("structured_request")


def response(prompt_id, payload):
    if prompt_id == "science":
        return dict(thesis="Synthetic mechanism remains uncertain", position="weak", claims=[],
            supporting_arguments=[], opposing_arguments=[], risks=[], unknowns=["Human relevance unknown"],
            change_conditions=["Reviewed human data"], limitations=["Synthetic integration test"])
    if prompt_id == "translation":
        return translation_output().model_dump(mode="json")
    if prompt_id == "clinical":
        raw = clinical_output().model_dump(mode="json")
        # Preserve an honestly missing statistical basis rather than importing another fixture's facts.
        raw["trial_size"] = dict(has_basis=False, estimate=None, assumptions=[],
            statistical_design_gap="Reviewed effect size required", evidence_ids=[])
        raw["claims"] = []
        raw["risks"] = []
        raw["historical_analogues"] = []
        return raw
    if prompt_id == "market":
        return market_fixture()[2]
    if prompt_id == "ip_licensing":
        return ip_fixture()[2]
    if prompt_id == "partnerships":
        return partnerships_output()
    if prompt_id == "investment_plan":
        return plan_output()
    if prompt_id == "investment":
        return explanation_output()
    if prompt_id == "investment_threshold":
        return threshold_output()
    if prompt_id == "failure_miner":
        raw = failure_output()
        for review in raw["domain_reviews"]:
            upstream = payload["upstream_context"][review["role_id"]]
            review["risk_dispositions"] = [dict(upstream_risk_id=risk["id"], disposition="deferred",
                failure_ids=[], rationale="Synthetic integration example: requires manual review")
                for risk in upstream["risks"]]
        return raw
    if prompt_id == "chair":
        raw = chair_output()
        for review in raw["domain_reviews"]:
            review["dispositions"] = [dict(item_id=item["id"], disposition="considered",
                rationale="Requires diligence", argument_ids=["gap"], question_ids=[], condition_ids=[])
                for item in payload["input_inventory"][review["role_id"]]]
        return raw
    if prompt_id == "audit":
        import re
        return dict(verdicts=[dict(claim_id=id_, verdict="supported", reason="Synthetic comparator excerpt matches",
            population="unclear", candidate_match="class_level", evidence_type="descriptive", polarity="unclear")
            for id_ in re.findall(r"^CLAIM (\S+)", payload["audit_items"], flags=re.MULTILINE)])
    raise AssertionError(prompt_id)


class Provider:
    name = "deterministic-integration"

    async def complete(self, *, system, messages, **kwargs):
        prompt_id, payload = CURRENT.get()
        assert "JSON Schema" in system
        assert json.loads(messages[0]["content"]) == json.loads(json.dumps(payload, default=str))
        return ProviderResponse(json.dumps(response(prompt_id, payload)), 100, 50)


class Model(StructuredLlm):
    def __init__(self):
        super().__init__(Provider(), Settings(_env_file=None))
        self.calls = []

    async def generate_structured(self, prompt_id, payload, response_model, ctx):
        self.calls.append((prompt_id, payload))
        token = CURRENT.set((prompt_id, payload))
        try:
            return await super().generate_structured(prompt_id, payload, response_model, ctx)
        finally:
            CURRENT.reset(token)


def test_http_runs_all_real_nodes_and_preserves_rich_results(tmp_path, monkeypatch):
    from vic import runner
    model = Model()
    monkeypatch.setenv("RUN_BACKEND", "pipeline")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("DEV_STUBS", "false")
    monkeypatch.setattr(runner, "build_llm", lambda settings: model)
    with new_client() as client:
        case = market_fixture()[0].model_dump(mode="json")
        cid = client.post("/cases", json=case).json()["case_id"]
        repo = get_repository()
        from vic.evidence.importer import ImportResult
        from datetime import datetime, timezone
        repo.add_import(cid, ImportResult(market_fixture()[1], [], datetime.now(timezone.utc)))
        rid = client.post(f"/cases/{cid}/runs", json={"mode": "evidence_only"}).json()["run_id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            run = client.get(f"/runs/{rid}").json()
            if run["status"] in ("failed", "completed"):
                break
            time.sleep(.02)
        assert run["status"] == "completed", run.get("error")
        report = Report.model_validate(client.get(f"/cases/{cid}/reports/1").json())
        assert {r.role_id.value for r in report.roles} == {
            "science", "translation", "clinical", "market", "investment", "ip_licensing",
            "partnerships", "investment_threshold", "failure_miner", "chair", "audit"}
        assert len(report.sections) == 11
        payloads = dict(model.calls)
        assert all(payloads["chair"]["context_availability"].values())
        assert payloads["investment_plan"]["upstream_context"]["partnerships"] is not None
        assert payloads["investment_plan"]["upstream_context"]["ip_licensing"] is not None
        chair = next(r for r in report.roles if r.role_id == "chair")
        assert chair.section_content[0].structured_data["chair"]["committee_decision"]["recommendation"] == report.recommendation
        assert repo.get_trace(rid)["prompt_versions"]["chair"]
        # Reopening reads the persisted result; no new generation call.
        count = len(model.calls)
        assert client.get(f"/cases/{cid}/reports/1").json()["run_id"] == rid
        assert len(model.calls) == count
        (tmp_path / "integrated-report.json").write_text(report.model_dump_json(), encoding="utf-8")
        # A dated text import does not start a run; an explicit full rerun keeps v1 immutable.
        imported = client.post(f"/cases/{cid}/evidence", json={"title": "Unrelated synthetic update",
            "text": "Synthetic administrative contact update; no change to scientific evidence.",
            "synthetic": True, "published_at": "2026-10-08"}).json()
        second_id = client.post(f"/cases/{cid}/runs", json={"mode": "evidence_only",
            "parent_report_id": report.id}).json()["run_id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            second_run = client.get(f"/runs/{second_id}").json()
            if second_run["status"] in ("failed", "completed"):
                break
            time.sleep(.02)
        assert second_run["status"] == "completed", second_run.get("error")
        second = Report.model_validate(client.get(f"/cases/{cid}/reports/2").json())
        assert second.recommendation == report.recommendation
        assert second.revision.parent_report_id == report.id
        assert set(imported["evidence_ids"]) <= set(second.revision.new_evidence_ids)
        assert client.get(f"/cases/{cid}/reports/1").json() == report.model_dump(mode="json")
        from vic.storage import SqliteRepository
        reopened = SqliteRepository(repo.path, seed=False)
        assert reopened.get_report(cid, 1) == report and reopened.get_report(cid, 2) == second


def test_evaluation_runner_keeps_labels_out_of_model_input(tmp_path, monkeypatch):
    import importlib.util
    import asyncio
    spec = importlib.util.spec_from_file_location("evaluation_runner", Path(__file__).resolve().parents[3] / "evals" / "run.py")
    evaluation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluation)
    model = Model()
    monkeypatch.setattr(evaluation, "build_llm", lambda settings: model)
    case, pack, _ = market_fixture()
    manifest = {"cases": [dict(id="first", family="synthetic-one", split="development",
        input=case.model_dump(mode="json"), pack=pack.model_dump(mode="json"),
        expectations={"SECRET_EVALUATOR_LABEL": "never send this"})]}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    results = asyncio.run(evaluation.evaluate(path, tmp_path / "results",
        Settings(_env_file=None, llm_provider="openai", dev_stubs=False)))
    assert results[0]["status"] == "completed"
    assert "SECRET_EVALUATOR_LABEL" not in json.dumps(model.calls)
    folder = next((tmp_path / "results").iterdir())
    assert (folder / "first" / "snapshot.json").exists()
    assert (folder / "first" / "report.json").exists()
    assert (folder / "first" / "trace.json").exists()
    invalid = {"cases": [manifest["cases"][0], manifest["cases"][0] | {"id": "second", "split": "holdout"}]}
    import pytest
    with pytest.raises(ValueError, match="same split"):
        evaluation.validate_manifest(invalid)


def test_compacted_schema_preserves_title_fields_and_validation_constraints():
    from vic.contracts import Source
    compact = _compact_schema(Source.model_json_schema())
    assert "title" in compact["properties"] and "title" in compact["required"]
    assert compact["properties"]["content_hash"]["pattern"]


def test_audit_repairs_expand_to_every_dependent_node():
    from vic.pipeline import _expand
    from vic.contracts import RoleId
    assert _expand({RoleId.SCIENCE}) == set(RoleId) - {RoleId.TRANSLATION, RoleId.CHAIR, RoleId.AUDIT}
    assert _expand({RoleId.PARTNERSHIPS}) == {RoleId.PARTNERSHIPS, RoleId.INVESTMENT,
                                           RoleId.INVESTMENT_THRESHOLD, RoleId.FAILURE_MINER}
