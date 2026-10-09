"""R4-03 paired before/after checks against evaluator-only expectations.

Simulated model outputs are hand-written per phase; they verify the harness, the code-level
evidence guards and that the expectations are falsifiable. They are not a live-model result.
"""
import json
import re
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from vic.agents.science.clinical import ClinicalPlanAnalysis, analyze_clinical
from vic.agents.science.scientific import ScientificAnalysis, analyze_science
from vic.agents.science.translation import (
    TRANSLATION_LINKS,
    TranslationAnalysis,
    analyze_translation,
)
from vic.contracts import CaseInput, EvidencePack, RoleResult, RunContext

MANIFEST_PATH = (
    Path(__file__).resolve().parents[6] / "evals" / "cases" / "r4_paired_manifest.json"
)
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
FAMILIES = {family["family_id"]: family for family in MANIFEST["families"]}
PAIR_A = "pair_a_negative_candidate_hepatotoxicity"
PAIR_B = "pair_b_positive_target_engagement"
PAIR_C = "pair_c_irrelevant_other_candidate"
CLAIM_ID = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")

# ------------------------------------------------------------------ simulated model outputs
_A_BEFORE = {
    "science": {
        "science.genetic_evidence": ("supported", ["ev-a-genetics"]),
        "science.pathway_biology": ("supported", ["ev-a-pathway"]),
        "science.target_validation": ("supported", ["ev-a-genetics", "ev-a-pathway"]),
        "science.prior_programs": ("supported", ["ev-a-class"]),
    },
    "links": {"translation.molecular_effect": ("established", ["ev-a-pathway"])},
    "extra": {
        "translation.safe_exposure": ("unknown", []),
        "translation.therapeutic_window": ("unknown", []),
    },
    "clinical": {
        "clinical.target_population": ("supported", ["ev-a-class"]),
        "clinical.safety_requirements": ("mixed", ["ev-a-preclin-tox"]),
        "clinical.next_milestone": ("mixed", ["ev-a-class", "ev-a-preclin-tox"]),
    },
    "risks": {
        "science": ["science.risk.jak_selectivity"],
        "translation": ["translation.risk.exposure_margin"],
        "clinical": ["clinical.risk.safety", "clinical.risk.competitive_bar"],
    },
}
_A_AFTER = deepcopy(_A_BEFORE)
_A_AFTER["links"]["translation.human_exposure"] = (
    "partially_established", ["ev-a-ph1-hepatotox"]
)
_A_AFTER["extra"] = {
    "translation.safe_exposure": ("contradicted", ["ev-a-ph1-hepatotox"]),
    "translation.therapeutic_window": (
        "contradicted", ["ev-a-ph1-hepatotox", "ev-a-ph1-metabolite"]
    ),
}
_A_AFTER["clinical"]["clinical.safety_requirements"] = (
    "contradicted", ["ev-a-ph1-hepatotox", "ev-a-ph1-metabolite"]
)
_A_AFTER["clinical"]["clinical.next_milestone"] = (
    "mixed", ["ev-a-ph1-hepatotox", "ev-a-ph1-metabolite"]
)

_B_BEFORE = {
    "science": {
        "science.pathway_biology": ("supported", ["ev-b-mechanism"]),
        "science.animal_model_evidence": ("supported", ["ev-b-pizmouse"]),
        "science.target_validation": ("mixed", ["ev-b-mechanism", "ev-b-pizmouse"]),
    },
    "links": {"translation.molecular_effect": ("established", ["ev-b-pizmouse"])},
    "extra": {},  # safe_exposure omitted on purpose: the agent must add it as unknown
    "clinical": {
        "clinical.target_population": ("supported", ["ev-b-mechanism"]),
        "clinical.biomarker_strategy": ("unverified", []),
        "clinical.safety_requirements": ("unknown", []),
    },
    "risks": {
        "science": ["science.risk.fibrosis_reversibility"],
        "translation": ["translation.risk.lung_protection"],
        "clinical": ["clinical.risk.safety", "clinical.risk.surrogate_endpoint"],
    },
}
_B_AFTER = deepcopy(_B_BEFORE)
_B_AFTER["links"]["translation.target_engagement"] = ("established", ["ev-b-ph1-pd"])
_B_AFTER["links"]["translation.biological_response"] = (
    "partially_established", ["ev-b-ph1-pd"]
)
_B_AFTER["clinical"]["clinical.biomarker_strategy"] = ("supported", ["ev-b-ph1-pd"])
_B_AFTER["clinical"]["clinical.safety_requirements"] = ("mixed", ["ev-b-ph1-safety"])

