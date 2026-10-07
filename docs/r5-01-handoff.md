# R5-01: local market node

Branch: `codex/r5-01-market`. Scope: market/competitor analysis only.

## Files and execution

- `services/api/src/vic/agents/business/market.py`: structured model schema,
  input preparation, single adapter call, validation, grouping and report assembly.
- `services/api/src/vic/agents/business/calculations.py`: Decimal scenarios.
- `services/api/src/vic/agents/business/prompts/market.md`: versioned LLM instructions.
- `services/api/tests/vic/agents/business/test_market.py`: offline regression tests.

From the repository root, with Python, Pydantic 2, pytest and pytest-asyncio:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest services/api/tests -q -p no:cacheprovider
```

No external model requests are made by these tests. They use an AsyncMock adapter.
No API client, model key, RAG retriever or LangGraph dependency is introduced here.

## R2 integration

Call `await analyze_market(case, pack, ctx)` with the common evidence pack.
The node calls exactly:
`await ctx.model.generate_structured("market", payload, MarketAnalysis, ctx)`.
Register `prompts/market.md` for this prompt ID, including version/hash in traces.
Provider and model choice remain in the shared adapter; none is hardcoded here.
The current repository has no working R2 adapter or API runtime, so live model
execution has not been verified. Invalid outputs raise exceptions; bounded
repair/retries, budgets and failed-run handling belong to R2.

Current `vic/contracts.py` explicitly says it is a temporary R4 test contract.
It defines singular `section_content`. We preserve it without modifying another
owner's module. Both canonical report sections are available under
`result.section_content.structured_data["sections"]`: competitive_landscape and
commercial_opportunity. R2 must map these to final SectionContent models when
finalizing the shared contract. No Invest recommendation is issued here.

## Numeric inputs

Optional keyword `scenarios=[MarketScenario(...)]` accepts caller-reviewed inputs,
not model-extracted numbers. All populated numeric inputs require IDs from the
pack; this checks existence, not whether the evidence supports the numeric value.
Review number provenance, currency, annual price units, geography, date and
assumptions before passing inputs. The schema uses annual price per patient and
fractions in [0,1]. Missing input produces null, a known zero produces zero.
Decimal arithmetic is serialized as strings to avoid binary floating-point drift.
Each scenario retains its own currency/geography/date; scenarios are not summed
or currency converted. Population × eligibility × access × annual price is a
simplified opportunity scenario, not sales, profit or investment return.
Without reviewed inputs, no numeric estimate is produced and source requests
are returned. Choosing inputs from evidence automatically is future work.

## Responsibility and limitations

R3 retrieves evidence. This node keeps all supplied excerpts and limitations so
keyword filtering does not silently remove a safety warning. R3/R2 must bound
pack size and enforce as-of availability before invocation. Synthetic source
flags are carried into payload and result metadata.

Python rejects unknown evidence/claim IDs, contradictory competitor status,
duplicate IDs, invalid scope and unsupported comparator references. The LLM
performs substantive competitor extraction and differentiation; helper functions
organize its output. JSON validation is not a factual correctness guarantee.
Prompts prohibit invented prices and embedded document instructions, but these
properties need semantic audit and adversarial/live evaluation; offline structural
tests do not prove prompt-injection resistance or absence of hallucinations.
R3 must audit summaries, competitor statuses and claim-to-excerpt support. The
chair must consume only appropriately audited outputs. A listed citation alone
must never count as proof.

No investment/chair node or R5-04 dataset implementation is included in this step.

## Target population (introduced in v1.1.0)

MarketAnalysis now requires TargetPopulation: description, eligibility,
geography, access_limitations, claim_ids and unknowns. Missing description and
geography are null; absent criteria/barriers are empty lists. Population-specific
unknowns flow into RoleResult.unknowns/source_requests. Nonempty descriptions
require claim references, and unknown references are rejected. R3 must audit
semantic support; R4 reviews clinical eligibility. The block is returned in
commercial_opportunity.structured_data.target_population. Update fixtures/model
responses to include this required block. See r5-output-coverage.md for scope.


## Market schema v1.2.0 (required response update)

The structured response now requires competitive_coverage for all six categories,
pricing_analogues/pricing_unknowns, access, commercial_value and at least one
structured diligence_question. TargetPopulation adds indication. Every Competitor
adds discontinuation_reason (nullable), discontinuation_reason_claim_ids and
 discontinuation_unknowns. Old model fixtures must be updated; missing required
fields fail validation rather than silently omitting requested outputs.

Pass optional `clinical=clinical_role_result` to analyze_market for explicit R4
context. It must have role_id="clinical" and evidence IDs in this pack. The
serialized upstream result is included in the payload; the prompt requests
reconciliation, not automatic confirmation. Without it clinical_alignment and
source_requests explicitly say R4 review is pending. Semantic agreement requires
R4/R3 review. The function never calls another node.

commercial_opportunity structured_data includes pricing_analogues, pricing_unknowns,
access, commercial_value, addressable_patients, scenario_ranges and diligence_questions.
competitive_landscape includes coverage and diligence_questions. Questions are
market contributions, not the chair's final 5–10. R2 should deduplicate them when
assembling the Report. Risks still use the existing shared Risk contract.

Calculations now separately preserve eligible_patients (population × eligibility)
and accessible patients (including access_fraction). Existing addressable_patients
in each scenario retains its accessible-patient meaning. scenario_ranges groups
complete scenarios by currency/geography/date and gives minimum/maximum values.
It does not mix currencies/regions/dates or imply confidence intervals. A single
complete scenario produces equal bounds, not a fabricated downside/upside range.

Pricing descriptions can reproduce supplied facts, but scenario inputs remain
caller-reviewed. Citation existence is not proof of numerical or semantic support.
Unknown prices, discontinuation reasons and commercial willingness to pay must
stay explicit. Empty evidence cannot establish a positive commercial assessment.

Validation: 47 offline tests pass (entire services/api/tests), including new output
assembly, missing-data errors, invalid references, range grouping and R4 context.
The offline tests make no provider calls. Separate temporary Gemini attempts are
recorded below; no valid model output was obtained. R5-01 must not be marked
live-complete from these mock tests alone.


## Handoff status — 2026-10-07

Local R5 implementation is ready for review/commit and team integration. This is
not confirmation that the full live issue is complete. No commit or push was
created during this documentation update. Code, tests and prompt are local on
`codex/r5-01-market`; inspect the current git status before staging.

Latest user-run command above: `47 passed in 0.15s` (40 business/market tests,
7 science/translation tests in this local checkout). This verifies structure,
links, calculations and mock assembly, not semantic generation quality.

### Separate Gemini experiment

A temporary adapter outside the repository read the actual market prompt and
called the actual node with explicitly synthetic evidence. It did not use the
hackathon gateway or team budget. Credentials are not part of this handoff.
Initial TLS certificate setup was repaired in the temporary adapter. Gemini
2.5 Flash returned HTTP 404 (unavailable to new users). Access to Gemini 3.8 Flash
was confirmed by a model metadata request, but generation timed out at 180 and
300 seconds; a final JSON-only attempt without provider schema enforcement also
timed out at 60 seconds. No successful MarketAnalysis/RoleResult was obtained.
Cause remains unknown; this is neither a demonstrated market-code defect nor
proof of working live integration. Attempts were stopped. Exact token usage or
Google billing was not verified; a timeout alone does not establish zero usage.

### Team dependencies and acceptance

| Owner | Required integration work | Acceptance evidence |
| --- | --- | --- |
| R2 | Register market.md v1.2.0; implement generate_structured; provider schema handling, bounded timeouts/retries/repair, budgets and tracing | Actual valid model response plus recorded failure behavior |
| R2 | Finalize contracts; move BOTH nested sections into Report.sections; retain RoleResult.claims/risks/unknowns/change_conditions and pack sources/evidence | End-to-end report without dropped fields or broken links |
| R3 | Supply shared evidence pack with exact excerpts, provenance, dates and limitations; audit claim-to-excerpt support | Audited real claims; missing data remains explicit |
| R4 | Supply clinical RoleResult from the same evidence snapshot; reconcile population, eligibility, comparator and required benefit | Reviewed agreement or explicit unresolved conflicts |
| R1 with R2 | Map detailed structured_data to the final UI; support contradicted claims and accurate source/synthetic labels | Competitors, pricing, access, scenarios and evidence are visible |

The new clinical module is published in GitHub main (reviewed commit a527dc1),
but is not in this local checkout; this update does not merge it. A real R4 →
market execution has not been tested. Current asdict(clinical) relies on dataclass
contracts and must be adapted if R2 changes RoleResult to Pydantic.
clinical_alignment records input availability, not verified clinical agreement.

Missing-data caveat: the generic no-scenarios gap mentions unknown pricing even
when qualitative pricing analogues may exist. Treat this as missing reviewed
numeric scenario inputs; do not discard the analogue facts.

### Review/staging scope

Include README, this handoff, r5-output-coverage, docs/roles/r5-investment,
docs/issues/r5-01, business/__init__.py, market.py, calculations.py,
prompts/market.md and tests/vic/agents/business/test_market.py (10 files after
this documentation update). Exclude Codex.code-workspace, API keys, environment
files, bytecode and temporary Gemini adapters/results. Stage explicit paths,
not the whole business directory. No provider-specific adapter is required in
this R5 commit. Next independent implementation: investment; unavailable upstream
nodes can be represented by clearly labelled fixtures or explicit gaps.
