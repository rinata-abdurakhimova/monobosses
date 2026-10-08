"""One canonical Report assembly: top-level fields and sections are built together from the
same objects, so they cannot disagree (contract section 2)."""
from vic.contracts import (CaseInput, Claim, ClaimChange, CommitteeDecision, EvidencePack,
                           Importance, Recommendation, Report, Revision, Risk, RoleId, RoleResult,
                           SectionContent, SectionKey, SupportStatus)
from vic.failures import ValidationFailed

# Sections whose content is written by a subject role. The other five are assembled here.
SECTION_OWNERS: dict[SectionKey, RoleId] = {
    SectionKey.SCIENTIFIC_THESIS: RoleId.SCIENCE,
    SectionKey.HUMAN_TRANSLATION_THESIS: RoleId.TRANSLATION,
    SectionKey.CLINICAL_DEVELOPMENT_PLAN: RoleId.CLINICAL,
    SectionKey.COMPETITIVE_LANDSCAPE: RoleId.MARKET,
    SectionKey.COMMERCIAL_OPPORTUNITY: RoleId.MARKET,
    SectionKey.CAPITAL_TO_MILESTONE: RoleId.INVESTMENT,
}


def _dedupe(items, key):
    seen, out = set(), []
    for item in items:
        k = key(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def _sections(roles: list[RoleResult], decision: CommitteeDecision, claims: list[Claim],
              risks: list[Risk], pack: EvidencePack) -> list[SectionContent]:
    by_key: dict[SectionKey, SectionContent] = {}
    for role in roles:
        for sc in role.section_content:
            owner = SECTION_OWNERS.get(sc.key)
            if owner is not None and (sc.key not in by_key or role.role_id == owner):
                by_key[sc.key] = sc
    critical = [c.id for c in claims if c.importance == Importance.CRITICAL]
    out: list[SectionContent] = []
    for key in SectionKey:
        if key in SECTION_OWNERS:
            sc = by_key.get(key)
            if sc is None:
                raise ValidationFailed(
                    f"The '{SECTION_OWNERS[key].value}' role did not provide the '{key.value}' section",
                    code="missing_section_content")
            out.append(sc)
        elif key == SectionKey.RECOMMENDATION:
            out.append(SectionContent(key=key, summary=decision.rationale, claim_ids=critical,
                                      limitations=list(decision.conditions),
                                      structured_data={"recommendation": decision.recommendation.value}))
        elif key == SectionKey.KEY_RISKS:
            counts = {p: sum(1 for r in risks if r.priority == p) for p in Importance}
            out.append(SectionContent(
                key=key,
                summary=(f"Ризиків: {len(risks)} (critical: {counts[Importance.CRITICAL]}, "
                         f"major: {counts[Importance.MAJOR]}, minor: {counts[Importance.MINOR]})."),
                claim_ids=_dedupe([cid for r in risks for cid in r.claim_ids], lambda x: x),
                structured_data={"risk_ids": [r.id for r in risks]}))
        elif key == SectionKey.CRITICAL_UNKNOWNS:
            unknown_claims = [c for c in claims if c.support_status == SupportStatus.UNKNOWN
                              and c.importance in (Importance.CRITICAL, Importance.MAJOR)]
            texts = _dedupe([u for role in roles for u in role.unknowns], lambda x: x)
            out.append(SectionContent(
                key=key, summary="; ".join(texts) or "Критичні невідомі ролями не зазначені.",
                claim_ids=[c.id for c in unknown_claims]))
        elif key == SectionKey.DILIGENCE_QUESTIONS:
            out.append(SectionContent(
                key=key, summary=f"{len(decision.questions)} пріоритетних питань для перевірки.",
                structured_data={"question_count": len(decision.questions)}))
        elif key == SectionKey.SOURCES:
            out.append(SectionContent(
                key=key, summary=f"Джерел: {len(pack.sources)}, доказів: {len(pack.evidence)}.",
                structured_data={"source_ids": [s.id for s in pack.sources]}))
    return out


def _revision(parent: Report, pack: EvidencePack, claims: list[Claim],
              recommendation: Recommendation) -> Revision:
    parent_ev = {e.id for e in parent.evidence}
    new_ids = [e.id for e in pack.evidence if e.id not in parent_ev]
    pc = {c.id: c for c in parent.claims}
    cc = {c.id: c for c in claims}
    changed = [ClaimChange(claim_id=cid, before=pc.get(cid), after=cc.get(cid))
               for cid in sorted(set(pc) | set(cc)) if pc.get(cid) != cc.get(cid)]
    explanation = (f"Нові докази: {', '.join(new_ids) if new_ids else 'немає'}. "
                   f"Змінені claims: {', '.join(c.claim_id for c in changed) if changed else 'жодного'}. "
                   f"Рекомендація: {parent.recommendation.value} → {recommendation.value}.")
    return Revision(parent_report_id=parent.id, new_evidence_ids=new_ids, changed_claims=changed,
                    previous_recommendation=parent.recommendation, new_recommendation=recommendation,
                    explanation=explanation)


def build_report(*, case: CaseInput, pack: EvidencePack, roles: list[RoleResult],
                 decision: CommitteeDecision, claims: list[Claim], case_id: str, run_id: str,
                 report_id: str, version: int, parent: Report | None = None,
                 synthetic: bool | None = None) -> Report:
    risks = _dedupe(decision.risks or [r for role in roles for r in role.risks], lambda r: r.id)
    sections = _sections(roles, decision, claims, risks, pack)
    return Report(
        id=report_id, case_id=case_id, run_id=run_id, version=version, scope=case.scope,
        synthetic=(synthetic if synthetic is not None
            else bool(pack.sources) and all(s.synthetic for s in pack.sources)),
        snapshot_id=pack.snapshot_id, recommendation=decision.recommendation,
        rationale=decision.rationale, decision_conditions=list(decision.conditions),
        sections=sections, roles=roles, claims=claims, evidence=pack.evidence,
        sources=pack.sources, disagreements=list(decision.disagreements), risks=risks,
        diligence_questions=list(decision.questions),
        revision=_revision(parent, pack, claims, decision.recommendation) if parent else None)