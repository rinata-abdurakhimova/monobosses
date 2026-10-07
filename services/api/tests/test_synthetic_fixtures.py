import json
from pathlib import Path

from vic.contracts import Recommendation
from vic.synthetic import build_all

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures"


def test_committed_json_matches_generator():
    """Fails until you run: python scripts/generate_fixtures.py (and commit the result)."""
    for stem, model in build_all().items():
        path = FIXTURES / f"{stem}.json"
        assert path.exists(), f"{path} is missing; run scripts/generate_fixtures.py"
        assert json.loads(path.read_text(encoding="utf-8")) == model.model_dump(mode="json")


def test_generator_is_deterministic():
    a = {k: v.model_dump(mode="json") for k, v in build_all().items()}
    b = {k: v.model_dump(mode="json") for k, v in build_all().items()}
    assert a == b


def test_story_v1_conditional_v2_do_not_invest():
    built = build_all()
    v1, v2 = built["report-v1"], built["report-v2"]
    assert v1.recommendation == Recommendation.CONDITIONAL
    assert v2.recommendation == Recommendation.DO_NOT_INVEST
    assert len(v1.sections) == len(v2.sections) == 11
    assert 5 <= len(v1.diligence_questions) <= 10 and 5 <= len(v2.diligence_questions) <= 10
    assert v2.revision.parent_report_id == v1.id
    assert "ev-synthetic-07" in v2.revision.new_evidence_ids


def test_v1_unchanged_after_v2_is_built():
    before = build_all()["report-v1"].model_dump(mode="json")
    build_all()  # builds v2 again
    assert build_all()["report-v1"].model_dump(mode="json") == before


def test_contract_example_claim():
    claim = next(c for c in build_all()["report-v1"].claims if c.id == "translation.safe_exposure")
    assert claim.support_status.value == "unknown" and claim.importance.value == "critical"
    assert claim.provenance.value == "ai"


def test_run_fixtures():
    built = build_all()
    assert built["run-running"].status.value == "running"
    assert built["run-failed"].status.value == "failed"
    assert built["run-failed"].error.code == "run_interrupted"