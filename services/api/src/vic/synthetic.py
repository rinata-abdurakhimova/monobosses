"""English-language synthetic fixtures for contract v1. No real drug, target or disease.

`build_all()` is the single source of truth: scripts/generate_fixtures.py writes it to
contracts/fixtures/*.json, and the mock repository serves the same objects.
Story: v1 = Conditional (safe exposure unknown); v2 = Do Not Invest (synthetic safety result).
"""
import hashlib
from datetime import UTC, date, datetime

from pydantic import BaseModel

from vic import integrity
from vic.contracts import (
    CaseInput,
    Claim,
    ClaimChange,
    DiligenceQuestion,
    Disagreement,
    ErrorBody,
    Evidence,
    EvidencePack,
    Importance,
    Provenance,
    Recommendation,
    Report,
    Revision,
    Risk,
    RoleId,
    RoleResult,
    Run,
    RunMode,
    RunStage,
    RunStatus,
    Scope,
    SectionContent,
    SectionKey,
    Source,
    SupportStatus,
)

CASE_ID = "case-synthetic-01"
REPORT_V1_ID = "rep-synthetic-v1"
REPORT_V2_ID = "rep-synthetic-v2"
SNAPSHOT_V1 = "snap-synthetic-v1"
SNAPSHOT_V2 = "snap-synthetic-v2"
RETRIEVED_AT = datetime(2025, 1, 10, 12, 0, 0, tzinfo=UTC)
RETRIEVED_AT_V2 = datetime(2025, 6, 10, 12, 0, 0, tzinfo=UTC)

# ------------------------------------------------------------------ sources & evidence
_TEXTS = {
    "src-synthetic-01": (
        "A synthetic study reports that loss-of-function variants in the target Y gene are associated with a lower risk of disease X in a synthetic cohort. Association does not establish causality."),
    "src-synthetic-02": (
        "In a synthetic animal model, target Y inhibition reduced a marker of X progression. The model only partially represents human disease."),
    "src-synthetic-03": (
        "Synthetic registry record: a phase 1 trial of the synthetic candidate is planned; the primary endpoint is safety and tolerability; patient exposure has not been reported."),
    "src-synthetic-04": (
        "A synthetic company presentation states an intention to start phase 2 after confirming safety. This is company material, not independent evidence."),
    "src-synthetic-05": (
        "Synthetic phase 1 trial report: at the exposure required for target engagement, a serious adverse event was recorded, halting dose escalation."),
}

# (id, title, type, published_at)
_SOURCE_SPECS = [
    ("src-synthetic-01", "[SYNTHETIC] Article: genetic association of target Y with disease X",
     "peer_reviewed", date(2022, 3, 15)),
    ("src-synthetic-02", "[SYNTHETIC] Preprint: preclinical model of target Y inhibition",
     "preprint", date(2023, 5, 2)),
    ("src-synthetic-03", "[SYNTHETIC] Clinical trial registry record", "registry",
     date(2024, 9, 1)),
    ("src-synthetic-04", "[SYNTHETIC] Developer company presentation", "company",
     date(2024, 11, 20)),
]
_SOURCE_SPEC_V2 = ("src-synthetic-05", "[SYNTHETIC] Phase 1 trial safety report",
                   "company", date(2025, 6, 1))

