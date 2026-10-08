# R5 Chair handoff

Base: origin/main caaa912 (verified 2026-10-09). No shared files modified.

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

## R2 integration still required

This module deliberately does NOT export synthesize_committee: current discovery
would activate it automatically, but that signature lacks case and EvidencePack.
R2 should supply an adapter/closure with positional (results, audit, ctx), capture
case/pack, map all nine RoleResults into analyze_chair, return output.decision,
and retain output.role_result among report roles. Forward all nine roles rather
than only current ROLE_ORDER. Do not invoke analyze_chair with summaries alone.
No pipeline, Modules/discovery, llm.py, Report builder, contracts, OpenAPI or UI
changes are included. End-to-end API wiring is not claimed.

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

Offline verification: 106 Chair tests and 961 backend tests pass, including
real R2 gateway via httpx.MockTransport, chair feedback/prompt hash trace,
real Failure Miner and Threshold outputs, existing upstream JSON examples, R3
new-claim audit, canonical Report assembly and JSON round-trip. Deployment tests
require permission for local sockets; no live LLM/API is called.