_C_BEFORE = {
    "science": {
        "science.expression_relevance": ("supported", ["ev-c-bal"]),
        "science.causal_vs_correlative": ("mixed", ["ev-c-bal", "ev-c-knockout"]),
        "science.perturbation_data": ("supported", ["ev-c-knockout"]),
        "science.prior_programs": ("supported", ["ev-c-ph2"]),
        "science.target_validation": ("mixed", ["ev-c-knockout", "ev-c-ph2"]),
    },
    "links": {
        "translation.molecular_effect": ("established", ["ev-c-knockout"]),
        "translation.patient_benefit": ("partially_established", ["ev-c-ph2"]),
    },
    "extra": {"translation.safe_exposure": ("unknown", [])},
    "clinical": {
        "clinical.target_population": ("supported", ["ev-c-ph2"]),
        "clinical.primary_endpoint": ("supported", ["ev-c-ph2"]),
        "clinical.next_milestone": ("mixed", ["ev-c-ph2"]),
    },
    "risks": {
        "science": ["science.risk.redundant_fibrotic_pathways"],
        "translation": ["translation.risk.exposure_unknown"],
        "clinical": ["clinical.risk.safety", "clinical.risk.endpoint_variability"],
    },
}
_C_AFTER = deepcopy(_C_BEFORE)

SIMULATED = {
    PAIR_A: {"before": _A_BEFORE, "after": _A_AFTER},
    PAIR_B: {"before": _B_BEFORE, "after": _B_AFTER},
    PAIR_C: {"before": _C_BEFORE, "after": _C_AFTER},
}


def _risks(ids: list[str]) -> list[dict]:
    return [
        {
            "id": risk_id,
            "description": f"Simulated risk {risk_id}.",
            "priority": "major",
            "related_claim_keys": [],
            "impact": "Affects the investment thesis.",
            "next_check": "Review in diligence.",
        }
        for risk_id in ids
    ]


def _responses(spec: dict, scope: str) -> dict:
    science = ScientificAnalysis(
        thesis="Simulated scientific thesis.",
        position="moderate",
        claims=[
            {
                "key": key,
                "text": f"{key} assessment.",
                "support_status": status,
                "evidence_ids": ids,
                "assumptions": [],
                "scope": scope,
                "importance": "critical",
                "reasoning": "Simulated reasoning.",
            }
            for key, (status, ids) in spec["science"].items()
        ],
        supporting_arguments=[],
        opposing_arguments=[],
        risks=_risks(spec["risks"]["science"]),
        unknowns=[],
        change_conditions=[],
        limitations=[],
    )
    translation = TranslationAnalysis(
        thesis="Simulated translation thesis.",
        position="moderate",
        links=[
            {
                "key": key,
                "status": spec["links"].get(key, ("gap", []))[0],
                "text": f"{key} assessment.",
                "evidence_ids": spec["links"].get(key, ("gap", []))[1],
                "evidence_summary": "Simulated summary.",
                "gaps": [] if key in spec["links"] else [f"{key}: no human data."],
                "limitations": [],
                "assumptions": [],
                "scope": scope,
                "importance": "critical",
            }
            for key in TRANSLATION_LINKS
        ],
        additional_claims=[
            {
                "key": key,
                "text": f"{key} assessment.",
                "support_status": status,
                "evidence_ids": ids,
                "assumptions": [],
                "scope": scope,
                "importance": "critical",
            }
            for key, (status, ids) in spec["extra"].items()
        ],
        barriers=[],
        risks=_risks(spec["risks"]["translation"]),
        unknowns=[],
        change_conditions=[],
        data_needed=[],
        limitations=[],
    )
    clinical = ClinicalPlanAnalysis(
        thesis="Simulated clinical thesis.",
        position="conditionally_feasible",
        target_population="Simulated population.",
        clinically_meaningful_outcome="Simulated outcome.",
        primary_endpoint="Simulated endpoint.",
        comparator="Placebo.",
        biomarker_strategy="Simulated biomarker strategy.",
        trial_size={"has_basis": False, "estimate": None, "assumptions": [], "evidence_ids": []},
        study_sequence=[],
        regulatory_context="Context only; not a guarantee of approval.",
        next_milestone="Simulated milestone.",
        standard_of_care="Simulated standard of care.",
        unmet_need="Simulated unmet need.",
        claims=[
            {
                "key": key,
                "text": f"{key} assessment.",
                "support_status": status,
                "evidence_ids": ids,
                "assumptions": [],
                "scope": scope,
                "importance": "critical",
                "reasoning": "Simulated reasoning.",
            }
            for key, (status, ids) in spec["clinical"].items()
        ],
        risks=_risks(spec["risks"]["clinical"]),
        unknowns=[],
        change_conditions=[],
        limitations=[],
        science_gaps_carried_forward=[],
    )
    return {"science": science, "translation": translation, "clinical": clinical}


