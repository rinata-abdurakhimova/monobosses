# R5 Chair handoff

Current state (2026-10-09): Chair is connected in main `a060c26` through R2's
`vic/committee.py` bridge. Full live quality remains unverified.
Original implementation base: caaa912; R5 did not change shared runtime files.

`await analyze_chair(case, pack, ctx, science=..., translation=..., clinical=...,
market=..., investment=..., partnerships=..., ip_licensing=...,
investment_threshold=..., failure_miner=..., audit=...)` returns `ChairResult`:

- `.decision`: existing shared CommitteeDecision for Report/pipeline.
- `.role_result`: shared RoleResult with full `section_content[0].structured_data["chair"]`.

All nine inputs accept RoleResult, JSON dictionary or None. Audit accepts
AuditResult/dictionary/None. Missing input is explicit, never silently fabricated.
Complete serialized upstream results, complete source/evidence objects, nested
financial plans/calculations/sensitivities and Failure Miner/Threshold structures
are sent to one generate_structured("chair", ..., ChairAnalysis, ctx) call.
An inventory requires explicit considered/deferred dispositions for claims, risks,
summaries, positions, sections, identified records, questions, unknowns, change conditions and nested
limitations/source requests. Deferred entries need reasons. This checks structural
coverage; it cannot prove the LLM understood every value or made sound judgments.

The full output preserves both argument sides, evidence weights, conditions,
conflicts, risks, critical unknowns, change triggers, ranked questions and input
reviews. claim_evidence_links -> evidence_source_links -> complete sources/excerpts
provide evidence navigation. source_requests and RoleResult.unknowns retain nested
gaps and missing contexts. Questions, conditions and conflicts in CommitteeDecision
are projected from the same validated rich analysis. Detailed methods/ranks and
links remain in the role record. Chair risks exist canonically in decision.risks;
role_result.risks is empty to avoid conflicting canonical records when a risk cites
upstream claims (shared role integrity expects local claim refs).

## Current R2 integration

The business module does not export the old positional synthesize_committee.
R2's `vic/committee.py` supplies the bridge with results/audit/ctx and keyword
case/pack; it maps all upstream roles into analyze_chair. Pipeline retains both
ChairResult.decision and ChairResult.role_result among Report roles.
All nine upstream roles are wired; summaries alone are not used.
See [R2 full workflow handoff](r2-full-workflow-handoff.md).

Offline HTTP/provider-fixture integration is verified; this does not demonstrate
sound reasoning by a real model. New Chair claims still require final R3 audit.

Existing load_prompt finds chair.md. StructuredLlm forwards chair feedback and
records prompt hash. New chair claims go through R3's existing additional_claims
audit path. Existing Report builder preserves the full analysis in report.roles
when R2 supplies role_result; top-level recommendation only exposes its current
canonical fields. No live LLM/API calls are used in offline validation.

Invest structurally requires complete contexts, dated evidence and audit with no
blockers plus decisive documented support. Missing data alone cannot justify
Do Not Invest. Conditional conditions have pass/fail/inconclusive handling.
Synthetic data is retained and is not evidence for an actual investment.
Semantic review of evidence weighting, scientific validity, finances and legal
interpretations remains necessary. Merge conflicts depend on later branch edits;
four new owner-local files minimize overlap but cannot guarantee future merges.

Inventory contains stable input paths and kinds only; full values are sent once
in upstream_context, avoiding duplication of large financial/scientific sections.
Invest also requires audit coverage of decisive and critical upstream claims,
supported critical claims and no unknown domain assessments.

Historical implementation verification: 106 Chair tests and 961 backend tests passed, including
real R2 gateway via httpx.MockTransport, chair feedback/prompt hash trace,
real Failure Miner and Threshold outputs, existing upstream JSON examples, R3
new-claim audit, canonical Report assembly and JSON round-trip. Deployment tests
require permission for local sockets; no live LLM/API is called.

Latest recorded backend regression suite: 970 passed (2026-10-09).
[Evaluation content](../evals/README.md) includes decisive, irrelevant and
relevant non-decisive revisions; expectations review and live outputs are pending.
