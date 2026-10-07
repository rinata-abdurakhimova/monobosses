# R5 — ip_licensing handoff, 2026-10-07

Local implementation on codex/r5-ip-licensing, based on main 6d52de8 (R2-01 merged).
No new commit/push. Shared contracts are now Pydantic; the shared LLM and report
builder still raise NotImplementedError in R2-01. This is offline readiness,
not live integration, legal accuracy or closure of a live issue.

## API

```python
from vic.agents.business.ip_licensing import analyze_ip_licensing
result = await analyze_ip_licensing(case, pack, ctx, science=None, clinical=None, market=None)
```

Required: CaseInput, EvidencePack (possibly empty), RunContext.
Optional: same-pack science/clinical/market RoleResults. No retrieval or node-to-node
calls. Exactly one ctx.model.generate_structured call. Full source/evidence records,
source synthetic flags, snapshot, case, dates, warnings and optional context are sent.
Input validation uses assert_pack and checks context snapshot, matching analysis dates,
upstream role identities and evidence references. It does not implement a historical
retrieval cutoff: R3/R2 must establish when records were actually available.

Prompt ID ip_licensing; version 1.0.0; PROMPT_PATH points to prompts/ip_licensing.md.
PROMPT_IDS and RoleId receive the additive ip_licensing value. contracts/openapi.json
is regenerated with the existing export script. No SectionKey change and no fixture
regeneration is needed: existing fixtures retain their existing valid role IDs.
R2/consumers must review the additive enum before merge.

## Output / report mapping

Shared RoleResult(role_id=ip_licensing) includes claims, risks, unknowns,
change_conditions and section_content (list). Its single SectionContent has
key=critical_unknowns and structured_data['ip_licensing'] containing:
patents, rights_and_licenses, licensable_assets, licensing_options,
freedom_to_operate, deal_data_gaps, specialist_questions, implications, coverage,
source_requests, snapshot_id, as_of_date, synthetic, prompt_version,
context_availability, claim_evidence_links, evidence_source_links,
legal_review_required=True, plus summary/position/unknowns/limitations/change_conditions.

Do not overwrite other critical_unknowns contributions when merging sections.
R2 must retain RoleResult claims/risks/unknowns and the full evidence snapshot.
Downstream partnerships and investment consume this RoleResult via the pipeline.
A report schema still has exactly 11 sections; this node is an additional role.
No orchestration/frontend wiring is implemented by this change.

## Behavior and validation

Every output domain is mandatory even when unknown. IPFinding distinguishes
supported documented values, unverified hypotheses with assumptions, and null
unknowns with an explained gap. Unknown owners, term, exclusivity and transfer
restrictions are not defaulted to free rights. Patent identifiers must be documented;
known licenses need documented rights; proposed deals are separate licensing options.
Dates are valid ISO dates when present, not estimated patent expiry calculations.
Claims cannot expand approach to program or cite nonexistent evidence; supported
program claims need program evidence. Broken nested record references, duplicate
IDs, unsupported documented fields, incomplete coverage and silent gaps are rejected.
FTO status is potential_barriers/unresolved: no clearance output is available.
Coverage of FTO documents concerns, not completion of legal analysis.
No numerical deal valuation fields exist; free text still needs semantic review.

Provider errors and invalid outputs propagate; R2 owns bounded repair/retry, timeouts,
budgets, prompt loading/version/hash traces and failed-run handling. Existence of a
citation is not proof of excerpt support. Structure does not establish hallucination
or prompt-injection protection, current patent validity, enforceability, ownership
or freedom to operate.

## Offline verification

A temporary Python venv with system site packages was used because host python lacks
pydantic-settings. No repo dependency declarations were changed.

```sh
PYTHONDONTWRITEBYTECODE=1 /private/tmp/r5-ip-licensing-venv/bin/python -m pytest services/api/tests/vic/agents/business/test_ip_licensing.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /private/tmp/r5-ip-licensing-venv/bin/python -m pytest services/api/tests -q -p no:cacheprovider
```

Results: 47 ip_licensing tests pass; 158 backend tests pass.
Checks include full/empty mocked-adapter cases, source/evidence/snapshot integrity,
upstream role/context preservation, local and program claim references, owner gaps,
territory dates/unknowns, license/asset links, hypotheses, all-domain coverage,
FTO-clear rejection, invented price-field rejection, provider failure propagation,
JSON serialization and preservation of warnings/risks/claims.

Illustrative complete-with-gaps and empty-pack outputs:
[examples/ip-licensing-synthetic.json](examples/ip-licensing-synthetic.json).
Both use fully synthetic evidence and mocked model responses. No live provider call,
real patent lookup, R3 semantic audit, legal expert review or report integration was run.

## Remaining review

- R2: register/load actual prompt; provider, pipeline and Report integration; preserve
  synthetic/date/provenance details and merge section contributions.
- R3: supply exact patent and license excerpts; audit each claimed fact, jurisdiction,
  observed status date, scope and remaining term. Missing search results ≠ absent IP.
- R4: confirm relevance of molecule, use, manufacturing and clinical context.
- Patent/legal specialist: current title/status, actual claims, transfer/sublicense
  restrictions and territorial/candidate-specific FTO.
- R5: adapt to integration findings, rerun tests and produce integrated examples.

This additional node is agreed with Uliana but is not a separately numbered task
in the original R5 issues. Team issue tracking still needs clarification; do not
close R5-01 or R5-02 because this IP implementation exists.

Learning guide: [r5-ip-licensing-guide.md](r5-ip-licensing-guide.md).
