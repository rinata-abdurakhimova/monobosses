from vic import integrity
from vic.contracts import Report
from vic.synthetic import build_all


def _data(name="report-v1"):
    return build_all()[name].model_dump(mode="json")


def _problems(data):
    return integrity.check_report(Report.model_validate(data))


def test_fixtures_are_valid():
    built = build_all()
    assert integrity.check_report(built["report-v1"]) == []
    assert integrity.check_report(built["report-v2"]) == []
    assert integrity.check_revision(built["report-v1"], built["report-v2"]) == []


def test_dangling_evidence():
    data = _data()
    data["claims"][0]["evidence_ids"] = ["ev-missing-99"]
    assert any("ev-missing-99" in p for p in _problems(data))


def test_dangling_claim_in_section():
    data = _data()
    data["sections"][1]["claim_ids"].append("science.nonexistent")
    assert any("science.nonexistent" in p for p in _problems(data))


def test_duplicate_claim_id():
    data = _data()
    data["claims"].append(data["claims"][0])
    assert any("duplicate claim id" in p for p in _problems(data))


def test_forbidden_id():
    data = _data()
    data["risks"][0]["id"] = "TBD"
    assert any("forbidden risk id" in p for p in _problems(data))


def test_recommendation_must_match_section():
    data = _data()
    data["sections"][0]["structured_data"]["recommendation"] = "Invest"
    assert any("does not match report.recommendation" in p for p in _problems(data))


def test_synthetic_report_rejects_real_source():
    data = _data()
    data["sources"][0]["synthetic"] = False
    assert any("non-synthetic" in p for p in _problems(data))


def test_invest_with_critical_unknown_is_rejected():
    data = _data()
    data["recommendation"] = "Invest"
    data["sections"][0]["structured_data"]["recommendation"] = "Invest"
    assert any("critical claim" in p for p in _problems(data))


def test_revision_checks():
    built = build_all()
    child = built["report-v2"].model_copy(deep=True)
    child.revision = child.revision.model_copy(update={"new_evidence_ids": []})
    assert integrity.check_revision(built["report-v1"], child)
    child = built["report-v2"].model_copy(deep=True)
    child.revision = child.revision.model_copy(update={"explanation": "Дані оновились."})
    assert any("cite" in p for p in integrity.check_revision(built["report-v1"], child))