# (id, source_id, excerpt, locator, scope, limitations) — excerpt must be a substring of the text
_EVIDENCE_SPECS = [
    ("ev-synthetic-01", "src-synthetic-01",
     "loss-of-function variants in the target Y gene are associated with a lower risk of disease X",
     "abstract", Scope.APPROACH, ["Synthetic cohort; causality has not been established"]),
    ("ev-synthetic-02", "src-synthetic-01", "Association does not establish causality.", "limitations",
     Scope.APPROACH, []),
    ("ev-synthetic-03", "src-synthetic-02",
     "target Y inhibition reduced a marker of X progression", "results", Scope.APPROACH,
     ["The animal model only partially represents human disease"]),
    ("ev-synthetic-04", "src-synthetic-03", "patient exposure has not been reported",
     "record.results", Scope.PROGRAM, []),
    ("ev-synthetic-05", "src-synthetic-03", "the primary endpoint is safety and tolerability",
     "record.endpoints", Scope.PROGRAM, []),
    ("ev-synthetic-06", "src-synthetic-04", "This is company material, not independent evidence.",
     "slide 5", Scope.PROGRAM, ["Company material"]),
]
_EVIDENCE_SPEC_V2 = (
    "ev-synthetic-07", "src-synthetic-05",
    "a serious adverse event was recorded, halting dose escalation", "section 3",
    Scope.PROGRAM, ["Synthetic result for the controlled v1-to-v2 story"])


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sources(specs, retrieved_at):
    return [Source(id=i, title=t, url=None, type=ty, published_at=d, retrieved_at=retrieved_at,
                   content_hash=_hash(_TEXTS[i]), synthetic=True) for i, t, ty, d in specs]


def _evidence(specs):
    for _id, src, excerpt, *_ in specs:
        if excerpt not in _TEXTS[src]:
            raise AssertionError(f"excerpt of {_id} is not a substring of {src}")
    return [Evidence(id=i, source_id=s, excerpt=x, locator=loc, scope=sc, limitations=lim)
            for i, s, x, loc, sc, lim in specs]


def build_pack_v1() -> EvidencePack:
    return EvidencePack(
        sources=_sources(_SOURCE_SPECS, RETRIEVED_AT), evidence=_evidence(_EVIDENCE_SPECS),
        retrieval_warnings=["Synthetic pack: no sources were retrieved over the network."],
        snapshot_id=SNAPSHOT_V1, synthetic=True)


def build_pack_v2() -> EvidencePack:
    v1 = build_pack_v1()
    return EvidencePack(
        sources=v1.sources + _sources([_SOURCE_SPEC_V2], RETRIEVED_AT_V2),
        evidence=v1.evidence + _evidence([_EVIDENCE_SPEC_V2]),
        retrieval_warnings=v1.retrieval_warnings, snapshot_id=SNAPSHOT_V2, synthetic=True)


# ------------------------------------------------------------------ case
def build_case() -> CaseInput:
    return CaseInput(
        indication="Synthetic disease X",
        mechanism="Inhibition of synthetic target Y",
        scope=Scope.PROGRAM,
        program_data=("Synthetic programme: an oral small molecule that inhibits target Y; preclinical data are limited; no human exposure data are available."),
        modality="Small molecule", development_stage="Preparation for phase 1", as_of_date=None)


# ------------------------------------------------------------------ claims
def _claim(id_, text, prov, status, ev, scope, imp):
    return Claim(id=id_, text=text, provenance=prov, support_status=status, evidence_ids=ev,
                 assumptions=[], scope=scope, importance=imp)