# ------------------------------------------------------------------ harness
def build_pack(family: dict, phase: str) -> EvidencePack:
    before = family["before"]
    sources, evidence = list(before["sources"]), list(before["evidence"])
    snapshot_id = before["snapshot_id"]
    if phase == "after":
        sources += family["after"]["added_sources"]
        evidence += family["after"]["added_evidence"]
        snapshot_id = family["after"]["snapshot_id"]
    return EvidencePack(sources=sources, evidence=evidence, snapshot_id=snapshot_id, synthetic=True)


async def run_phase(
    family: dict, phase: str, spec: dict
) -> tuple[dict[str, RoleResult], list[dict]]:
    case = CaseInput(**family["case"])
    pack = build_pack(family, phase)
    responses = _responses(spec, family["case"]["scope"])
    generate = AsyncMock(side_effect=lambda prompt_id, payload, model, ctx: responses[prompt_id])
    ctx = RunContext(
        case_id=family["family_id"],
        run_id=f"{family['family_id']}-{phase}",
        snapshot_id=pack.snapshot_id,
        as_of_date=None,
        mode="evidence_only",
        model=type("SimulatedAdapter", (), {"generate_structured": generate})(),
    )
    science = await analyze_science(case, pack, ctx)
    translation = await analyze_translation(case, pack, ctx)
    clinical = await analyze_clinical(case, pack, science, translation, ctx)
    payloads = [call.args[1] for call in generate.await_args_list]
    return {"science": science, "translation": translation, "clinical": clinical}, payloads


async def run_pair(family_id: str, after_spec: dict | None = None):
    family = FAMILIES[family_id]
    before, before_payloads = await run_phase(family, "before", SIMULATED[family_id]["before"])
    after, after_payloads = await run_phase(
        family, "after", after_spec or SIMULATED[family_id]["after"]
    )
    return family, before, after, before_payloads, after_payloads


def _claims(results: dict[str, RoleResult]) -> dict:
    return {claim.id: claim for result in results.values() for claim in result.claims}


def _status(claims: dict, claim_id: str) -> str | None:
    claim = claims.get(claim_id)
    return claim.support_status.value if claim else None


def _risk_ids(results: dict[str, RoleResult]) -> set[str]:
    return {risk.id for result in results.values() for risk in result.risks}


def evaluate_pair(expect: dict, before: dict, after: dict) -> list[str]:
    errors: list[str] = []
    b, a = _claims(before), _claims(after)
    changed = {item["claim_id"]: item for item in expect["changed_claims"]}
    unchanged = expect["unchanged_claims"]
    tolerated = expect["tolerated_claims"]

    for claim_id, item in changed.items():
        if _status(b, claim_id) != item["before_status"]:
            errors.append(f"{claim_id}: before={_status(b, claim_id)} expected {item['before_status']}")
        if _status(a, claim_id) != item["after_status"]:
            errors.append(f"{claim_id}: after={_status(a, claim_id)} expected {item['after_status']}")
        cited = set(a[claim_id].evidence_ids) if claim_id in a else set()
        missing = set(item["required_evidence_ids"]) - cited
        if missing:
            errors.append(f"{claim_id}: changed premise lacks evidence {sorted(missing)}")

    for claim_id, status in unchanged.items():
        for phase, claims in (("before", b), ("after", a)):
            if _status(claims, claim_id) != status:
                errors.append(f"{claim_id}: {phase}={_status(claims, claim_id)} expected {status}")

    for claim_id, allowed in tolerated.items():
        if claim_id in a and _status(a, claim_id) not in allowed:
            errors.append(f"{claim_id}: after={_status(a, claim_id)} outside tolerated {allowed}")

    for claim_id in sorted((b.keys() | a.keys()) - changed.keys() - unchanged.keys() - tolerated.keys()):
        if (claim_id in b) != (claim_id in a):
            errors.append(f"{claim_id}: claim appeared or disappeared without expectation")
        elif _status(b, claim_id) != _status(a, claim_id):
            errors.append(
                f"{claim_id}: unexpected change {_status(b, claim_id)} -> {_status(a, claim_id)}"
            )

    for claim_id in sorted(b.keys() & a.keys()):
        if b[claim_id].scope != a[claim_id].scope:
            errors.append(f"{claim_id}: scope drifted {b[claim_id].scope} -> {a[claim_id].scope}")

    for rule in expect["forbidden_citations"]:
        for claim_id, claim in a.items():
            if claim_id.startswith(rule["claim_prefix"]) and rule["evidence_id"] in claim.evidence_ids:
                errors.append(f"{claim_id}: cites out-of-subject evidence {rule['evidence_id']}")

    for phase, results in (("before", before), ("after", after)):
        for risk_id in sorted(set(expect["unchanged_risks"]) - _risk_ids(results)):
            errors.append(f"{risk_id}: risk missing {phase}")

    links = after["translation"].section_content[0].structured_data["translation_links"]
    for key in expect["missing_links_preserved"]:
        if links[key]["status"] not in {"gap", "unknown"}:
            errors.append(f"{key}: missing link closed without expectation ({links[key]['status']})")
    return errors


