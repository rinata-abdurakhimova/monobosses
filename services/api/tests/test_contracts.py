import pytest
from pydantic import ValidationError

from vic.contracts import CaseInput, Claim, Recommendation, Report, SectionKey
from vic.synthetic import build_all


def _report_data(name="report-v1"):
    return build_all()[name].model_dump(mode="json")


def test_recommendation_values_are_exact():
    assert {r.value for r in Recommendation} == {"Invest", "Conditional", "Do Not Invest"}


def test_eleven_section_keys_in_order():
    assert [k.value for k in SectionKey] == [
        "recommendation", "scientific_thesis", "human_translation_thesis",
        "clinical_development_plan", "competitive_landscape", "commercial_opportunity",
        "capital_to_milestone", "key_risks", "critical_unknowns", "diligence_questions", "sources"]


def test_case_input_approach_ok():
    assert CaseInput(indication="X", mechanism="Y", scope="approach").program_data is None


@pytest.mark.parametrize("data", [
    {},
    {"indication": "  ", "mechanism": "Y", "scope": "approach"},
    {"indication": "X", "mechanism": "Y", "scope": "program"},
    {"indication": "X", "mechanism": "Y", "scope": "program", "program_data": "short"},
    {"indication": "X", "mechanism": "Y", "scope": "approach", "unknown_field": 1},
    {"indication": "X", "mechanism": "Y", "scope": "other"},
])
def test_case_input_invalid(data):
    with pytest.raises(ValidationError):
        CaseInput(**data)


def test_source_claim_requires_evidence():
    with pytest.raises(ValidationError):
        Claim(id="a.b", text="t", provenance="source", support_status="unknown",
              evidence_ids=[], scope="approach", importance="minor")


def test_supported_claim_requires_evidence():
    with pytest.raises(ValidationError):
        Claim(id="a.b", text="t", provenance="ai", support_status="supported",
              evidence_ids=[], scope="approach", importance="minor")


def test_report_roundtrip():
    for name in ("report-v1", "report-v2"):
        assert Report.model_validate(_report_data(name)).version in (1, 2)


def test_report_needs_11_sections():
    data = _report_data()
    data["sections"] = data["sections"][:10]
    with pytest.raises(ValidationError):
        Report.model_validate(data)


@pytest.mark.parametrize("count", [4, 11])
def test_report_questions_between_5_and_10(count):
    data = _report_data()
    data["diligence_questions"] = (data["diligence_questions"] * 2)[:count]
    with pytest.raises(ValidationError):
        Report.model_validate(data)


def test_v2_requires_revision_and_v1_forbids_it():
    data = _report_data("report-v2")
    data["revision"] = None
    with pytest.raises(ValidationError):
        Report.model_validate(data)
    data = _report_data("report-v1")
    data["revision"] = _report_data("report-v2")["revision"]
    with pytest.raises(ValidationError):
        Report.model_validate(data)