def _claims_v1() -> list[Claim]:
    P, S, I = Provenance, SupportStatus, Importance
    return [
        _claim("science.target_validation",
               "Genetic data link loss of target Y function to a lower risk of X, but this is an association, not established causality.",
               P.SOURCE, S.MIXED, ["ev-synthetic-01", "ev-synthetic-02"], Scope.APPROACH, I.CRITICAL),
        _claim("science.animal_model",
               "The animal model shows a reduction in a progression marker, but its relevance to humans is limited.",
               P.SOURCE, S.MIXED, ["ev-synthetic-03"], Scope.APPROACH, I.MAJOR),
        _claim("translation.safe_exposure",
               "The safety of the required human exposure has not been established.",
               P.AI, S.UNKNOWN, ["ev-synthetic-04"], Scope.PROGRAM, I.CRITICAL),
        _claim("translation.biomarker_link",
               "A biomarker linking target engagement to patient benefit has not been confirmed.",
               P.AI, S.UNVERIFIED, [], Scope.PROGRAM, I.MAJOR),
        _claim("clinical.phase1_design",
               "The planned phase 1 trial focuses on safety and tolerability.",
               P.SOURCE, S.SUPPORTED, ["ev-synthetic-05"], Scope.PROGRAM, I.MAJOR),
        _claim("clinical.efficacy_path",
               "The path to evidence of efficacy depends on safety results and has not been defined.",
               P.AI, S.UNKNOWN, [], Scope.PROGRAM, I.MAJOR),
        _claim("market.company_claims",
               "Company statements of intent are not independent evidence of commercial value.",
               P.SOURCE, S.SUPPORTED, ["ev-synthetic-06"], Scope.PROGRAM, I.MINOR),
        _claim("market.unmet_need",
               "Unmet need in X requires verification using independent sources.",
               P.AI, S.UNVERIFIED, [], Scope.APPROACH, I.MAJOR),
        _claim("investment.capital_unknown",
               "Capital to the next milestone cannot be justified without a budget and trial plan.",
               P.AI, S.UNKNOWN, [], Scope.PROGRAM, I.MAJOR),
        _claim("user.program_summary",
               "The user provided a description of a synthetic programme; it has not been independently verified.",
               P.USER, S.UNVERIFIED, [], Scope.PROGRAM, I.MINOR),
    ]


def _claims_v2() -> list[Claim]:
    claims = _claims_v1()
    for i, c in enumerate(claims):
        if c.id == "translation.safe_exposure":
            claims[i] = _claim(
                "translation.safe_exposure",
                "The required human exposure is unsafe: a serious adverse event was recorded in the synthetic trial.",
                Provenance.SOURCE, SupportStatus.CONTRADICTED,
                ["ev-synthetic-04", "ev-synthetic-07"], Scope.PROGRAM, Importance.CRITICAL)
    return claims


# ------------------------------------------------------------------ risks, questions, sections
def _risks(v2: bool) -> list[Risk]:
    r1 = (Risk(id="risk-synthetic-01",
               description="A serious adverse event has been confirmed at the required exposure.",
               priority=Importance.CRITICAL, claim_ids=["translation.safe_exposure"],
               impact="The programme thesis cannot be met without a different dosing regimen or candidate.",
               next_check="Check whether an alternative regimen or candidate exists.")
          if v2 else
          Risk(id="risk-synthetic-01",
               description="The safety of the required human exposure has not been established.",
               priority=Importance.CRITICAL, claim_ids=["translation.safe_exposure"],
               impact="May halt development and invalidate the investment thesis.",
               next_check="Obtain safety and exposure data from the phase 1 trial."))
    return [
        r1,
        Risk(id="risk-synthetic-02",
             description="The effect in the animal model may not translate to humans.",
             priority=Importance.MAJOR, claim_ids=["science.animal_model"],
             impact="Reduces the scientific support for the mechanism in humans.",
             next_check="Find human tissue or biomarker data."),
        Risk(id="risk-synthetic-03",
             description="The budget and time to the next milestone are unknown.",
             priority=Importance.MAJOR, claim_ids=["investment.capital_unknown"],
             impact="Funding needs cannot be assessed.",
             next_check="Obtain a phase 1 cost estimate and trial plan."),
    ]


