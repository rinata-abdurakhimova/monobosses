import copy
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field
from vic.request_protocol import (
    BriefGroup,
    ContextBrief,
    compact_references,
    compact_schema,
    context_records,
    fit_wire_context,
    numeric_table,
    shared_text,
    translate,
    validate_brief,
    validate_component_references,
)


def test_aliases_restore_references_without_changing_text_enums_or_field_names():
    data = {"scope": "program", "role_id": "science", "text": "claim.original",
            "claims": [{"id": "claim.original", "evidence_ids": ["evidence.original"]}]}
    mapping = {"program": "ref0", "science": "ref1", "claim.original": "ref2", "evidence.original": "ref3"}
    wire = translate(data, mapping)
    assert wire["scope"] == "program" and wire["role_id"] == "science"
    assert wire["text"] == "claim.original"
    assert wire["claims"][0]["id"] == "ref2"
    assert translate(wire, {v: k for k, v in mapping.items()}) == data


@pytest.mark.parametrize("defect", ["omitted", "duplicated", "scope", "status", "priority"])
def test_context_brief_cannot_drop_or_mix_incompatible_records(defect):
    records = [{"id": i, "role": "clinical", "kind": "claim", "scope": "program",
                "status": "contradicted", "priority": "critical"} for i in range(2)]
    members = [0, 1]
    if defect == "omitted":
        members = [0]
    elif defect == "duplicated":
        members = [0, 0, 1]
    else:
        records[1][defect] = {"scope": "approach", "status": "supported", "priority": "minor"}[defect]
    with pytest.raises(ValueError):
        validate_brief(ContextBrief(groups=[BriefGroup(record_ids=members, summary="Safety concern")]), records)


def test_numeric_locators_and_values_are_lossless():
    records = [{"path": "investment.plan.costs[2].amount", "value": "1234.50"},
               {"path": "clinical.trial_size.has_basis", "value": False}]
    packed = numeric_table(records)
    decoded = [{"path": "".join(packed["path_tokens"][i] for i in path), "value": value}
               for path, value in packed["rows"]]
    assert decoded == records


def test_reference_ranges_cover_exact_aliases():
    original = ["ref0", "ref1", "ref4", "ref7", "ref8"]
    packed = compact_references(original, "refs")
    expanded = [f"ref{i}" for start, end in packed["alias_ranges"] for i in range(start, end + 1)]
    assert expanded == original


def test_shared_text_does_not_mutate_input_or_change_content():
    sentence = "Candidate safety at efficacious exposure remains unverified."
    original = {"first": sentence, "second": sentence}
    before = copy.deepcopy(original)
    packed = shared_text(original)
    assert original == before
    assert packed["shared_texts"][packed["first"]["text_ref"]] == sentence
    assert packed["first"] == packed["second"]


def test_compact_schema_retains_required_properties_constraints_and_descriptions():
    class Output(BaseModel):
        title: str = Field(min_length=1, description="Evidence-backed title")
        number: int = Field(ge=1, le=10)
    rendered = compact_schema(Output.model_json_schema())
    assert "title:" in rendered and "title?:" not in rendered
    assert "Evidence-backed title" in rendered
    assert '"minLength":1' in rendered
    assert '"minimum":1' in rendered and '"maximum":10' in rendered


def test_context_records_preserve_finding_basis_and_critical_negative_scope():
    payload = {"upstream_context": {"clinical": {"summary": "Unknown", "position": "insufficient_data",
        "claims": [{"id": "clinical.safety", "text": "Dose-limiting liver toxicity", "scope": "program",
                    "support_status": "contradicted", "importance": "critical", "evidence_ids": ["e1"]}],
        "risks": [], "unknowns": ["Long-term risk unknown"], "change_conditions": [],
        "section_content": [{"key": "clinical_development_plan", "limitations": [],
                              "structured_data": {"finding": {"basis": "hypothesis", "value": "Not demonstrated"}}}]}}}
    records, _ = context_records(payload)
    negative = next(r for r in records if r["kind"] == "claim")
    assert (negative["scope"], negative["status"], negative["priority"]) == ("program", "contradicted", "critical")
    finding = next(r for r in records if r["kind"] == "record")
    assert finding["status"] == "hypothesis"
    assert finding["data"]["record"] == {"basis": "hypothesis", "value": "Not demonstrated"}


def test_large_partner_record_is_split_without_losing_identity_or_fields():
    fields = {f"finding_{i}": {"basis": "unknown", "value": None, "claim_ids": [],
              "assumptions": [], "unknowns": [f"Gap {i}: " + "Source detail; " * 60]} for i in range(12)}
    payload = {"upstream_context": {"partnerships": {"summary": "Partner unverified", "position": "insufficient_data",
        "claims": [], "risks": [], "unknowns": [], "section_content": [{"key": "commercial_opportunity",
        "structured_data": {"candidates": [{"id": "partner_test", "kind": "category", **fields}]}}]}}}
    original = copy.deepcopy(payload)
    records, _ = context_records(payload)
    own = [record for record in records if record["kind"] == "record"]
    assert any(record["data"]["record"].get("id") == "partner_test" and record["refs"] == ["partner_test"] for record in own)
    for key, finding in fields.items():
        assert any(record["data"]["path"].endswith("." + key) and record["data"]["record"] == finding for record in own)
    assert payload == original


