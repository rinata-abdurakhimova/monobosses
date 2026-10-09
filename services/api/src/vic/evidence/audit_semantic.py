"""R3-03 (part B): LLM-assisted semantic audit on top of the deterministic audit.

Only claims that passed the structural/heuristic checks are sent to the model. The model may
downgrade such a claim, never rescue a failed one. Model unavailable => warning, not a crash.
Prompt text: evidence/prompts/audit.md (prompt id "audit").
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from vic.contracts import (
    AuditFinding,
    AuditResult,
    Claim,
    EvidencePack,
    Importance,
    RunContext,
    RunStage,
    SupportStatus,
)

from .audit import audit_claims
from .importer import ParsedDocument

PROMPT_ID = "audit"
PROMPT_VERSION = "1.0.0"
MAX_CLAIMS_PER_CALL = 12
_VERDICTS = {
    "supported": SupportStatus.SUPPORTED,
    "contradicted": SupportStatus.CONTRADICTED,
    "mixed": SupportStatus.MIXED,
    "unverified": SupportStatus.UNVERIFIED,
}
_CHECKED = (SupportStatus.SUPPORTED, SupportStatus.MIXED, SupportStatus.CONTRADICTED)


class _Verdict(BaseModel):
    claim_id: str = Field(description="Exact claim id from the input")
    verdict: str = Field(description="One of: supported, contradicted, mixed, unverified")
    reason: str = Field(description="1-2 sentences naming the specific mismatch or confirming the match, with evidence IDs")
    population: str = Field(description="Population of the cited evidence: human, animal, in_vitro, mixed, unclear")
    candidate_match: str = Field(description="same_candidate, class_level, different_candidate, unclear")
    evidence_type: str = Field(description="causal, associative, descriptive, absence_of_data, unclear")
    polarity: str = Field(description="positive, negative, mixed, unclear")


class SemanticAudit(BaseModel):
    verdicts: list[_Verdict]


def _format_items(claims: list[Claim], pack: EvidencePack) -> str:
    ev_by_id = {e.id: e for e in pack.evidence}
    sources = {s.id: s for s in pack.sources}
    blocks: list[str] = []
    for c in claims:
        lines = [
            f"CLAIM {c.id} (scope={c.scope.value}, importance={c.importance.value}, "
            f"claimed_status={c.support_status.value})",
            f"  Text: {c.text}",
        ]
        for eid in c.evidence_ids:
            ev = ev_by_id[eid]
            src = sources.get(ev.source_id)
            meta = f" | source={src.title} ({src.type})" if src else ""
            lines.append(f"  EVIDENCE [{ev.id}] scope={ev.scope.value}{meta}")
            lines.append(f"    Excerpt: {ev.excerpt}")
            if ev.limitations:
                lines.append(f"    Limitations: {'; '.join(ev.limitations)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _passed_deterministic(claim: Claim, finding: AuditFinding) -> bool:
    return bool(claim.evidence_ids) and claim.support_status in _CHECKED and finding.verdict == claim.support_status


async def audit_claims_semantic(
    claims: list[Claim],
    pack: EvidencePack,
    ctx: RunContext,
    *,
    documents: list[ParsedDocument] | None = None,
) -> AuditResult:
    """Deterministic audit + LLM semantic check. Use for specialists' claims and the chair's new claims."""
    result = audit_claims(claims, pack, documents=documents)
    eligible = [c for c, f in zip(claims, result.findings) if _passed_deterministic(c, f)]
    if not eligible:
        return result
    if ctx.model is None:
        result.warnings.append("Semantic audit not applied: no LLM adapter in the run context; only structural and heuristic checks were done.")
        return result

    index = {c.id: i for i, c in enumerate(claims)}
    for start in range(0, len(eligible), MAX_CLAIMS_PER_CALL):
        chunk = eligible[start:start + MAX_CLAIMS_PER_CALL]
        by_id = {c.id: c for c in chunk}
        payload = {"audit_items": _format_items(chunk, pack), "claim_count": len(chunk)}
        try:
            out = await ctx.model.generate_structured(PROMPT_ID, payload, SemanticAudit, ctx)
        except Exception as exc:  # model/network failure must not break the run
            result.warnings.append(
                f"Semantic (LLM) audit unavailable for {len(chunk)} claim(s) ({type(exc).__name__}); "
                "only structural and heuristic checks were applied.")
            ctx.trace.log(RunStage.AUDIT, f"semantic audit failed: {type(exc).__name__}")
            continue
        for v in out.verdicts:
            claim = by_id.get(v.claim_id)
            verdict = _VERDICTS.get(v.verdict.strip().lower())
            if claim is None or verdict is None:
                result.warnings.append(
                    f"Semantic audit: ignored an invalid verdict (claim_id={v.claim_id!r}, verdict={v.verdict!r}).")
                continue
            i = index[claim.id]
            finding = result.findings[i]
            if verdict == claim.support_status:
                result.findings[i] = finding.model_copy(update={
                    "reason": finding.reason + f" LLM-assisted semantic check agrees "
                              f"(population={v.population}, evidence_type={v.evidence_type})."})
                continue
            blocking = (claim.importance == Importance.CRITICAL
                        and verdict in (SupportStatus.CONTRADICTED, SupportStatus.UNVERIFIED)
                        and claim.support_status in (SupportStatus.SUPPORTED, SupportStatus.MIXED))
            reason = v.reason.strip() or "The model found that the cited evidence does not support the claim as worded."
            result.findings[i] = finding.model_copy(update={
                "verdict": verdict, "reason": f"LLM-assisted: {reason}", "blocking": blocking})
    result.unresolved_critical_claim_ids = list(dict.fromkeys(f.claim_id for f in result.findings if f.blocking))
    return result