def _questions(v2: bool) -> list[DiligenceQuestion]:
    q1 = (DiligenceQuestion(
        question="Is there a dosing regimen that achieves target engagement without a serious adverse event?",
        why_it_matters="This determines whether the programme can be reconsidered.",
        evidence_needed="Dosing and safety data from subsequent cohorts.",
        decision_if_positive="Reconsider the recommendation towards Conditional.",
        decision_if_negative="Retain Do Not Invest.")
        if v2 else DiligenceQuestion(
        question="Can the required human exposure be achieved safely?",
        why_it_matters="This is a critical unknown that blocks the patient benefit thesis.",
        evidence_needed="PK and safety data from the phase 1 trial.",
        decision_if_positive="The recommendation may become Invest if other conditions are confirmed.",
        decision_if_negative="The recommendation becomes Do Not Invest."))
    return [
        q1,
        DiligenceQuestion(
            question="Which biomarker confirms target engagement in humans?",
            why_it_matters="Without it, the effect-to-benefit chain remains incomplete.",
            evidence_needed="Biomarker data from early trials.",
            decision_if_positive="Strengthens the human translation thesis.",
            decision_if_negative="Reduces confidence in the mechanism."),
        DiligenceQuestion(
            question="Is the genetic association confirmed in independent cohorts?",
            why_it_matters="A single cohort does not establish causality.",
            evidence_needed="Independent genetic studies.",
            decision_if_positive="Strengthens the scientific thesis.",
            decision_if_negative="The scientific case weakens."),
        DiligenceQuestion(
            question="What are the budget and timeline for the phase 1 trial?",
            why_it_matters="Needed to estimate capital to milestone.",
            evidence_needed="CRO cost estimate and trial plan.",
            decision_if_positive="Allows a capital range to be estimated.",
            decision_if_negative="A range cannot be justified; the decision remains conditional."),
        DiligenceQuestion(
            question="What alternatives exist for patients with X, and how does the programme differ?",
            why_it_matters="Commercial value depends on differentiation from the standard of care.",
            evidence_needed="Review of the standard of care and competing programmes.",
            decision_if_positive="Strengthens the commercial thesis.",
            decision_if_negative="Reduces commercial attractiveness."),
        DiligenceQuestion(
            question="Are there rights or licensing restrictions that affect the programme?",
            why_it_matters="Third-party rights may change the deal terms.",
            evidence_needed="Patent search and legal opinion.",
            decision_if_positive="Deal terms can be discussed.",
            decision_if_negative="Licences are needed, or the deal structure must change."),
    ]


_SUMMARIES_V1 = {
    SectionKey.RECOMMENDATION: "Conditional: interest depends on confirming exposure safety.",
    SectionKey.SCIENTIFIC_THESIS: "Target Y has partial genetic and preclinical support.",
    SectionKey.HUMAN_TRANSLATION_THESIS: "The safety of the required human exposure has not been established.",
    SectionKey.CLINICAL_DEVELOPMENT_PLAN: "Phase 1 focuses on safety; the path to efficacy has not been defined.",
    SectionKey.COMPETITIVE_LANDSCAPE: "The competitive landscape requires independent verification.",
    SectionKey.COMMERCIAL_OPPORTUNITY: "Commercial value has not been confirmed by independent sources.",
    SectionKey.CAPITAL_TO_MILESTONE: "The capital range has not been estimated: a budget and trial plan are missing.",
    SectionKey.KEY_RISKS: "The critical risk is exposure safety; the model and budget are material risks.",
    SectionKey.CRITICAL_UNKNOWNS: "Safe exposure, biomarker, path to efficacy, and budget.",
    SectionKey.DILIGENCE_QUESTIONS: "Six priority diligence questions.",
    SectionKey.SOURCES: "Four synthetic sources; some are company materials.",
}
_SUMMARIES_V2 = dict(_SUMMARIES_V1) | {
    SectionKey.RECOMMENDATION: "Do Not Invest: the synthetic result shows unsafe exposure.",
    SectionKey.HUMAN_TRANSLATION_THESIS: "The required exposure is associated with a serious adverse event.",
    SectionKey.KEY_RISKS: "The synthetic safety result confirms a critical risk.",
    SectionKey.CRITICAL_UNKNOWNS: "Whether a safe dosing regimen exists; biomarker; budget.",
    SectionKey.DILIGENCE_QUESTIONS: "Six questions; the first concerns a safe regimen.",
    SectionKey.SOURCES: "Five synthetic sources, including the safety report.",
}

