"""One canonical Report assembly (top-level fields and sections built together).

STUB in R2-01; implemented in R2-02 (issue #7).
"""
from vic.contracts import (
    AuditResult,
    CaseInput,
    CommitteeDecision,
    EvidencePack,
    Report,
    RoleResult,
)


def build_report(case: CaseInput, pack: EvidencePack, roles: list[RoleResult],
                 audit: AuditResult, decision: CommitteeDecision, *, case_id: str, run_id: str,
                 version: int) -> Report:
    raise NotImplementedError("Report builder is implemented in R2-02 (#7)")