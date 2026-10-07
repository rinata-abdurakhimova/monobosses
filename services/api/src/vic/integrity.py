"""Integrity checks: dangling/forbidden IDs, section consistency, revision rules.

Each check_* function returns a list of human-readable problems (empty list = valid).
assert_* functions raise IntegrityError listing every problem. In R2-02 this is the
gate a report must pass before a run may become `completed`.
"""
from vic.contracts import (EvidencePack, Importance, Recommendation, Report, SectionKey,
                           SupportStatus)

FORBIDDEN_IDS = {"", "todo", "tbd", "unknown", "n/a", "na", "null", "none", "placeholder"}


class IntegrityError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _dups(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i in seen and i not in out:
            out.append(i)
        seen.add(i)
    return out


def _forbidden(value: str) -> bool:
    return value.strip().lower() in FORBIDDEN_IDS


def _check_ids(problems: list[str], name: str, ids: list[str]) -> None:
    for d in _dups(ids):
        problems.append(f"duplicate {name} id: {d}")
    for i in ids:
        if _forbidden(i):
            problems.append(f"forbidden {name} id: {i!r}")


def check_evidence_pack(pack: EvidencePack) -> list[str]:
    p: list[str] = []
    src_ids = [s.id for s in pack.sources]
    ev_ids = [e.id for e in pack.evidence]
    _check_ids(p, "source", src_ids)
    _check_ids(p, "evidence", ev_ids)
    if _forbidden(pack.snapshot_id):
        p.append(f"forbidden snapshot id: {pack.snapshot_id!r}")
    for e in pack.evidence:
        if e.source_id not in set(src_ids):
            p.append(f"evidence {e.id} references missing source {e.source_id}")
    if pack.synthetic:
        for s in pack.sources:
            if not s.synthetic:
                p.append(f"synthetic pack contains non-synthetic source {s.id}")
    return p


def _section(report: Report, key: SectionKey):
    for s in report.sections:
        if s.key == key:
            return s
    return None


def check_report(report: Report) -> list[str]:
    p: list[str] = []
    src_ids = [s.id for s in report.sources]
    ev_ids = [e.id for e in report.evidence]
    cl_ids = [c.id for c in report.claims]
    rk_ids = [r.id for r in report.risks]
    _check_ids(p, "source", src_ids)
    _check_ids(p, "evidence", ev_ids)
    _check_ids(p, "claim", cl_ids)
    _check_ids(p, "risk", rk_ids)
    for name, value in (("report", report.id), ("case", report.case_id),
                        ("run", report.run_id), ("snapshot", report.snapshot_id)):
        if _forbidden(value):
            p.append(f"forbidden {name} id: {value!r}")

    src_set, ev_set, cl_set = set(src_ids), set(ev_ids), set(cl_ids)

    # dangling references
    for e in report.evidence:
        if e.source_id not in src_set:
            p.append(f"evidence {e.id} references missing source {e.source_id}")
    for c in report.claims:
        for eid in c.evidence_ids:
            if eid not in ev_set:
                p.append(f"claim {c.id} references missing evidence {eid}")
    for s in report.sections:
        for cid in s.claim_ids:
            if cid not in cl_set:
                p.append(f"section {s.key.value} references missing claim {cid}")
    for r in report.risks:
        for cid in r.claim_ids:
            if cid not in cl_set:
                p.append(f"risk {r.id} references missing claim {cid}")
    canonical = {c.id: c for c in report.claims}
    for role in report.roles:
        for c in role.claims:
            if c.id not in cl_set:
                p.append(f"role {role.role_id.value} claim {c.id} is missing from report.claims")
            elif c != canonical[c.id]:
                p.append(f"role {role.role_id.value} claim {c.id} differs from report.claims")
        for sc in role.section_content:
            for cid in sc.claim_ids:
                if cid not in cl_set:
                    p.append(f"role {role.role_id.value} section {sc.key.value} "
                             f"references missing claim {cid}")

    # sections / questions
    keys = [s.key for s in report.sections]
    missing = [k.value for k in SectionKey if k not in keys]
    if missing:
        p.append(f"missing sections: {missing}")
    for k in _dups([k.value for k in keys]):
        p.append(f"duplicate section: {k}")
    if not 5 <= len(report.diligence_questions) <= 10:
        p.append(f"diligence_questions must be 5-10, got {len(report.diligence_questions)}")

    # one canonical assembly: top-level fields and sections must agree
    sec = _section(report, SectionKey.RECOMMENDATION)
    if sec and (sec.structured_data or {}).get("recommendation") != report.recommendation.value:
        p.append("section 'recommendation' does not match report.recommendation")
    sec = _section(report, SectionKey.KEY_RISKS)
    if sec and (sec.structured_data or {}).get("risk_ids") != rk_ids:
        p.append("section 'key_risks' risk_ids do not match report.risks")
    sec = _section(report, SectionKey.DILIGENCE_QUESTIONS)
    if sec and (sec.structured_data or {}).get("question_count") != len(report.diligence_questions):
        p.append("section 'diligence_questions' question_count does not match report")
    sec = _section(report, SectionKey.SOURCES)
    if sec and (sec.structured_data or {}).get("source_ids") != src_ids:
        p.append("section 'sources' source_ids do not match report.sources")

    # synthetic purity
    if report.synthetic:
        for s in report.sources:
            if not s.synthetic:
                p.append(f"synthetic report contains non-synthetic source {s.id}")

    # an Invest recommendation cannot rest on an unresolved critical claim
    if report.recommendation == Recommendation.INVEST:
        bad = (SupportStatus.UNKNOWN, SupportStatus.UNVERIFIED, SupportStatus.CONTRADICTED)
        for c in report.claims:
            if c.importance == Importance.CRITICAL and c.support_status in bad:
                p.append(f"recommendation is Invest but critical claim {c.id} is "
                         f"{c.support_status.value}")
    return p


def check_revision(parent: Report, child: Report) -> list[str]:
    rev = child.revision
    if rev is None:
        return ["child report has no revision block"]
    p: list[str] = []
    if child.case_id != parent.case_id:
        p.append("parent and child belong to different cases")
    if child.version <= parent.version:
        p.append("child version must be greater than parent version")
    if rev.parent_report_id != parent.id:
        p.append("revision.parent_report_id does not match the parent report")
    if rev.previous_recommendation != parent.recommendation:
        p.append("revision.previous_recommendation does not match the parent recommendation")
    if rev.new_recommendation != child.recommendation:
        p.append("revision.new_recommendation does not match the child recommendation")

    # previous evidence and sources are immutable inside a case
    for label, old, new in (("evidence", {e.id: e for e in parent.evidence},
                             {e.id: e for e in child.evidence}),
                            ("source", {s.id: s for s in parent.sources},
                             {s.id: s for s in child.sources})):
        for key, obj in old.items():
            if key not in new:
                p.append(f"{label} {key} from parent is missing in child")
            elif new[key] != obj:
                p.append(f"{label} {key} was modified")

    parent_ev = {e.id for e in parent.evidence}
    child_ev = {e.id for e in child.evidence}
    if set(rev.new_evidence_ids) != child_ev - parent_ev:
        p.append("revision.new_evidence_ids must equal the evidence added since the parent")
    if rev.new_evidence_ids and not any(eid in rev.explanation for eid in rev.new_evidence_ids):
        p.append("revision.explanation must cite at least one new evidence id")

    pc = {c.id: c for c in parent.claims}
    cc = {c.id: c for c in child.claims}
    differing = {cid for cid in set(pc) | set(cc) if pc.get(cid) != cc.get(cid)}
    listed = {ch.claim_id for ch in rev.changed_claims}
    if differing != listed:
        p.append(f"revision.changed_claims {sorted(listed)} != actually changed {sorted(differing)}")
    for ch in rev.changed_claims:
        if ch.before != pc.get(ch.claim_id):
            p.append(f"changed claim {ch.claim_id}: 'before' does not match the parent")
        if ch.after != cc.get(ch.claim_id):
            p.append(f"changed claim {ch.claim_id}: 'after' does not match the child")
    return p


def assert_pack(pack: EvidencePack) -> None:
    problems = check_evidence_pack(pack)
    if problems:
        raise IntegrityError(problems)


def assert_report(report: Report, parent: Report | None = None) -> None:
    problems = check_report(report)
    if parent is not None:
        problems += check_revision(parent, report)
    if problems:
        raise IntegrityError(problems)