_SECTION_CLAIMS = {
    SectionKey.RECOMMENDATION: ["translation.safe_exposure"],
    SectionKey.SCIENTIFIC_THESIS: ["science.target_validation", "science.animal_model"],
    SectionKey.HUMAN_TRANSLATION_THESIS: ["translation.safe_exposure", "translation.biomarker_link"],
    SectionKey.CLINICAL_DEVELOPMENT_PLAN: ["clinical.phase1_design", "clinical.efficacy_path"],
    SectionKey.COMPETITIVE_LANDSCAPE: ["market.unmet_need"],
    SectionKey.COMMERCIAL_OPPORTUNITY: ["market.company_claims", "market.unmet_need"],
    SectionKey.CAPITAL_TO_MILESTONE: ["investment.capital_unknown"],
    SectionKey.KEY_RISKS: ["translation.safe_exposure", "science.animal_model",
                           "investment.capital_unknown"],
    SectionKey.CRITICAL_UNKNOWNS: ["translation.safe_exposure", "clinical.efficacy_path",
                                   "investment.capital_unknown"],
    SectionKey.DILIGENCE_QUESTIONS: ["translation.safe_exposure", "translation.biomarker_link"],
    SectionKey.SOURCES: [],
}
_SECTION_LIMITS = {
    SectionKey.SCIENTIFIC_THESIS: ["Association does not establish causality."],
    SectionKey.CAPITAL_TO_MILESTONE: ["A cost estimate and trial plan are needed."],
    SectionKey.COMMERCIAL_OPPORTUNITY: ["Population size is not the same as the addressable market."],
}


def _sections(summaries, recommendation, risks, questions, sources) -> list[SectionContent]:
    out = []
    for key in SectionKey:
        data = None
        if key == SectionKey.RECOMMENDATION:
            data = {"recommendation": recommendation.value}
        elif key == SectionKey.KEY_RISKS:
            data = {"risk_ids": [r.id for r in risks]}
        elif key == SectionKey.DILIGENCE_QUESTIONS:
            data = {"question_count": len(questions)}
        elif key == SectionKey.SOURCES:
            data = {"source_ids": [s.id for s in sources]}
        out.append(SectionContent(key=key, summary=summaries[key],
                                  claim_ids=list(_SECTION_CLAIMS[key]),
                                  limitations=list(_SECTION_LIMITS.get(key, [])),
                                  structured_data=data))
    return out


def _roles(claims, risks, sections, v2: bool) -> list[RoleResult]:
    c = {x.id: x for x in claims}
    r = {x.id: x for x in risks}
    s = {x.key: x for x in sections}
    return [
        RoleResult(
            role_id=RoleId.SCIENCE, summary="Partial biological support.",
            position="Genetic and preclinical data support target Y; causality has not been established.",
            claims=[c["science.target_validation"], c["science.animal_model"]],
            risks=[r["risk-synthetic-02"]],
            unknowns=["Causality of the genetic association"],
            change_conditions=["Independent cohorts or human tissue data"],
            section_content=[s[SectionKey.SCIENTIFIC_THESIS]]),
        RoleResult(
            role_id=RoleId.TRANSLATION,
            summary=("Exposure is unsafe." if v2 else "Exposure safety has not been established."),
            position=("New synthetic evidence contradicts safe exposure." if v2 else
                      "The exposure-to-safety link is missing; candidate properties cannot be generalized to the entire mechanism."),
            claims=[c["translation.safe_exposure"], c["translation.biomarker_link"]],
            risks=[r["risk-synthetic-01"]],
            unknowns=["Target engagement biomarker"],
            change_conditions=["A safe dosing regimen"] if v2 else
            ["PK and safety data from the phase 1 trial"],
            section_content=[s[SectionKey.HUMAN_TRANSLATION_THESIS]]),
        RoleResult(
            role_id=RoleId.CLINICAL, summary="Phase 1 is planned; subsequent development is uncertain.",
            position="The path to efficacy depends on safety.",
            claims=[c["clinical.phase1_design"], c["clinical.efficacy_path"]], risks=[],
            unknowns=["Phase 2 endpoints"], change_conditions=["Safety results"],
            section_content=[s[SectionKey.CLINICAL_DEVELOPMENT_PLAN]]),
        RoleResult(
            role_id=RoleId.MARKET, summary="Commercial value has not been confirmed.",
            position="Company statements are not independent evidence.",
            claims=[c["market.company_claims"], c["market.unmet_need"]], risks=[],
            unknowns=["Standard of care and alternatives"],
            change_conditions=["Independent market review"],
            section_content=[s[SectionKey.COMPETITIVE_LANDSCAPE],
                             s[SectionKey.COMMERCIAL_OPPORTUNITY]]),
        RoleResult(
            role_id=RoleId.INVESTMENT, summary="Capital has not been estimated.",
            position="A range cannot be justified without a budget; no number is invented.",
            claims=[c["investment.capital_unknown"]], risks=[r["risk-synthetic-03"]],
            unknowns=["Cost estimate and time to milestone"], change_conditions=["CRO cost estimate"],
            section_content=[s[SectionKey.CAPITAL_TO_MILESTONE]]),
    ]


