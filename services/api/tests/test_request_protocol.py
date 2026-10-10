import copy
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, Field

from vic.request_protocol import (
    BriefGroup,
    ContextBrief,
    chair_audit_slice,
    chair_audit_table,
    compact_references,
    compact_schema,
    consolidate_note_table,
    context_aliases,
    context_records,
    expand_disposition_groups,
    fit_wire_context,
    grouped_chair_review_model,
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
    original = [f"ref{i}" for i in range(30)] + [f"ref{i}" for i in range(40, 50)]
    packed = compact_references(original, "refs")
    expanded = [f"ref{i}" for start, end in packed["alias_ranges"] for i in range(start, end + 1)]
    assert expanded == original


def test_compatible_context_aliases_compress_interleaved_claims_without_losing_ids():
    from vic.request_protocol import dumps

    claims = [{"id": f"market.claim_{i}", "scope": "approach",
               "support_status": "unknown" if i % 2 else "supported",
               "importance": "critical", "evidence_ids": ["e1"]} for i in range(300)]
    payload = {"upstream_context": {"market": {"claims": claims, "risks": []}}}
    original = copy.deepcopy(payload)
    mapping = context_aliases(payload)
    inverse = {alias: reference for reference, alias in mapping.items()}
    assert translate(translate(payload, mapping), inverse) == original
    assert set(mapping) == {"e1", *(claim["id"] for claim in claims)}
    supported = [claim["id"] for claim in claims if claim["support_status"] == "supported"]
    packed = compact_references(translate({"refs": supported}, mapping))["refs"]
    assert len(packed["alias_ranges"]) == 1
    decoded = [inverse[f"ref{i}"] for start, end in packed["alias_ranges"]
               for i in range(start, end + 1)]
    assert set(decoded) == set(supported)
    assert len(dumps(packed)) < len(dumps(supported))
    assert payload == original


def test_shared_text_does_not_mutate_input_or_change_content():
    sentence = "Candidate safety at efficacious exposure remains unverified."
    original = {"first": sentence, "second": sentence}
    before = copy.deepcopy(original)
    packed = shared_text(original)
    assert original == before
    assert packed["shared_texts"][packed["first"]["text_ref"]] == sentence
    assert packed["first"] == packed["second"]


@pytest.mark.asyncio
async def test_context_fit_refuses_request_without_room_for_compact_repair():
    from vic.contracts import RunContext
    from vic.failures import RunFailure
    from vic.llm import request_sizes, structured_request

    class Output(BaseModel):
        summary: str

    payload = {"exact_numeric_context": {"source_value": "preserve exact input"}}
    ctx = RunContext("case", "run", "snapshot", None, "evidence_only")
    _, system, messages = structured_request("investment", payload, Output, ctx,
        system_override="Analyze supplied evidence only.", compact=True)
    size = request_sizes(system, messages, model="test", max_tokens=4096)["request_bytes"]
    adapter = SimpleNamespace(_s=SimpleNamespace(node_initial_request_bytes=size,
        node_request_max_bytes=size + 100, llm_model="test", llm_max_output_tokens=4096),
        _reasoning_effort=lambda _: None)
    with pytest.raises(RunFailure, match="repair reserve"):
        await fit_wire_context(adapter, "investment", payload, Output, ctx,
                               "Analyze supplied evidence only.")


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


@pytest.mark.parametrize("text", ["Safety unknown. " * 1800, 'Невідомо 🧬 "\\\n' * 1800],
                         ids=["ascii", "unicode-escapes"])
def test_oversized_summary_review_preserves_every_character_position_and_role(text):
    from vic.request_protocol import briefing_payload, dumps

    payload = {"upstream_context": {"market": {"summary": text,
        "position": "insufficient_data", "claims": [], "risks": []}}}
    original = copy.deepcopy(payload)
    records, _ = context_records(payload)
    assert len(records) > 1
    assert "".join(record["data"]["summary"] for record in records) == text
    offset = 0
    for record in records:
        data = record["data"]
        assert record["role"] == "market" and record["kind"] == "summary"
        assert data["position"] == "insufficient_data"
        assert data["source_start"] == offset
        offset = data["source_end"]
        assert len(dumps(briefing_payload([record], 4500)).encode()) <= 10500
    assert offset == len(text)
    validate_brief(ContextBrief(groups=[BriefGroup(record_ids=[r["id"] for r in records],
                                                  summary="Unresolved safety")]), records)
    with pytest.raises(ValueError, match="omitted"):
        validate_brief(ContextBrief(groups=[BriefGroup(record_ids=[r["id"] for r in records[:-1]],
                                                      summary="Unresolved safety")]), records)
    assert payload == original


@pytest.mark.asyncio
async def test_summary_segments_fit_real_envelope_and_preserve_coverage_in_final_notes():
    import json

    from vic.config import Settings
    from vic.contracts import RunContext
    from vic.llm import ProviderResponse, StructuredLlm, request_sizes
    from vic.request_protocol import brief_context

    text = "Немає клінічного підтвердження; safety unknown. " * 600
    payload = {"upstream_context": {"market": {"summary": text,
        "position": "insufficient_data", "claims": [], "risks": []}}}
    received, sizes = [], []

    class Provider:
        async def complete(self, *, system, messages, **kwargs):
            sizes.append(request_sizes(system, messages, model="test", max_tokens=4096)["request_bytes"])
            request = json.loads(messages[0]["content"])
            received.extend(record for group in request["groups"].values() for record in group
                            if isinstance(record["data"], dict))
            return ProviderResponse(json.dumps({name: "Human efficacy and safety remain unknown."
                                    for name in request["groups"]}), None, None)

    ctx = RunContext("case", "run", "snapshot", None, "evidence_only")
    adapter = StructuredLlm(Provider(), Settings(_env_file=None, llm_model="test"))
    notes, numeric = await brief_context(adapter, payload, ctx, target_bytes=4500)
    received.sort(key=lambda record: record["data"]["source_start"])
    assert "".join(record["data"]["summary"] for record in received) == text
    assert len({record["id"] for record in received}) == len(received)
    assert sizes and max(sizes) <= 13500
    assert all(note["status"] == "insufficient_data" for note in notes["market"])
    assert numeric == [] and payload["upstream_context"]["market"]["summary"] == text


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


@pytest.mark.parametrize("field,wrong", [
    ("upstream_claim_ids", "investment.own_claim"),
    ("upstream_claim_ids", "partner_candidate"),
    ("upstream_claim_ids", "ip_licensing.upstream_claim"),
    ("record_ids", "partnerships.upstream_claim"),
    ("record_ids", "license_record"),
])
@pytest.mark.parametrize("node", ["investment", "investment_threshold"])
def test_investment_dependencies_keep_each_role_claim_and_record_namespace(node, field, wrong):
    inverse = {"ref0": "partnerships.upstream_claim", "ref1": "partner_candidate"}
    payload = {"context_dependency_ids": {"partnerships": {
        "upstream_claim_ids": {"alias_ranges": [[0, 0]]}, "record_ids": ["ref1"]}}}
    dependency = {"role_id": "partnerships", "upstream_claim_ids": [inverse["ref0"]],
                  "record_ids": [inverse["ref1"]]}
    validate_component_references(node, payload, dependency, inverse)
    validate_component_references(node, payload, {**dependency, "record_ids": []}, inverse)
    with pytest.raises(ValueError, match="context_dependency_ids"):
        validate_component_references(node, payload, {**dependency, field: [wrong]}, inverse)


def test_threshold_prospective_criterion_cannot_become_documented_from_an_unknown_claim():
    payload = {"frozen_components": {"claims": {"rows": [["ref1", "human_gate", "unknown"]]}}}
    inverse = {"ref1": "investment_threshold.human_gate"}
    finding = {"value": "Human safety and exposure meet a prespecified target", "basis": "hypothesis",
               "claim_ids": [inverse["ref1"]], "assumptions": ["Proposed target; no human results"],
               "unknowns": ["Human exposure and safety remain unestablished"]}
    validate_component_references("investment_threshold", payload, {"sufficient_result": finding}, inverse)
    with pytest.raises(ValueError, match="supported"):
        validate_component_references("investment_threshold", payload,
            {"sufficient_result": {**finding, "basis": "documented"}}, inverse)


def test_threshold_risk_cannot_reuse_a_claim_identity():
    payload = {"frozen_components": {"claims": {"rows": [["ref1", "human_gate", "unknown"]]}}}
    inverse = {"ref1": "investment_threshold.human_gate"}
    risk = {"id": "investment_threshold.risk_human_gate", "claim_ids": [inverse["ref1"]]}
    validate_component_references("investment_threshold", payload, {"risks": [risk]}, inverse)
    with pytest.raises(ValueError, match="never frozen claim IDs"):
        validate_component_references("investment_threshold", payload,
            {"risks": [{**risk, "id": inverse["ref1"]}]}, inverse)


def test_unknown_threshold_gate_cannot_have_a_hypothetical_achievement_assessment():
    payload = {"gate_components": {"status": "unknown"}, "frozen_components": {
        "claims": {"rows": [["ref1", "human_gate", "unknown"]]}}}
    inverse = {"ref1": "investment_threshold.human_gate"}
    assessment = {"basis": "unknown", "value": None, "claim_ids": [],
                  "assumptions": [], "unknowns": ["Human safety result unavailable"]}
    validate_component_references("investment_threshold", payload, {"assessment": assessment}, inverse)
    with pytest.raises(ValueError, match="status=unknown"):
        validate_component_references("investment_threshold", payload, {"assessment": {
            **assessment, "basis": "hypothesis", "value": "Possibly sufficient", "claim_ids": [inverse["ref1"]]}}, inverse)


def test_gate_rule_table_retains_exact_targets_claims_gap_scope_and_priority():
    from vic.request_protocol import gate_rule_context
    view = {"id": "next_stage", "horizon": "next_stage", "status": "unknown",
        "criteria": [{"id": "human_safety", "sufficient_result": {
            "value": "Prespecified human exposure and safety target, conditional on applicable evidence",
            "basis": "hypothesis", "claim_ids": ["ref5"]}}],
        "gaps": [{"id": "human_gap", "criterion_ids": ["human_safety"],
            "missing_result_or_data": "Animal benefit does not establish human safety", "priority": "critical"}],
        "existing_evidence": [{"criterion_id": "human_safety", "finding": {"basis": "unknown"}}]}
    original = copy.deepcopy(view)
    packed = gate_rule_context(view)
    criteria = [dict(zip(packed["criteria"]["columns"], row, strict=True)) for row in packed["criteria"]["rows"]]
    gaps = [dict(zip(packed["gaps"]["columns"], row, strict=True)) for row in packed["gaps"]["rows"]]
    assert criteria == [{"id": "human_safety", **view["criteria"][0]["sufficient_result"]}]
    assert gaps == view["gaps"]
    assert packed["status"] == "unknown"
    assert view == original


@pytest.mark.parametrize("field,wrong", [
    ("upstream_claim_ids", "clinical.risk_safety"),
    ("upstream_risk_ids", "clinical.safety"),
    ("record_ids", "absent_trial"),
])
def test_failure_origins_keep_claim_risk_record_namespaces(field, wrong):
    inverse = {"ref1": "clinical.safety", "ref2": "clinical.risk_safety", "ref3": "trial_record"}
    payload = {"origin_reference_ids": {"clinical": {
        "upstream_claim_ids": ["ref1"], "upstream_risk_ids": {"alias_ranges": [[2, 2]]},
        "record_ids": ["ref3"]}}}
    origin = {"role_id": "clinical", "upstream_claim_ids": [inverse["ref1"]],
              "upstream_risk_ids": [inverse["ref2"]], "record_ids": [inverse["ref3"]]}
    validate_component_references("failure_miner", payload, {"origins": [origin]}, inverse)
    with pytest.raises(ValueError, match="origin_reference_ids"):
        validate_component_references("failure_miner", payload, {"origins": [{**origin, field: [wrong]}]}, inverse)


def test_failure_unknown_findings_cannot_launder_claims_into_established_failures():
    payload = {"frozen_components": {"claims": {"rows": [["ref1", "human", "unknown"]]}}}
    inverse = {"ref1": "failure_miner.human"}
    finding = {"basis": "unknown", "value": None, "claim_ids": [], "assumptions": [],
               "unknowns": ["Human safety unavailable"]}
    validate_component_references("failure_miner", payload, {"problem": finding}, inverse)
    with pytest.raises(ValueError, match=r"claim_ids=\[\]"):
        validate_component_references("failure_miner", payload,
            {"problem": {**finding, "claim_ids": [inverse["ref1"]]}}, inverse)


def test_failure_interactions_require_real_endpoints_instead_of_claim_keys():
    inverse = {"ref1": "clinical_gap", "ref2": "translation_gap"}
    payload = {"frozen_components": {"record_descriptors": [
        {"id": alias, "component": "failure_modes"} for alias in inverse]}}
    link = {"id": "linked_gap", "from_failure_id": "clinical_gap", "to_failure_id": "translation_gap",
            "relationship": "shared_dependency"}
    validate_component_references("failure_miner", payload, {"interaction_blueprint": [link]}, inverse)
    with pytest.raises(ValueError, match="frozen collection"):
        validate_component_references("failure_miner", payload, {"interaction_blueprint": [
            {**link, "from_failure_id": "failure_miner.human"}]}, inverse)
    with pytest.raises(ValueError, match="distinct endpoints"):
        validate_component_references("failure_miner", payload, {"interaction_blueprint": [
            {**link, "to_failure_id": "clinical_gap"}]}, inverse)


def test_failure_review_cannot_defer_a_risk_already_linked_by_its_frozen_origin():
    inverse = {"ref1": "clinical.risk_safety", "ref2": "clinical_gap"}
    payload = {"review_role": "clinical", "review_items": [{"id": "ref1"}],
        "frozen_components": {"failure_modes": [{"id": "ref2", "domains": ["clinical"], "origins": [
            {"role_id": "clinical", "upstream_risk_ids": ["ref1"]}]}]}}
    disposition = {"upstream_risk_id": "clinical.risk_safety", "disposition": "included",
                   "failure_ids": ["clinical_gap"]}
    review = {"role_id": "clinical", "failure_ids": ["clinical_gap"], "risk_dispositions": [disposition]}
    validate_component_references("failure_miner", payload, review, inverse)
    with pytest.raises(ValueError, match="included with EVERY matching"):
        validate_component_references("failure_miner", payload, {**review, "risk_dispositions": [
            {**disposition, "disposition": "deferred", "failure_ids": []}]}, inverse)
    with pytest.raises(ValueError, match="EVERY review_items"):
        validate_component_references("failure_miner", payload, {**review, "risk_dispositions": []}, inverse)


def test_failure_diligence_cannot_drop_a_chain_or_rank_major_before_critical():
    inverse = {"ref1": "human_gap", "ref2": "budget_gap"}
    payload = {"frozen_components": {"record_descriptors": [
        {"id": alias, "component": "failure_modes"} for alias in inverse]}}
    questions = [{"rank": 1, "priority": "critical", "failure_ids": ["human_gap"], "interaction_ids": []},
                 {"rank": 2, "priority": "major", "failure_ids": ["budget_gap"], "interaction_ids": []}]
    validate_component_references("failure_miner", payload, {"diligence_priorities": questions}, inverse)
    with pytest.raises(ValueError, match="missing failure_ids"):
        validate_component_references("failure_miner", payload, {"diligence_priorities": questions[:1]}, inverse)
    with pytest.raises(ValueError, match="Critical diligence"):
        validate_component_references("failure_miner", payload, {"diligence_priorities": [
            {**questions[0], "priority": "major"}, {**questions[1], "priority": "critical"}]}, inverse)


def test_failure_interaction_question_must_cover_both_endpoints():
    inverse = {"ref1": "human_gap", "ref2": "budget_gap", "ref3": "shared_gap"}
    payload = {"frozen_components": {
        "record_descriptors": [{"id": alias, "component": "failure_modes"} for alias in ("ref1", "ref2")]
            + [{"id": "ref3", "component": "interactions"}],
        "interaction_links": [{"id": "ref3", "from_failure_id": "ref1", "to_failure_id": "ref2"}]}}
    question = {"rank": 1, "priority": "critical", "failure_ids": ["human_gap", "budget_gap"],
                "interaction_ids": ["shared_gap"]}
    validate_component_references("failure_miner", payload, {"diligence_priorities": [question]}, inverse)
    with pytest.raises(ValueError, match="BOTH endpoint"):
        validate_component_references("failure_miner", payload, {"diligence_priorities": [
            {**question, "failure_ids": ["human_gap"]},
            {"rank": 2, "priority": "major", "failure_ids": ["budget_gap"], "interaction_ids": []}]}, inverse)


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


@pytest.mark.parametrize("field", ["capital", "time"])
def test_investment_without_calculated_scenarios_rejects_placeholder_scenario_ids(field):
    payload = {"calculated_financials": {"scenarios": []}}
    validate_component_references("investment", payload, {field: {"scenario_ids": []}}, {})
    with pytest.raises(ValueError, match="not scenario IDs"):
        validate_component_references("investment", payload,
            {field: {"scenario_ids": ["delay", "human_development_decision"]}}, {})


def test_commercial_constraints_reject_non_market_dependencies_before_final_assembly():
    validate_component_references("investment", {},
        {"commercial_constraints": [{"role_id": "market"}]}, {})
    with pytest.raises(ValueError, match="EVERY"):
        validate_component_references("investment", {},
            {"commercial_constraints": [{"role_id": "market"}, {"role_id": "partnerships"}]}, {})


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


def test_sparse_references_keep_shorter_exact_list():
    original = ["ref0", "ref4", "ref7"]
    assert compact_references(original, "refs") == original


def test_chair_audit_table_retains_verdicts_evidence_blockers_and_warnings():
    audit = {"findings": [
        {"claim_id": "science.a", "verdict": "supported", "evidence_ids": ["ev1"], "blocking": False, "reason": "Confirmed"},
        {"claim_id": "market.b", "verdict": "unverified", "evidence_ids": ["ev1"], "blocking": True, "reason": "Absent clinical premise"},
        {"claim_id": "clinical.c", "verdict": "unknown", "evidence_ids": [], "blocking": False, "reason": "Gap"}],
        "warnings": ["synthetic evidence"], "unresolved_critical_claim_ids": ["market.b"]}
    before = copy.deepcopy(audit)
    wire = chair_audit_table(audit)
    decoded = [{"claim_id": cid, "verdict": wire["legends"]["verdict"][verdict],
                "evidence_ids": wire["legends"]["evidence_ids"][evidence], "blocking": blocking}
               for verdict, evidence, blocking, refs in wire["findings"] for cid in refs]
    assert decoded == [{k: f[k] for k in ("claim_id", "verdict", "evidence_ids", "blocking")} for f in audit["findings"]]
    assert wire["blocking_reasons"] == {"market.b": "Absent clinical premise"}
    assert wire["warnings"] == audit["warnings"]
    assert wire["unresolved_critical_claim_ids"] == audit["unresolved_critical_claim_ids"]
    assert audit == before


def test_note_consolidation_never_mixes_status_or_loses_references():
    table = {"columns": ["kind", "scope", "status", "priority", "refs", "summary"],
             "legends": {}, "roles": {"science": [
                 [1, 1, 2, 1, ["ref1"], "Mouse only"],
                 [1, 1, 2, 1, ["ref2"], "No humans"],
                 [1, 1, 3, 1, ["ref3"], "Conflicting signal"]], "clinical": None}}
    before = copy.deepcopy(table)
    result = consolidate_note_table(table)
    assert result["roles"]["science"] == [
        [1, 1, 2, 1, ["ref1", "ref2"], "Mouse only; No humans"],
        [1, 1, 3, 1, ["ref3"], "Conflicting signal"]]
    assert result["roles"]["clinical"] is None
    assert table == before


def test_chair_wire_claim_alias_decodes_exactly():
    audit = {"findings": [{"claim_id": "ref123", "verdict": "unverified", "evidence_ids": [],
                          "blocking": True, "reason": "Human safety unknown"}],
             "warnings": [], "unresolved_critical_claim_ids": ["ref123"]}
    wire = chair_audit_table(audit)
    assert wire["findings"] == [[0, 0, True, ["ref123"]]]
    assert wire["blocking_reasons"] == {"ref123": "Human safety unknown"}


def test_chair_question_cannot_change_frozen_links_or_rank():
    plan = {"id": "planned", "rank": 1, "role_ids": ["market"], "risk_ids": ["ref1"]}
    payload = {"requested_question_plan": plan}
    good = {**plan, "risk_ids": ["chair_risk"], "question": "Verify commercial premise?"}
    validate_component_references("chair", payload, good, {"ref1": "chair_risk"})
    for change in ({"rank": 2}, {"risk_ids": []}, {"role_ids": ["clinical"]}, {"id": "invented"}):
        with pytest.raises(ValueError, match="frozen question"):
            validate_component_references("chair", payload, {**good, **change}, {"ref1": "chair_risk"})


def test_chair_documented_reason_rejects_unknown_own_and_audit_downgraded_claims():
    payload = {"frozen_components": {"claims": {"rows": [["ref1", "", "unknown"], ["ref2", "", "supported"]]}},
               "audit": {"unresolved_critical_claim_ids": ["ref2"]}}
    reason = {"basis": "documented", "claim_ids": ["chair.gap"], "unknowns": [], "assumptions": []}
    inverse = {"ref1": "chair.gap", "ref2": "market.blocked"}
    for cid in ("chair.gap", "market.blocked"):
        with pytest.raises(ValueError, match="supported unblocked"):
            validate_component_references("chair", payload, {"rationale": {**reason, "claim_ids": [cid]}}, inverse)
    validate_component_references("chair", payload,
        {"rationale": {"basis": "unknown", "claim_ids": [], "unknowns": ["Human safety absent"]}}, inverse)


def test_chair_unknown_claim_requires_gap_assumptions_before_acceptance():
    with pytest.raises(ValueError, match="assumptions"):
        validate_component_references("chair", {},
            {"claims": [{"support_status": "unknown", "assumptions": []}]}, {})


def test_chair_audit_reasons_follow_claim_and_risk_inventory_with_exact_aliases():
    raw = {"claims": [{"id": "market.a"}, {"id": "market.b"}],
           "risks": [{"claim_ids": ["market.b"]}]}
    audit = {"findings": [
        {"claim_id": "market.a", "verdict": "supported", "reason": "Animal report", "evidence_ids": ["ev1"], "blocking": False},
        {"claim_id": "market.b", "verdict": "unverified", "reason": "Human benefit absent", "evidence_ids": ["ev1"], "blocking": True}], "warnings": ["synthetic"]}
    mapping = {"market.a": "ref1", "market.b": "ref2", "ev1": "ref3"}
    first = chair_audit_slice(audit, raw, [{"id": "market/claims/0"}], mapping)
    risk = chair_audit_slice(audit, raw, [{"id": "market/risks/0"}], mapping)
    assert first["findings"] == [["ref1", "supported", "Animal report", ["ref3"], False]]
    assert risk["findings"] == [["ref2", "unverified", "Human benefit absent", ["ref3"], True]]
    assert first["warnings"] == risk["warnings"] == ["synthetic"]
    assert chair_audit_slice(audit, raw, [{"id": "market/unknowns/0"}], mapping)["findings"] == []


def test_chair_domain_review_requires_exact_coverage_and_valid_decision_links():
    payload = {"review_role": "market", "review_items": [{"id": "ref1"}],
               "frozen_components": {"arguments": [{"id": "ref2"}], "questions": [], "conditions": []}}
    inverse = {"ref1": "market/unknowns/0", "ref2": "market_gate"}
    disposition = {"item_id": "market/unknowns/0", "disposition": "considered", "rationale": "Blocks diligence",
                   "argument_ids": ["market_gate"], "question_ids": [], "condition_ids": []}
    data = {"role_id": "market", "assessment": {"basis": "unknown", "claim_ids": [], "unknowns": ["Missing inputs"]},
            "dispositions": [disposition]}
    validate_component_references("chair", payload, data, inverse)
    for invalid in ({"dispositions": []}, {"role_id": "clinical"},
                    {"dispositions": [disposition, disposition]},
                    {"dispositions": [{**disposition, "argument_ids": ["invented"]}]},
                    {"dispositions": [{**disposition, "disposition": "deferred"}]}):
        with pytest.raises(ValueError):
            validate_component_references("chair", payload, {**data, **invalid}, inverse)


def test_grouped_chair_dispositions_expand_without_changing_rationale_or_links():
    from vic.agents.business.chair import DomainReview
    grouped = grouped_chair_review_model(DomainReview)
    raw = {"role_id": "market", "assessment": {"text": "Inputs missing", "basis": "unknown", "claim_ids": [],
            "assumptions": [], "unknowns": ["Pricing absent"], "evidence_weight": "No market evidence"},
           "dispositions": [{"item_ids": ["market/unknowns/0", "market/unknowns/1"], "disposition": "deferred",
             "rationale": "Missing underlying inputs", "argument_ids": [], "question_ids": [], "condition_ids": []}]}
    wire = grouped.model_validate(raw).model_dump(mode="json")
    canonical = DomainReview.model_validate({**wire, "dispositions": expand_disposition_groups(wire["dispositions"])})
    assert [d.item_id for d in canonical.dispositions] == ["market/unknowns/0", "market/unknowns/1"]
    assert all(d.rationale == "Missing underlying inputs" and not d.argument_ids for d in canonical.dispositions)
    payload = {"grouped_dispositions": True, "review_role": "market", "review_items": [{"id": d.item_id} for d in canonical.dispositions],
               "frozen_components": {"arguments": [], "questions": [], "conditions": []}}
    validate_component_references("chair", payload, wire, {})
    broken = copy.deepcopy(wire); broken["dispositions"][0]["item_ids"] *= 2
    with pytest.raises(ValueError, match="exactly once"):
        validate_component_references("chair", payload, broken, {})


def test_chair_conflict_requires_claims_from_every_named_role():
    view = {"legends": {"kind": ["claim"], "status": ["supported"]},
            "roles": {"science": [[0, 0, 0, 0, ["ref1"], "signal"]],
                      "market": [[0, 0, 0, 0, ["ref2"], "readiness"]]}}
    payload = {"upstream_context": view}
    good = {"role_ids": ["science", "market"], "upstream_claim_ids": ["science.signal", "market.ready"]}
    inverse = {"ref1": "science.signal", "ref2": "market.ready"}
    validate_component_references("chair", payload, {"conflicts": [good]}, inverse)
    with pytest.raises(ValueError, match="each listed role"):
        validate_component_references("chair", payload, {"conflicts": [{**good, "role_ids": ["science", "investment"]}]}, inverse)
    with pytest.raises(ValueError, match="listed roles"):
        validate_component_references("chair", payload, {"conflicts": [{**good, "upstream_claim_ids": [*good["upstream_claim_ids"], "clinical.other"]}]}, inverse)


def test_chair_change_trigger_must_change_frozen_recommendation():
    payload = {"frozen_components": {"recommendation": "Conditional"}}
    with pytest.raises(ValueError, match="different"):
        validate_component_references("chair", payload, {"change_triggers": [{"resulting_recommendation": "Conditional"}]}, {})
    validate_component_references("chair", payload, {"change_triggers": [{"resulting_recommendation": "Invest"}]}, {})
    # Missing fields are handled by schema validation rather than KeyError.
    validate_component_references("chair", payload, {"change_triggers": [{}]}, {})


def test_ip_missing_identifier_is_a_gap_before_accepting_component():
    with pytest.raises(ValueError, match="documented publication_number"):
        validate_component_references("ip_licensing", {}, {"patents": [{"publication_number": {"basis": "unknown"}}]}, {})
    with pytest.raises(ValueError, match="documented rights_granted"):
        validate_component_references("ip_licensing", {}, {"rights_and_licenses": [{"rights_granted": {"basis": "hypothesis"}}]}, {})


@pytest.mark.parametrize("basis", ["documented", "hypothesis"])
def test_ip_non_unknown_findings_require_own_claims_before_component_acceptance(basis):
    payload = {"frozen_components": {"claims": {"rows": [
        ["ref0", "Source observation", "supported"],
        ["ref1", "Proposed work", "unverified"]]}}}
    inverse = {"ref0": "ip_licensing.source", "ref1": "ip_licensing.proposal"}
    finding = {"basis": basis, "value": "Potential option", "claim_ids": [],
               "assumptions": ["Unverified proposal"], "unknowns": ["Agreement absent"]}
    with pytest.raises(ValueError, match="nonempty"):
        validate_component_references("ip_licensing", payload, {"finding": finding}, inverse)
    claim = "ip_licensing.source" if basis == "documented" else "ip_licensing.proposal"
    validate_component_references("ip_licensing", payload,
                                  {"finding": {**finding, "claim_ids": [claim]}}, inverse)
    wrong = "ip_licensing.proposal" if basis == "documented" else "ip_licensing.source"
    with pytest.raises(ValueError) as error:
        validate_component_references("ip_licensing", payload,
                                      {"finding": {**finding, "claim_ids": [wrong]}}, inverse)
    if basis == "hypothesis":
        assert '"ref1"' in str(error.value)
        assert "ip_licensing.proposal" not in str(error.value)


def test_ip_position_cannot_claim_barriers_without_frozen_identified_barriers():
    payload = {"frozen_components": {"fto_decision": {"status": "unresolved", "barrier_ids": []}}}
    with pytest.raises(ValueError, match="requires identified barriers"):
        validate_component_references("ip_licensing", payload, {"position": "potential_barriers"}, {})
    validate_component_references("ip_licensing", payload, {"position": "insufficient_data"}, {})
    payload["frozen_components"]["fto_decision"] = {"status": "potential_barriers",
                                                      "barrier_ids": ["ip_barrier"]}
    validate_component_references("ip_licensing", payload, {"position": "potential_barriers"}, {})


@pytest.mark.parametrize("count,status", [(0, "supported"), (1, "unverified")])
def test_ip_documented_coverage_requires_records_and_supported_own_claims(count, status):
    payload = {"frozen_components": {"ip_coverage_counts": {"patents": count},
               "claims": {"rows": [["ref0", "patent", status]]}}}
    finding = {"status": "documented", "claim_ids": ["ip_licensing.patent"], "unknowns": []}
    with pytest.raises(ValueError, match="existing entries"):
        validate_component_references("ip_licensing", payload, {"coverage": {"patents": finding}},
                                      {"ref0": "ip_licensing.patent"})
    finding.update(status="insufficient_data", claim_ids=[], unknowns=["Patent record absent"])
    validate_component_references("ip_licensing", payload, {"coverage": {"patents": finding}}, {})


def test_unwrapped_investment_time_keeps_scenario_and_numeric_validation():
    payload = {"single_investment_component": "time", "calculated_financials": {"scenarios": []}}
    finding = {"basis": "unknown", "value": None, "claim_ids": [],
               "unknowns": ["Duration absent"], "assumptions": []}
    data = {"scheduling_basis": finding, "scenario_ids": [], "dependencies": [finding],
            "possible_delays": [finding], "missing_inputs": ["Schedule missing"]}
    validate_component_references("investment", payload, data, {})
    with pytest.raises(ValueError, match="scenario_ids"):
        validate_component_references("investment", payload, {**data, "scenario_ids": ["invented"]}, {})
    with pytest.raises(ValueError, match="Numeric literals"):
        validate_component_references("investment", payload, {**data, "missing_inputs": ["Delay 12 months"]}, {})


def test_compressed_dependency_catalog_keeps_claim_and_record_namespaces_exact():
    inverse = {f"ref{i}": f"market.claim_{i}" for i in range(100)}
    inverse.update({f"ref{i}": f"market_record_{i}" for i in range(100, 200)})
    payload = {"context_dependency_ids": {"market": {
        "upstream_claim_ids": [f"ref{i}" for i in range(100)],
        "record_ids": [f"ref{i}" for i in range(100, 200)]}}}
    packed = compact_references(payload)
    assert packed["context_dependency_ids"]["market"]["upstream_claim_ids"] == {"alias_ranges": [[0, 99]]}
    assert packed["context_dependency_ids"]["market"]["record_ids"] == {"alias_ranges": [[100, 199]]}
    valid = {"dependency": {"role_id": "market", "upstream_claim_ids": ["market.claim_99"],
                            "record_ids": ["market_record_199"]}}
    validate_component_references("investment", packed, valid, inverse)
    for field, wrong in (("record_ids", "market.claim_99"), ("upstream_claim_ids", "market_record_199")):
        broken = copy.deepcopy(valid)
        broken["dependency"][field] = [wrong]
        with pytest.raises(ValueError, match="never own claims or other record types"):
            validate_component_references("investment", packed, broken, inverse)
