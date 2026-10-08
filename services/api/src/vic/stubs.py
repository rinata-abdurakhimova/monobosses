"""SYNTHETIC development stubs (DEV_STUBS=true only; refused in production).

They return synthetic content, never a real analysis. Reports that used any stub are marked
synthetic=true. They exist so the pipeline, storage and UI can be developed before every
R3/R4/R5 module is ready, and so real agents can be exercised while other parts are still stubs.
"""
import asyncio

from vic import synthetic
from vic.config import get_settings
from vic.contracts import (AuditFinding, AuditResult, CaseInput, Claim, CommitteeDecision,
                           DiligenceQuestion, EvidencePack, Recommendation, RoleId, RoleResult,
                           RunContext)
from vic.modules import STUB_ORIGIN, Modules


async def _pause() -> None:
    delay = get_settings().stub_delay_seconds
    if delay > 0:
        await asyncio.sleep(delay)


def _role(role: RoleId) -> RoleResult:
    return next(r for r in synthetic.build_report(1).roles if r.role_id == role)


def _questions_from(results: list[RoleResult]) -> list[DiligenceQuestion]:
    """Reuse the diligence questions that real roles put into structured_data, then pad with
    synthetic ones so the 5-10 rule is met."""
    seen: set[str] = set()
    out: list[DiligenceQuestion] = []

    def add(q: DiligenceQuestion) -> None:
        if q.question not in seen:
            seen.add(q.question)
            out.append(q)

    for res in results:
        for sc in res.section_content:
            for raw in (sc.structured_data or {}).get("diligence_questions") or []:
                try:
                    add(DiligenceQuestion.model_validate(raw))
                except ValueError:
                    continue
    for q in synthetic.build_report(1).diligence_questions:
        if len(out) >= 6:
            break
        add(q)
    return out[:10]


async def build_evidence_pack_synthetic(case: CaseInput, ctx: RunContext) -> EvidencePack:
    await _pause()
    return synthetic.build_pack_v1()


async def build_evidence_pack_r3(case: CaseInput, ctx: RunContext) -> EvidencePack:
    """R3's own synthetic baseline documents (used when real agents analyse the pack, because the
    synthetic role stubs cite evidence ids that only exist in R2's synthetic pack)."""
    await _pause()
    from vic.evidence.fixtures import build_baseline_pack
    return build_baseline_pack().pack


async def analyze_science(case, pack, ctx) -> RoleResult:
    await _pause()
    return _role(RoleId.SCIENCE)


async def analyze_translation(case, pack, ctx) -> RoleResult:
    await _pause()
    return _role(RoleId.TRANSLATION)


async def analyze_clinical(case, pack, scientific, ctx) -> RoleResult:
    await _pause()
    return _role(RoleId.CLINICAL)


async def analyze_market(case, pack, ctx) -> RoleResult:
    await _pause()
    return _role(RoleId.MARKET)


async def analyze_investment(case, pack, clinical, market, ctx) -> RoleResult:
    await _pause()
    return _role(RoleId.INVESTMENT)


async def audit_claims(claims: list[Claim], pack: EvidencePack, ctx: RunContext) -> AuditResult:
    await _pause()
    findings = [AuditFinding(claim_id=c.id, verdict=c.support_status,
                             reason="Synthetic stub audit: nothing was verified",
                             evidence_ids=list(c.evidence_ids), blocking=False) for c in claims]
    return AuditResult(findings=findings, unresolved_critical_claim_ids=[],
                       warnings=["Synthetic stub audit"])


async def synthesize_committee(results: list[RoleResult], audit: AuditResult,
                               ctx: RunContext) -> CommitteeDecision:
    """Builds a decision from the actual role results (never from a vote): always Conditional."""
    await _pause()
    known = {c.id for res in results for c in res.claims}
    risks, seen = [], set()
    for res in results:
        for r in res.risks:
            if r.id not in seen:
                seen.add(r.id)
                risks.append(r.model_copy(update={"claim_ids": [c for c in r.claim_ids if c in known]}))
    conditions = list(dict.fromkeys(c for res in results for c in res.change_conditions))[:5]
    return CommitteeDecision(
        recommendation=Recommendation.CONDITIONAL,
        rationale=("SYNTHETIC STUB DECISION: critical facts remain unknown or unverified, so the "
                   "stub committee returns Conditional. Replace this module with the real chair."),
        conditions=conditions or ["Verify the critical unknowns listed by the roles"],
        disagreements=[], risks=risks, questions=_questions_from(results), additional_claims=[])


def make_stub_modules(use_r3_fixtures: bool = False) -> Modules:
    names = ("build_evidence_pack", "audit_claims", "analyze_science", "analyze_translation",
             "analyze_clinical", "analyze_market", "analyze_investment", "synthesize_committee")
    return Modules(
        build_evidence_pack=build_evidence_pack_r3 if use_r3_fixtures else build_evidence_pack_synthetic,
        audit_claims=audit_claims, analyze_science=analyze_science,
        analyze_translation=analyze_translation, analyze_clinical=analyze_clinical,
        analyze_market=analyze_market, analyze_investment=analyze_investment,
        synthesize_committee=synthesize_committee, origin={n: STUB_ORIGIN for n in names})