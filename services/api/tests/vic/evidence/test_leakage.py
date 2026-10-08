import asyncio
from datetime import date, datetime

from vic.contracts import RunContext, RunMode, Source
from vic.evidence import fixtures
from vic.evidence.importer import build_pack, parse_text
from vic.evidence.leakage import (
    BlindGuess,
    anonymize_pack,
    assess_temporal,
    blind_identity_guess,
    build_leakage_report,
    evaluate_blind_guess,
    scan_blind_pack,
)

TEXT = (
    "# Results\n\n"
    "Acmedrug lowered marker M by 40% in 120 patients (NCT01234567, PMID 1234567).\n\n"
    "# Notes\n\n"
    "Full report: https://example.org/acmedrug-trial and doi 10.1000/abc.123 by Acme Bio."
)
TERMS = ["Acmedrug", "Acme Bio"]


def _pack():
    doc = parse_text("Acmedrug phase 2 trial", TEXT, identifier="NCT01234567", published_at="2022-03-01")
    pack = build_pack([doc]).pack
    src = pack.sources[0].model_copy(update={"url": "https://clinicaltrials.gov/study/NCT01234567"})
    return pack.model_copy(update={"sources": [src]})


def _src(stype="peer_reviewed", published=date(2020, 1, 1), sid="src-1"):
    return Source(id=sid, title="t", url=None, type=stype, published_at=published,
                  retrieved_at=datetime(2025, 1, 1), content_hash="sha256:" + "0" * 64, synthetic=True)


def test_anonymize_masks_names_ids_and_urls_and_rekeys_everything():
    blind = anonymize_pack(_pack(), TERMS)
    dump = blind.pack.model_dump_json()
    for secret in ["Acmedrug", "Acme Bio", "NCT01234567", "1234567", "example.org", "10.1000", "clinicaltrials.gov"]:
        assert secret.lower() not in dump.lower(), secret
    assert blind.pack.sources[0].url is None and blind.pack.sources[0].document_id is None
    assert blind.pack.sources[0].id == "blind-src-01" and blind.pack.evidence[0].id == "blind-ev-001"
    assert blind.pack.sources[0].title == "Source 01 (user_upload)"
    assert "[NAME_A]" in " ".join(e.excerpt for e in blind.pack.evidence)
    assert blind.pack.snapshot_id.startswith("snap-blind-")


def test_mapping_is_kept_separately_and_covers_all_ids():
    original = _pack()
    blind = anonymize_pack(original, TERMS)
    assert set(blind.mapping.evidence_ids) == {e.id for e in original.evidence}
    assert set(blind.mapping.source_ids) == {s.id for s in original.sources}
    assert blind.mapping.original_titles["blind-src-01"] == "Acmedrug phase 2 trial"
    assert "original_titles" not in blind.pack.model_dump_json()  # mapping is not part of the pack


def test_scan_finds_leaks_in_a_raw_pack_and_none_in_a_properly_blinded_one():
    raw = scan_blind_pack(_pack(), TERMS)
    assert {"identity_term", "direct_id"} <= {f.kind for f in raw}
    blind = anonymize_pack(_pack(), TERMS)
    clean = [f for f in scan_blind_pack(blind.pack, TERMS) if f.kind != "possible_code"]
    assert clean == []


def test_known_failure_incomplete_identity_list_is_flagged_not_hidden():
    base = fixtures.build_baseline_pack().pack
    blind = anonymize_pack(base, ["X-001", "SYN-1"])  # forgot that the text also says "SYN1"
    findings = scan_blind_pack(blind.pack, ["X-001", "SYN-1"])
    assert any(f.kind == "possible_code" and f.detail.upper() == "SYN1" for f in findings)
    report = build_leakage_report(identity_findings=findings,
                                  temporal=assess_temporal([], as_of=date(2021, 1, 1)),
                                  guess=None, method="rule-based masking")
    assert report["overall"] != "controlled_as_tested"


def test_allow_terms_keep_the_mechanism_from_being_flagged():
    base = fixtures.build_baseline_pack().pack
    blind = anonymize_pack(base, ["X-001", "SYN-1"])
    findings = scan_blind_pack(blind.pack, ["X-001", "SYN-1"], allow_terms=["SYN1"])
    assert not any(f.detail.upper() == "SYN1" for f in findings)