def test_reference_labels_are_not_quantities_and_duplicate_gaps_remain_once():
    gap = "Human evidence unknown; R4 review pending (ref1)."
    raw = {"summary": "Fixed plan", "position": "fixed", "claims": [], "risks": [], "unknowns": [gap],
           "section_content": [{"key": "capital_to_milestone", "structured_data": {
               "unknowns": [gap], "review": "R4 review required (ref1)", "dose": "Dose 12 mg; R4 review pending"}}]}
    records, numeric = context_records({"upstream_context": {"fixed_plan": raw}})
    assert [record["data"] for record in records if record["kind"] == "unknowns"] == [gap]
    assert [record["value"] for record in numeric] == ["Dose 12 mg; R4 review pending"]
    assert any(record.get("data", {}).get("value") == "R4 review required (ref1)"
               for record in records if isinstance(record.get("data"), dict))


@pytest.mark.parametrize("role", ["ip_licensing", "partnerships"])
def test_business_components_cannot_confuse_evidence_and_claim_references(role):
    claim_id = role + ".safety"
    inverse = {"ref0": "ev-original", "ref1": claim_id}
    payload = {"evidence": [{"id": "ref0"}], "frozen_components": {
        "claims": {"rows": [["ref1", "safety", "unknown"]]}, "record_descriptors": []}}
    valid = {"finding": {"claim_ids": [claim_id]}}
    validate_component_references(role, payload, valid, inverse)
    with pytest.raises(ValueError, match="claim_ids"):
        validate_component_references(role, payload, {"finding": {"claim_ids": ["ev-original"]}}, inverse)
    with pytest.raises(ValueError, match="evidence_ids"):
        validate_component_references(role, payload, {"claims": [{"evidence_ids": [claim_id]}]}, inverse)


def test_partnership_hypothesis_cannot_omit_its_claim_or_become_documented():
    payload = {"evidence": [], "frozen_components": {"claims": {
        "rows": [["ref1", "fit", "unverified"]]}, "record_descriptors": []}}
    inverse = {"ref1": "partnerships.fit"}
    finding = {"value": "Possible category fit", "basis": "hypothesis",
               "claim_ids": ["partnerships.fit"], "assumptions": ["Category hypothesis only"], "unknowns": []}
    validate_component_references("partnerships", payload, {"finding": finding}, inverse)
    for bad in ({**finding, "claim_ids": []}, {**finding, "basis": "documented"}):
        with pytest.raises(ValueError):
            validate_component_references("partnerships", payload, {"finding": bad}, inverse)


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_budget", [6500, 2500])
async def test_context_byte_fit_keeps_every_reference_and_metadata_row(initial_budget):
    class Output(BaseModel):
        summary: str
    premise = "Human safety unknown; mouse benefit does not prove patient benefit. "
    rows = [[0, 0, 0, 0, [f"ref{i}"], premise * 6] for i in range(20)]
    payload = {"upstream_context": {"columns": ["kind", "scope", "status", "priority", "refs", "summary"],
               "legends": {"kind": ["claim"], "scope": ["program"], "status": ["unknown"],
                           "priority": ["critical"]}, "roles": {"clinical": rows}},
               "exact_numeric_context": {"dose": None}, "wire_protocol": {"canonical_hash": "immutable"}}
    original = copy.deepcopy(payload)
    async def summarize(prompt_id, request, model, ctx, **kwargs):
        return model.model_validate({note["key"]: "Human safety unknown; animal benefit is not patient benefit."
                                     for note in request["notes"]})
    from vic.contracts import RunContext
    ctx = RunContext("case", "run", "snapshot", None, "evidence_only")
    adapter = SimpleNamespace(_s=SimpleNamespace(node_initial_request_bytes=initial_budget,
        node_request_max_bytes=8000, llm_model="test", llm_max_output_tokens=4096),
        _reasoning_effort=lambda _: None, _generate_direct=summarize)
    fitted = await fit_wire_context(adapter, "partnerships", payload, Output, ctx, "Analyze supplied evidence only.")
    assert payload == original
    assert [row[:-1] for row in fitted["upstream_context"]["roles"]["clinical"]] == [row[:-1] for row in rows]
    assert fitted["upstream_context"]["legends"] == original["upstream_context"]["legends"]
    assert fitted["exact_numeric_context"] == original["exact_numeric_context"]
    assert fitted["wire_protocol"] == original["wire_protocol"]
    from vic.llm import request_sizes, structured_request
    _, system, messages = structured_request("partnerships", fitted, Output, ctx,
        system_override="Analyze supplied evidence only.", compact=True)
    assert request_sizes(system, messages, model="test")["request_bytes"] <= 8000
