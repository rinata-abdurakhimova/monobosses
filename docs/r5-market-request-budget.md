# Market split and request budget — 2026-10-09

Implementation baseline: `origin/main` at `68ece19479130862cc4ceeb957af3c5326c880f8`.
Branch: `codex/r5-market-request-budget`. Related: #51, #6, #7, #14.
This handoff supersedes the single-call runtime description in r5-01-handoff.md.
No commit, push, PR or real provider call was made for this change.

## Runtime and public compatibility

`await analyze_market(case, pack, ctx, scenarios=..., clinical=...)` still returns
`RoleResult(role_id="market")`. Public contracts, pipeline, Report builder,
OpenAPI and frontend code are unchanged.

Two independent task streams execute concurrently via asyncio. Each calls the
existing `ctx.model.generate_structured`; batches inside a stream are sequential.
Planning both streams completes before any provider call. On failure/cancellation,
the sibling is cancelled and awaited (transport cancellation cannot guarantee
that a remote provider stops processing/billing a request already accepted).

| Prompt ID / file | Response schema | Version / content hash |
| --- | --- | --- |
| market_competitive / market_competitive.md | CompetitiveAnalysis | 2.0.0 / 3608ce2034f7 |
| market_commercial / market_commercial.md | CommercialAnalysis | 2.0.0 / e5d08dc5218d |

Both IDs are registered in `vic.prompts.ALIASES` and `vic.llm.PROMPT_IDS`, and
visible in `check_wiring.py`. Legacy `market.md` is retained for historical
comparison; the node no longer calls it. Trace usage retains each new prompt
hash, model, tokens when supplied, latency, retries and nullable cost. Missing
provider usage/prices marks cost unavailable; it is never reported as zero.

Python joins the validated pass objects into MarketAnalysis, then runs the
existing validator against the original pack and builds both unchanged sections:
`competitive_landscape` and `commercial_opportunity`. No final synthesis LLM call.
Investment, Chair, IP/licensing and Partnerships continue consuming a market role.

## Inputs, evidence coverage and R4 context

Market receives CaseInput, the shared EvidencePack and optionally Clinical; it
does not directly receive Science/Translation results. Pipeline still does not
supply numeric scenarios automatically.

R4 projection retains population, comparator/standard of care, unmet need,
safety, biomarker eligibility, regulatory context, linked risks, unknowns, change conditions and section limitations.
Competitive projection additionally retains endpoints. Known noncritical study
planning claims are excluded with their IDs and an explicit reason. Critical,
custom and risk-linked claims are retained conservatively. Selected claims retain
support labels, evidence links and assumptions. Relevant section fields without
claims remain explicitly unverified context. Full report sections, nested
upstream copies and the clinical thesis are never copied. Input availability
is not confirmation of semantic clinical alignment; R4/R3 review is still needed.

Source metadata is represented once per original source ID in a batch. Exact
excerpts, original IDs, locators, dates, types, scope, synthetic flags and
limitations are preserved. There is no new retrieval and no quotation truncation.

**Evidence-selection decision:** free-text Evidence records currently have no
reviewed task labels. Both task streams therefore review every supplied evidence
record in bounded batches. Their schemas, projected clinical context and numeric
inputs differ, but evidence is intentionally shared where relevance cannot be
established safely. No keyword filter or first-N cutoff silently excludes safety,
contradictions, numeric-input evidence or last-page findings. Coverage metadata
records total count and partial-batch status. This trades extra calls/time/cost
for preserved coverage. A later R3-reviewed routing map can reduce duplication;
it is not part of this fix. An oversized exact excerpt fails clearly, asking R3
for a smaller provenance-preserving unit instead of cutting the quote.

Reviewed scenarios go only to the commercial task. Arithmetic remains in
calculations.py; report values retain assumptions, original input evidence links,
units, missing inputs, zero values and separate currency/geography/date ranges.
Model-extracted numbers never become reviewed scenario inputs automatically.

## Deterministic merge and audit

Claims are namespaced as `market.competitive_<key>_<evidence_hash>` or
`market.commercial_<key>_<evidence_hash>`, compatible with the shared one-dot
ClaimId contract. Hashes use sorted evidence IDs, not model prose/batch indices.
Same-key/same-evidence claims with differing contents fail as collisions.
Distinct contradictory evidence remains distinct. Exact duplicate facts across
streams are deduplicated and every claim reference remapped. Identical risks and
questions are deduplicated; differing facts/descriptions are not silently chosen.
Conflicting population/value descriptions or competitor statuses survive with
explicit reconciliation gaps. This is structural validation, not a truth check.

Aggregate position is favorable only when all pass/batch positions are favorable
and important coverage/price/population/access/value gaps or material conflicting
claims are absent. All-unfavorable positions remain unfavorable; an insufficient
pass yields insufficient_data, and other disagreements yield mixed. A favorable
result with missing competitor categories is downgraded to insufficient_data;
other unresolved material conflicts/gaps downgrade it to mixed. Batch-local
unknowns are retained conservatively, so large packs may need semantic review to
resolve gaps that another batch answers; no majority vote declares positivity.

The adapter maps both prompt IDs to `ctx.feedback["market"]`. Because deduplicated
claims may support both sections, findings are forwarded to both streams with
merged IDs normalized to local semantic keys. Child contexts have independent
feedback containers and shared trace/budget, avoiding concurrent feedback writes.
Schema repair history and audit feedback count toward the same byte budget.

## Budget and measured sizes

