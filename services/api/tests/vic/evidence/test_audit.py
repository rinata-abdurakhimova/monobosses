from vic.contracts import Claim, Importance, Provenance, Scope, SupportStatus
from vic.evidence import fixtures
from vic.evidence.audit import audit_claims

BASE = fixtures.build_baseline_pack()
PACK = BASE.pack


def _ev(fragment):
    return next(e.id for e in PACK.evidence if fragment in e.excerpt)


def _claim(cid, text, ev_ids=(), *, status=SupportStatus.SUPPORTED, prov=Provenance.SOURCE,
           scope=Scope.PROGRAM, imp=Importance.CRITICAL, assumptions=()):
    return Claim(id=cid, text=text, provenance=prov, support_status=status, evidence_ids=list(ev_ids),
                 assumptions=list(assumptions), scope=scope, importance=imp)


def _one(claim, **kw):
    res = audit_claims([claim], PACK, **kw)
    return res, res.findings[0]


def test_mouse_result_cited_as_human_efficacy_is_caught_and_blocks():
    c = _claim("translation.human_efficacy", "X-001 lowers marker M in patients with Disease D.",
               [_ev("mouse model, the SYN-1 inhibitor")])
    res, f = _one(c)
    assert f.verdict == SupportStatus.UNVERIFIED and f.blocking
    assert "population mismatch" in f.reason.lower() and "animal" in f.reason
    assert f.evidence_ids == c.evidence_ids
    assert res.unresolved_critical_claim_ids == ["translation.human_efficacy"]


def test_correctly_labelled_animal_claim_passes():
    c = _claim("science.mouse_effect", "In a mouse model, X-001 lowered marker M by 48%.",
               [_ev("mouse model, the SYN-1 inhibitor")])
    _, f = _one(c)
    assert f.verdict == SupportStatus.SUPPORTED and not f.blocking


def test_dangling_citation_is_caught():
    c = _claim("science.target_validation", "SYN-1 inhibition reduces marker M.", ["ev-doesnotexist-001"])
    res, f = _one(c)
    assert f.verdict == SupportStatus.UNVERIFIED and f.blocking
    assert "does not exist" in f.reason and "ev-doesnotexist-001" in f.evidence_ids


def test_misattributed_citation_is_flagged_as_heuristic():
    c = _claim("market.pricing", "Annual pricing exceeds reimbursement benchmarks in the target region.",
               [_ev("mouse model, the SYN-1 inhibitor")], scope=Scope.APPROACH)
    _, f = _one(c)
    assert f.verdict == SupportStatus.UNVERIFIED and "misattribution" in f.reason and f.blocking


def test_association_cited_as_causal_is_caught():
    c = _claim("science.causality", "SYN-1 is causally linked to marker M, which validates the target.",
               [_ev("cohort analysis associated")], scope=Scope.APPROACH)
    _, f = _one(c)
    assert "association cited as causal" in f.reason.lower()


def test_association_claim_worded_as_association_passes():
    c = _claim("science.genetic_link", "Loss-of-function variants in SYN1 are associated with lower marker M.",
               [_ev("cohort analysis associated")], scope=Scope.APPROACH)
    _, f = _one(c)
    assert f.verdict == SupportStatus.SUPPORTED and not f.blocking


def test_program_claim_on_approach_level_evidence_is_scope_mismatch():
    c = _claim("science.cell_effect", "SYN-1 inhibition reduced marker M in cultured cells.",
               [_ev("cultured Disease-D model cells")], scope=Scope.PROGRAM)
    _, f = _one(c)
    assert "scope mismatch" in f.reason.lower() and f.blocking


def test_non_critical_failure_is_reported_but_not_blocking():
    c = _claim("science.minor", "X-001 lowers marker M in patients.", [_ev("mouse model, the SYN-1 inhibitor")],
               imp=Importance.MINOR)
    res, f = _one(c)
    assert f.verdict == SupportStatus.UNVERIFIED and not f.blocking and res.unresolved_critical_claim_ids == []


def test_honest_unknown_is_a_gap_not_a_blocker():
    c = _claim("translation.safe_exposure", "A safe human exposure range is unknown.",
               status=SupportStatus.UNKNOWN, prov=Provenance.AI)
    _, f = _one(c)
    assert f.verdict == SupportStatus.UNKNOWN and not f.blocking


def test_ai_inference_needs_premises_or_assumptions():
    bad = _claim("chair.inference", "Efficacy will translate to humans.", status=SupportStatus.UNVERIFIED,
                 prov=Provenance.AI)
    ok = _claim("chair.inference_ok", "Efficacy may translate to humans.", status=SupportStatus.UNVERIFIED,
                prov=Provenance.AI, assumptions=["Mouse and human SYN-1 share 71% identity."])
    res = audit_claims([bad, ok], PACK)
    assert res.findings[0].blocking and "cannot be inspected" in res.findings[0].reason
    assert not res.findings[1].blocking
    assert res.unresolved_critical_claim_ids == ["chair.inference"]


def test_user_provided_claim_is_marked_unverified_not_blocking():
    c = _claim("market.user_note", "Our partner confirmed interest.", status=SupportStatus.UNVERIFIED,
               prov=Provenance.USER)
    _, f = _one(c)
    assert f.verdict == SupportStatus.UNVERIFIED and not f.blocking and "User-provided" in f.reason


def test_altered_excerpt_is_caught_when_documents_are_supplied():
    real = next(e for e in PACK.evidence if "mouse model, the SYN-1 inhibitor" in e.excerpt)
    forged = real.model_copy(update={"id": "ev-forged-001", "excerpt": "X-001 cured all treated patients."})
    pack = PACK.model_copy(update={"evidence": PACK.evidence + [forged]})
    c = _claim("science.mouse_effect", "In a mouse model, X-001 lowered marker M.", ["ev-forged-001"])
    res = audit_claims([c], pack, documents=BASE.documents)
    assert "altered or invented" in res.findings[0].reason and res.findings[0].blocking


def test_evidence_with_unknown_source_is_flagged():
    orphan = PACK.evidence[0].model_copy(update={"id": "ev-orphan-001", "source_id": "src-missing"})
    pack = PACK.model_copy(update={"evidence": PACK.evidence + [orphan]})
    c = _claim("science.x", "In a mouse model, X-001 lowered marker M.", ["ev-orphan-001"])
    res = audit_claims([c], pack)
    assert any("unknown source" in w for w in res.warnings) and res.findings[0].blocking


def test_specialist_and_chair_claims_go_through_the_same_function():
    spec = _claim("science.mouse_effect", "In a mouse model, X-001 lowered marker M by 48%.",
                  [_ev("mouse model, the SYN-1 inhibitor")])
    chair = _claim("chair.bold", "X-001 is effective in patients.", [_ev("mouse model, the SYN-1 inhibitor")])
    res = audit_claims([spec, chair], PACK)
    assert [f.blocking for f in res.findings] == [False, True]
    assert res.unresolved_critical_claim_ids == ["chair.bold"]