def build_report(version: int) -> Report:
    v2 = version == 2
    pack = build_pack_v2() if v2 else build_pack_v1()
    claims = _claims_v2() if v2 else _claims_v1()
    risks = _risks(v2)
    questions = _questions(v2)
    rec = Recommendation.DO_NOT_INVEST if v2 else Recommendation.CONDITIONAL
    sections = _sections(_SUMMARIES_V2 if v2 else _SUMMARIES_V1, rec, risks, questions, pack.sources)
    revision = None
    if v2:
        before = next(c for c in _claims_v1() if c.id == "translation.safe_exposure")
        after = next(c for c in claims if c.id == "translation.safe_exposure")
        revision = Revision(
            parent_report_id=REPORT_V1_ID, new_evidence_ids=["ev-synthetic-07"],
            changed_claims=[ClaimChange(claim_id="translation.safe_exposure", before=before,
                                        after=after)],
            previous_recommendation=Recommendation.CONDITIONAL,
            new_recommendation=Recommendation.DO_NOT_INVEST,
            explanation=("New evidence ev-synthetic-07 shows a serious adverse event at the required exposure: claim translation.safe_exposure changes from unknown to contradicted, and the recommendation changes from Conditional to Do Not Invest."))
    return Report(
        id=REPORT_V2_ID if v2 else REPORT_V1_ID, case_id=CASE_ID,
        run_id="run-synthetic-v2" if v2 else "run-synthetic-v1", version=version,
        scope=Scope.PROGRAM, synthetic=True, snapshot_id=pack.snapshot_id, recommendation=rec,
        rationale=("New synthetic safety evidence contradicts a key condition of the thesis; the decision is Do Not Invest." if v2 else
                   "The mechanism has partial support, but safe human exposure has not been established and programme data are incomplete. The decision is Conditional: interest depends on confirming safety."),
        decision_conditions=(["Reconsider only with independent evidence of a safe regimen"]
                             if v2 else
                             ["Obtain human safety and exposure data",
                              "Confirm the target engagement biomarker",
                              "Obtain a phase 1 cost estimate and trial plan"]),
        sections=sections, roles=_roles(claims, risks, sections, v2), claims=claims,
        evidence=pack.evidence, sources=pack.sources,
        disagreements=[Disagreement(
            topic="Adequacy of the genetic evidence",
            role_ids=[RoleId.SCIENCE, RoleId.TRANSLATION],
            summary="The scientific analysis sees support for the target; the human translation analysis identifies a gap in the exposure chain.",
            resolution="The chair treats genetics as support for the mechanism, not evidence of benefit.")],
        risks=risks, diligence_questions=questions, revision=revision)