`MARKET_REQUEST_MAX_BYTES` / Settings.market_request_max_bytes defaults to 18,000
UTF-8 bytes. Initial calls use at most 75% (13,500 bytes), leaving repair headroom.
This is a **provisional application cap**, not an observed numerical gateway
limit. Live acceptance and headroom calibration remain required with R2.
No output allowance is increased; the existing default remains 4096.

The same serializer is used for batch planning and actual adapter calls.
Measurements cover the compact prompt/schema, payload, feedback/repair messages,
message envelopes, model name, output allowance and stream flag of the
OpenAI-compatible JSON body. Credentials/headers and raw private texts are not
logged. Logs contain sizes, budgets and evidence IDs, including separate
case/evidence/source/clinical/scenario sizes. Bytes/characters are not tokens.
No selected-model tokenizer is installed in the test environment; provider token
usage is recorded only when returned.

Oversized evidence is batched. An oversized schema/case/clinical/audit base or
single indivisible excerpt fails before any call. An oversized schema-repair
request fails before that request is sent, without repeating/truncating it.
Unbounded case program_data or clinical unknowns can therefore still require
upstream preparation. Configuring an impossibly small budget fails clearly.

Offline measurements reconstructed the original main implementation using
labelled synthetic fixtures and the same compact adapter serialization;
these are not measurements of Rinata's private failing request or live limits.
The model string `gpt-5-mini` was used only for envelope serialization; no model
was contacted. Both fixtures include one reviewed synthetic numeric scenario.

| Synthetic fixture | Original full request bytes | Competitive max bytes / calls | Commercial max bytes / calls |
| --- | ---: | ---: | ---: |
| 1 evidence item | 15,733 | 7,377 / 1 | 9,274 / 1 |
| 32 evidence items + Clinical | 57,697 | 12,586 / 8 | 13,377 / 10 |

Original compact schema: 7,295 bytes; split schemas: 4,243 and 5,240 bytes.
Original prompt: 5,584 bytes; split prompts: 1,386 and 1,416 bytes.
See [size data](r5-market-request-sizes.json) for component measurements. A split
reduces the maximum individual request, not necessarily total billed input.

## Requirement coverage

| Market requirement | Preserved output / implementation |
| --- | --- |
| Target patients, indication, eligibility, geography, access restrictions | commercial.target_population; R4 projection and unknowns |
| Standard of care, approved, clinical-stage, same-target, alternatives, discontinued | competitive competitors + all six coverage categories |
| Discontinuation reason or explicit unknown | competitor reason fields and evidence-linked claims |
| Additional benefit versus each comparator | competitive differentiation with claim/evidence links |
| Eligible/accessibly treated patients or gap | Python eligible_patients/addressable_patients and source_requests |
| Comparable prices and limitations | pricing_analogues, pricing_unknowns |
| Reimbursement, prescribing and access barriers | access + target population access_limitations |
| Reviewed numeric scenarios, assumptions, ranges | calculations.py output; scenario_ranges and original input evidence |
| Unmet need / willingness to pay | commercial_value, with explicit missing-data gaps |
| Risks, unknowns, checks and evidence | merged claims/risks/unknowns/change_conditions/questions/source_requests |

## Offline validation commands

Run from repository root (Python venv is local, not a team dependency):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/api/src /private/tmp/r5-ip-licensing-venv/bin/python -m pytest services/api/tests -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/api/src /private/tmp/r5-ip-licensing-venv/bin/python services/api/scripts/check_wiring.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/api/src /private/tmp/r5-ip-licensing-venv/bin/python services/api/scripts/measure_market_requests.py
```

From apps/web:

```sh
npm test
npm run typecheck
npm run contracts:check
```

Regression tests cover overlapping calls and sibling cancellation, distinct
schemas, R4 projection, missing pricing, all output fields, unknown discontinued
reason, provenance and numeric scenarios, stable IDs and collisions, deduplicated
facts, multiple batches, a decisive final contradiction, batch-local citations,
actual shared-adapter serialization, schema repairs, audit reruns, oversized
feedback/repair rejection and unavailable cost. The deterministic-provider HTTP
workflow runs all real nodes and confirms Market → downstream report flow with
both rich sections and unchanged revisions.

## Evaluation baseline

The existing dataset-lock correctly rejected changed Market/adapter hashes.
Its code baseline is refreshed for this branch's uncommitted code and the previous
baseline preserved in code_baseline_history. New prompt/config/loader hashes are
included. Dataset 1.0.0 case inputs, packs, expectations and rubric hashes remain
unchanged; R3/R4/R5 semantic review and live model/config freezing remain pending.
Offline content/provenance/retrieval and arithmetic validation is rerun, with no
model calls or holdout outcomes used for tuning.

## Live status and R2 handoff

**Not live verified.** No mentor gateway, API keys or private request bodies were
used. Do not close #51/#6 based on offline tests or claim complete live committee
success. Required separately authorized checks: a small labelled synthetic Market
run, a larger pack + Clinical, audit/schema repair, then R2's integrated HTTP
pipeline through Market to the next node. Record commands, actual model and prompt
hashes, maximum request/repair sizes, usage and outcome; calibrate the application
cap with headroom from observed acceptance. Parallel gateway acceptance/rate
limits also need confirmation. Other large nodes may still exceed gateway limits.

## Recorded final offline results

- Backend + evaluation dataset tests: **995 passed** (984 backend, 11 dataset).
- Frontend tests: **40 passed**; TypeScript and generated-contract checks passed.
- check_wiring.py: all node signatures compatible, both new prompts resolved.
- Dataset validator: 21 cases, 18 families, 8 numeric probes, zero model calls.
- git diff --check passed; final fetch still resolves origin/main to 68ece19.
- No real gateway run, commit, push or merge. Codex.code-workspace remains untouched.
