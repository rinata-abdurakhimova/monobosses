"""R3-03 (part A): deterministic claim -> evidence audit.

Structural checks: cited evidence exists, its source is in the pack, locator/excerpt are real
(when parsed documents are supplied), provenance has a basis.
Heuristic semantic checks (cheap, explainable, NOT a substitute for review): animal evidence cited for a
human claim, association evidence cited for a causal claim, approach-level evidence cited for a
program-level claim, cited excerpt sharing no terms with the claim.

Same function audits specialist claims and the chair's new claims (just pass them in).
Blocking = a CRITICAL claim that is presented as supported/sourced but fails a check. An honestly
labelled unknown/unverified claim is a gap, not a blocker.
"""
from __future__ import annotations

import re

from vic.contracts import (
    AuditFinding,
    AuditResult,
    Claim,
    Evidence,
    EvidencePack,
    Importance,
    Provenance,
    Scope,
    SupportStatus,
)

from .importer import ParsedDocument
from .normalization import excerpt_in_text

_HUMAN = re.compile(
    r"\b(humans?|patients?|participants?|volunteers?|women|adults?|"
    r"clinical (?:trial|efficacy|benefit)s?|phase (?:1|2|3|i{1,3}))\b", re.I)
_ANIMAL = re.compile(
    r"\b(mouse|mice|murine|rats?|animals?|nonhuman|dogs?|canines?|primates?|monkeys?|"
    r"zebrafish|in vitro|cell lines?|cultured cells?|xenografts?)\b", re.I)
_CAUSAL = re.compile(r"\b(causes?|caused|causal(?:ly)?|drives?|leads? to|proves?|validat\w+|establish\w*)\b", re.I)
_ASSOC = re.compile(r"\b(associat\w*|correlat\w*|linked)\b", re.I)
_NEG_CAUSAL = re.compile(r"\b(?:not|no|cannot|without|neither)\b[^.]{0,40}caus", re.I)
_WORD = re.compile(r"[a-z0-9][a-z0-9-]{3,}")
_STOPW = {"that", "this", "with", "from", "have", "been", "were", "which", "their", "than", "into",
          "such", "also", "only", "more", "most", "will", "would", "could", "should", "about"}


def _cap(text: str) -> str:
    """Capitalize only the first letter (str.capitalize() would lowercase the rest, e.g. 'AI')."""
    return text[:1].upper() + text[1:]


def _norm(text: str) -> str:
    return re.sub(r"non-human", "nonhuman", text, flags=re.I)


def _terms(text: str) -> set[str]:
    return {w.rstrip("s") for w in _WORD.findall(text.lower()) if w not in _STOPW}


def _is_animal_only(ev: Evidence) -> bool:
    excerpt = _norm(ev.excerpt)
    lims = _norm(" ".join(ev.limitations))
    return bool(_ANIMAL.search(excerpt) or _ANIMAL.search(lims)) and not _HUMAN.search(excerpt)


def _is_association_only(ev: Evidence) -> bool:
    text = ev.excerpt + " " + " ".join(ev.limitations)
    return bool(_ASSOC.search(text)) and (not _CAUSAL.search(ev.excerpt) or bool(_NEG_CAUSAL.search(text)))


def _semantic_issues(claim: Claim, cited: list[Evidence]) -> list[str]:
    issues: list[str] = []
    claim_text = _norm(claim.text)
    ids = ", ".join(e.id for e in cited)
    if _HUMAN.search(claim_text) and not _ANIMAL.search(claim_text) and all(_is_animal_only(e) for e in cited):
        issues.append(
            f"population mismatch: the claim is about humans/patients but the cited evidence ({ids}) "
            "describes animal or in vitro data only")
    if _CAUSAL.search(claim.text) and all(_is_association_only(e) for e in cited):
        issues.append(
            f"association cited as causal: the claim asserts causation but the cited evidence ({ids}) "
            "reports association/correlation only")
    if claim.scope == Scope.PROGRAM and all(e.scope == Scope.APPROACH for e in cited):
        issues.append(
            f"scope mismatch: the claim is about the specific program but the cited evidence ({ids}) "
            "is approach-level")
    claim_terms = _terms(claim.text)
    evidence_terms = set().union(*(_terms(e.excerpt) for e in cited))
    if len(claim_terms) >= 3 and not claim_terms & evidence_terms:
        issues.append(
            f"possible misattribution (heuristic): the cited excerpt(s) {ids} share no key terms with the claim")
    return issues