def _evaluator_texts(expect: dict) -> list[str]:
    texts = [item["changed_premise"] for item in expect["changed_claims"]]
    for values in expect["r5_handoff"].values():
        texts.extend(values)
    return texts


# ------------------------------------------------------------------ manifest integrity
def test_manifest_is_team_reviewed_and_covers_three_kinds():
    assert MANIFEST["label_status"] == "team-reviewed"
    assert "Not an external expert assessment" in MANIFEST["label_note"]
    assert MANIFEST["evaluator_only_fields"] == ["expectations"]
    assert sorted(family["kind"] for family in FAMILIES.values()) == [
        "irrelevant", "negative", "positive"
    ]


@pytest.mark.parametrize("family_id", list(FAMILIES))
def test_manifest_packs_and_expectations_are_well_formed(family_id):
    family = FAMILIES[family_id]
    expect = family["expectations"]
    before, after = build_pack(family, "before"), build_pack(family, "after")
    new_ids = {ev.id for ev in after.evidence} - {ev.id for ev in before.evidence}

    assert before.snapshot_id != after.snapshot_id
    assert new_ids == {ev["id"] for ev in family["after"]["added_evidence"]}
    assert CaseInput(**family["case"]).scope.value == expect["case_scope"]
    for item in expect["changed_claims"]:
        assert CLAIM_ID.match(item["claim_id"])
        assert set(item["required_evidence_ids"]) <= new_ids, "a decisive change must cite new evidence"
    declared = [item["claim_id"] for item in expect["changed_claims"]]
    declared += list(expect["unchanged_claims"]) + list(expect["tolerated_claims"])
    assert len(declared) == len(set(declared)), "a claim may have only one expectation"
    assert set(expect["missing_links_preserved"]) <= set(TRANSLATION_LINKS)


# ------------------------------------------------------------------ paired behaviour
@pytest.mark.asyncio
@pytest.mark.parametrize("family_id", list(FAMILIES))
async def test_expectations_never_reach_model_payload(family_id):
    family, _, _, before_payloads, after_payloads = await run_pair(family_id)
    new_ids = [ev["id"] for ev in family["after"]["added_evidence"]]

    for payload in before_payloads + after_payloads:
        serialized = json.dumps(payload, default=str)
        assert "expectations" not in payload
        for text in _evaluator_texts(family["expectations"]):
            assert text not in serialized
    for payload in before_payloads:
        assert not any(f"[{eid}]" in payload["evidence_items"] for eid in new_ids)
    for payload in after_payloads:
        assert all(f"[{eid}]" in payload["evidence_items"] for eid in new_ids)


@pytest.mark.asyncio
@pytest.mark.parametrize("family_id", list(FAMILIES))
async def test_paired_update_matches_expectations(family_id):
    family, before, after, _, _ = await run_pair(family_id)
    assert evaluate_pair(family["expectations"], before, after) == []