def build_r5_role_report() -> Report:
    """Display-only fixture for all agreed roles; no expert nodes are executed."""
    report = build_report(1)
    report.id = "rep-synthetic-r5"
    report.run_id = "run-synthetic-r5"
    examples = [
        (RoleId.FAILURE_MINER, "Safe human exposure remains an unresolved failure mode.",
         "translation.safe_exposure", SectionKey.KEY_RISKS),
        (RoleId.INVESTMENT_THRESHOLD, "Safe exposure is required before the thesis can advance.",
         "translation.safe_exposure", SectionKey.CRITICAL_UNKNOWNS),
        (RoleId.PARTNERSHIPS, "No partner interest is established in this fictional case.",
         "partnerships.interest_unknown", SectionKey.COMMERCIAL_OPPORTUNITY),
        (RoleId.IP_LICENSING, "Patent ownership and licensing rights have not been established.",
         "ip_licensing.rights_unknown", SectionKey.KEY_RISKS),
        (RoleId.CHAIR, "The fictional committee remains Conditional pending safe exposure.",
         "translation.safe_exposure", SectionKey.RECOMMENDATION),
        (RoleId.AUDIT, "Evidence links in this display fixture do not establish live audit quality.",
         "translation.safe_exposure", SectionKey.SOURCES),
    ]
    for role_id, summary, claim_id, section_key in examples:
        claim = next((c for c in report.claims if c.id == claim_id), None)
        if claim is None:
            claim = Claim(id=claim_id, text=summary, provenance=Provenance.AI,
                          support_status=SupportStatus.UNKNOWN, scope=report.scope,
                          importance=Importance.MAJOR)
            report.claims.append(claim)
        report.roles.append(RoleResult(
            role_id=role_id, summary=f"Synthetic display example: {summary}",
            position="Illustrative only; missing evidence remains unknown.",
            claims=[claim], risks=[report.risks[0]] if role_id == RoleId.FAILURE_MINER else [],
            unknowns=[summary],
            change_conditions=["Obtain and audit the missing evidence before changing this position."],
            section_content=[SectionContent(
                key=section_key, summary=summary, claim_ids=[claim_id],
                limitations=["Synthetic display fixture; no live analysis was performed."],
            )],
        ))
    integrity.assert_report(report)
    return report


def build_runs() -> tuple[Run, Run]:
    running = Run(id="run-synthetic-running", case_id=CASE_ID, status=RunStatus.RUNNING,
                  stage=RunStage.ANALYZE, report_version=None, warnings=[],
                  trace_id="trace-synthetic-running", mode=RunMode.LIVE,
                  model_version="synthetic", config_version="synthetic-v1")
    failed = Run(id="run-synthetic-failed", case_id=CASE_ID, status=RunStatus.FAILED,
                 stage=RunStage.AUDIT, report_version=None,
                 warnings=["Synthetic failure example"],
                 error=ErrorBody(code="run_interrupted",
                                 message="The run was interrupted by a server restart; start a new run.",
                                 retryable=True),
                 trace_id="trace-synthetic-failed", mode=RunMode.LIVE,
                 model_version="synthetic", config_version="synthetic-v1")
    return running, failed


def build_all() -> dict[str, BaseModel]:
    """File stem -> model. Validates every object and every integrity rule."""
    pack = build_pack_v1()
    v1, v2 = build_report(1), build_report(2)
    integrity.assert_pack(pack)
    integrity.assert_pack(build_pack_v2())
    integrity.assert_report(v1)
    integrity.assert_report(v2, parent=v1)
    running, failed = build_runs()
    return {"case": build_case(), "evidence-pack": pack, "report-v1": v1, "report-v2": v2,
            "report-r5": build_r5_role_report(),
            "run-running": running, "run-failed": failed}