def _structural_issues(
    claim: Claim, ev_by_id: dict[str, Evidence], source_ids: set[str], docs: dict[str, ParsedDocument]
) -> tuple[list[str], list[Evidence]]:
    issues: list[str] = []
    cited: list[Evidence] = []
    missing = [i for i in claim.evidence_ids if i not in ev_by_id]
    if missing:
        issues.append("cites evidence that does not exist in the pack: " + ", ".join(missing))
    for i in claim.evidence_ids:
        ev = ev_by_id.get(i)
        if ev is None:
            continue
        cited.append(ev)
        if ev.source_id not in source_ids:
            issues.append(f"{ev.id} points to source {ev.source_id}, which is not in the pack")
            continue
        doc = docs.get(ev.source_id)
        if doc is not None:
            unit = doc.unit_by_locator(ev.locator)
            if unit is None:
                issues.append(f"{ev.id}: locator {ev.locator!r} does not exist in the source document")
            elif not excerpt_in_text(ev.excerpt, unit.text):
                issues.append(f"{ev.id}: excerpt does not appear at locator {ev.locator!r} (altered or invented)")
    return issues, cited


def _audit_one(
    claim: Claim, ev_by_id: dict[str, Evidence], source_ids: set[str], docs: dict[str, ParsedDocument]
) -> AuditFinding:
    critical = claim.importance == Importance.CRITICAL
    issues, cited = _structural_issues(claim, ev_by_id, source_ids, docs)
    asserts_support = claim.support_status in (SupportStatus.SUPPORTED, SupportStatus.MIXED)
    if asserts_support and cited:
        issues += _semantic_issues(claim, cited)

    if (claim.provenance == Provenance.AI and not claim.evidence_ids and not claim.assumptions
            and claim.support_status != SupportStatus.UNKNOWN):
        issues.append("AI inference has neither cited premises nor stated assumptions; its reasoning cannot be inspected")

    base = dict(claim_id=claim.id, evidence_ids=list(claim.evidence_ids))
    if issues:
        return AuditFinding(verdict=SupportStatus.UNVERIFIED, reason=_cap("; ".join(issues)),
                            blocking=critical, **base)
    if claim.provenance == Provenance.USER and not claim.evidence_ids:
        return AuditFinding(verdict=SupportStatus.UNVERIFIED, blocking=False, **base,
                            reason="User-provided assertion without evidence; it is not independently verified.")
    if claim.support_status == SupportStatus.UNKNOWN:
        return AuditFinding(verdict=SupportStatus.UNKNOWN, blocking=False, **base,
                            reason="The claim states a data gap; no supporting evidence is required.")
    if claim.support_status == SupportStatus.UNVERIFIED:
        return AuditFinding(verdict=SupportStatus.UNVERIFIED, blocking=False, **base,
                            reason="The claim is explicitly marked unverified and is presented as such.")
    return AuditFinding(
        verdict=claim.support_status, blocking=False, **base,
        reason=(f"Structural checks passed for {len(cited)} cited evidence item(s). Semantic checks are "
                "heuristic (population, scope, causality); critical claims still need manual review."))


def audit_pack_structure(pack: EvidencePack, docs: dict[str, ParsedDocument] | None = None) -> list[str]:
    """Pack-level problems, independent of any claim."""
    warnings: list[str] = []
    source_ids = {s.id for s in pack.sources}
    seen: set[str] = set()
    for ev in pack.evidence:
        if ev.id in seen:
            warnings.append(f"Duplicate evidence id {ev.id} in the pack.")
        seen.add(ev.id)
        if ev.source_id not in source_ids:
            warnings.append(f"Evidence {ev.id} references unknown source {ev.source_id}.")
    return warnings


def audit_claims(
    claims: list[Claim], pack: EvidencePack, *, documents: list[ParsedDocument] | None = None
) -> AuditResult:
    """Audit any list of claims (specialists' or the chair's new claims) against the pack.

    Pass `documents` (ParsedDocument list from the import/retrieval step) to also verify that
    every cited excerpt literally exists at its locator.
    """
    docs = {d.source_id: d for d in documents or []}
    ev_by_id = {e.id: e for e in pack.evidence}
    source_ids = {s.id for s in pack.sources}
    result = AuditResult(warnings=audit_pack_structure(pack, docs))
    for claim in claims:
        finding = _audit_one(claim, ev_by_id, source_ids, docs)
        result.findings.append(finding)
        if finding.blocking:
            result.unresolved_critical_claim_ids.append(claim.id)
    return result