@pytest.mark.asyncio
async def test_negative_candidate_result_preserves_mechanism():
    family, before, after, _, _ = await run_pair(PAIR_A)
    b, a = _claims(before), _claims(after)

    for claim_id in (cid for cid in b if cid.startswith("science.")):
        assert a[claim_id].support_status == b[claim_id].support_status
        assert a[claim_id].evidence_ids == b[claim_id].evidence_ids
    assert a["translation.safe_exposure"].support_status == "contradicted"
    assert "ev-a-ph1-hepatotox" in a["translation.safe_exposure"].evidence_ids
    assert a["clinical.safety_requirements"].support_status == "contradicted"
    assert a["translation.patient_benefit"].support_status == "unknown"
    assert set(family["expectations"]["unchanged_risks"]) <= _risk_ids(after)


@pytest.mark.asyncio
async def test_positive_engagement_does_not_erase_long_term_safety_risks():
    family, before, after, _, _ = await run_pair(PAIR_B)
    a = _claims(after)
    unchanged_risks = family["expectations"]["unchanged_risks"]

    assert "clinical.risk.safety" in unchanged_risks
    assert "translation.risk.lung_protection" in unchanged_risks
    assert set(unchanged_risks) <= _risk_ids(before) & _risk_ids(after)
    assert a["translation.target_engagement"].support_status == "supported"
    assert a["translation.safe_exposure"].support_status == "unknown"
    assert a["translation.safe_exposure"].evidence_ids == []
    assert a["translation.patient_benefit"].support_status == "unknown"


@pytest.mark.asyncio
async def test_irrelevant_document_creates_no_science_change():
    family, before, after, _, _ = await run_pair(PAIR_C)
    b, a = _claims(before), _claims(after)
    off_subject = {ev["id"] for ev in family["after"]["added_evidence"]}

    assert b.keys() == a.keys()
    for claim_id in b:
        assert (a[claim_id].support_status, a[claim_id].evidence_ids, a[claim_id].scope) == (
            b[claim_id].support_status, b[claim_id].evidence_ids, b[claim_id].scope
        )
        assert not off_subject & set(a[claim_id].evidence_ids)
    assert {claim.scope.value for claim in a.values()} == {"approach"}


@pytest.mark.asyncio
async def test_invented_citation_cannot_create_artificial_translation_change():
    spec = deepcopy(_C_AFTER)
    spec["links"]["translation.target_engagement"] = ("established", ["ev-invented"])
    family, before, after, _, _ = await run_pair(PAIR_C, spec)

    assert _claims(after)["translation.target_engagement"].support_status == "unknown"
    assert evaluate_pair(family["expectations"], before, after) == []


# ------------------------------------------------------------------ expectations are falsifiable
def _mechanism_wipe():
    spec = deepcopy(_A_AFTER)
    spec["science"]["science.pathway_biology"] = ("contradicted", ["ev-a-ph1-hepatotox"])
    return spec


def _safety_risk_dropped():
    spec = deepcopy(_B_AFTER)
    spec["risks"]["clinical"] = ["clinical.risk.surrogate_endpoint"]
    return spec


def _safety_declared_proven():
    spec = deepcopy(_B_AFTER)
    spec["extra"]["translation.safe_exposure"] = ("supported", ["ev-b-ph1-safety"])
    return spec


def _benefit_from_biomarker():
    spec = deepcopy(_B_AFTER)
    spec["links"]["translation.patient_benefit"] = ("established", ["ev-b-ph1-pd"])
    return spec


def _irrelevant_doc_cited():
    spec = deepcopy(_C_AFTER)
    spec["science"]["science.target_validation"] = ("contradicted", ["ev-c-pde4b"])
    return spec


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("family_id", "mutate", "expected_error"),
    [
        (PAIR_A, _mechanism_wipe, "science.pathway_biology"),
        (PAIR_B, _safety_risk_dropped, "clinical.risk.safety: risk missing after"),
        (PAIR_B, _safety_declared_proven, "translation.safe_exposure: after=supported"),
        (PAIR_B, _benefit_from_biomarker, "translation.patient_benefit"),
        (PAIR_C, _irrelevant_doc_cited, "cites out-of-subject evidence ev-c-pde4b"),
    ],
)
async def test_evaluator_flags_biologically_invalid_updates(family_id, mutate, expected_error):
    family, before, after, _, _ = await run_pair(family_id, mutate())
    errors = evaluate_pair(family["expectations"], before, after)
    assert any(expected_error in error for error in errors), errors