def test_temporal_controlled_only_with_documented_cutoff_and_later_outcome():
    ok = assess_temporal([_src()], as_of=date(2021, 1, 1), model_cutoff=date(2023, 6, 1),
                         cutoff_documented=True, outcome_date=date(2024, 1, 1))
    assert ok.control_level == "controlled" and ok.flags == []


def test_temporal_hard_failures_and_uncertainties():
    assert assess_temporal([_src()], as_of=None).control_level == "uncontrolled"
    late = assess_temporal([_src(published=date(2022, 1, 1))], as_of=date(2021, 1, 1),
                           model_cutoff=date(2023, 6, 1), cutoff_documented=True, outcome_date=date(2024, 1, 1))
    assert late.control_level == "uncontrolled" and any("after_as_of" in f for f in late.flags)
    nocut = assess_temporal([_src()], as_of=date(2021, 1, 1), outcome_date=date(2024, 1, 1))
    assert nocut.control_level == "partially_controlled" and any("not documented" in f for f in nocut.flags)
    before = assess_temporal([_src()], as_of=date(2021, 1, 1), model_cutoff=date(2023, 6, 1),
                             cutoff_documented=True, outcome_date=date(2022, 1, 1))
    assert before.control_level == "partially_controlled" and any("may have seen" in f for f in before.flags)
    reg = assess_temporal([_src("registry")], as_of=date(2021, 1, 1), model_cutoff=date(2023, 6, 1),
                          cutoff_documented=True, outcome_date=date(2024, 1, 1))
    assert reg.control_level == "partially_controlled" and any("registry" in f for f in reg.flags)
    undated = assess_temporal([_src(published=None)], as_of=date(2021, 1, 1), model_cutoff=date(2023, 6, 1),
                              cutoff_documented=True, outcome_date=date(2024, 1, 1))
    assert undated.control_level == "partially_controlled"


def test_blind_guess_evaluation():
    hit = evaluate_blind_guess(["Maybe Acmedrug from Acme Bio"], TERMS, guesser="llm")
    assert hit.identified and hit.matched_terms == ["Acmedrug", "Acme Bio"]
    miss = evaluate_blind_guess([], TERMS, guesser="llm")
    assert miss.performed and not miss.identified and "does not prove protection" in miss.note


def _report(guess, temporal_level="controlled", findings=()):
    from vic.evidence.leakage import TemporalAssessment
    return build_leakage_report(identity_findings=list(findings), temporal=TemporalAssessment(temporal_level, []),
                                guess=guess, method="rule-based masking + blind guess")


def test_overall_is_never_controlled_on_unproven_evidence():
    good_guess = evaluate_blind_guess([], TERMS, guesser="llm")
    assert _report(good_guess)["overall"] == "controlled_as_tested"
    assert _report(None)["overall"] == "partial"                                   # no guess performed
    assert _report(good_guess, "partially_controlled")["overall"] == "partial"      # uncertain temporal control
    assert _report(evaluate_blind_guess(["Acmedrug"], TERMS, guesser="llm"))["overall"] == "uncontrolled"
    assert _report(good_guess, "uncontrolled")["overall"] == "uncontrolled"
    assert len(_report(good_guess)["limitations"]) == 4  # limitations are always stated


class _FakeModel:
    def __init__(self, names=None, error=None):
        self.names, self.error, self.calls = names or [], error, []

    async def generate_structured(self, prompt_id, payload, response_model, ctx):
        self.calls.append((prompt_id, payload))
        if self.error:
            raise self.error
        return BlindGuess(candidate_names=self.names, confidence="high", reasoning="numbers")


def _ctx(model):
    return RunContext(case_id="c", run_id="r", snapshot_id=None, as_of_date=None, mode=RunMode.LIVE, model=model)


def test_model_blind_guess_sees_only_the_blind_pack():
    blind = anonymize_pack(_pack(), TERMS)
    model = _FakeModel(names=["Acmedrug"])
    res = asyncio.run(blind_identity_guess(blind, TERMS, _ctx(model)))
    sent = str(model.calls[0][1]).lower()
    assert model.calls[0][0] == "blind_guess" and "acmedrug" not in sent and "nct01234567" not in sent
    assert res.identified and res.guesser == "llm"


def test_blind_guess_failure_is_recorded_as_not_performed():
    blind = anonymize_pack(_pack(), TERMS)
    res = asyncio.run(blind_identity_guess(blind, TERMS, _ctx(_FakeModel(error=RuntimeError("x")))))
    assert not res.performed and not res.identified
    assert not asyncio.run(blind_identity_guess(blind, TERMS, _ctx(None))).performed