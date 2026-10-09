# R5 investment — two-stage handoff

Current state (2026-10-09): the node is in main and wired by R2 in `a060c26`.
[Full workflow handoff](r2-full-workflow-handoff.md) records offline integration
and live limitations. Original implementation branch was `codex/r5-investment`.
The node prepares financial inputs from clinical context and evidence before
performing deterministic arithmetic; live semantic quality remains unverified.

## Entry point and output

```python
await analyze_investment(case, pack, ctx, clinical=..., market=...,
    partnerships=..., ip_licensing=..., scenarios=..., stresses=...)
```

case/pack/ctx required; four upstream RoleResult/JSON inputs optional with gaps.
scenarios/stresses are optional caller-supplied inputs, not prerequisites. They
are preserved without duplication; the first model must use their milestone/work IDs.
The node itself does no retrieval, upstream calls, outreach or final recommendation.

Shared output remains RoleResult(role_id="investment"), existing section
capital_to_milestone; full map:
`result.section_content[0].structured_data["investment"]`.
All ten requirements remain present: next result/work, capital/time, value events,
future financing, three paths, partnerships/IP dependencies, three stress kinds,
risks, unknowns, evidence links and decision-changing checks.

## Two adapter calls with disjoint schemas

1. `investment_plan` / 1.0.0 / PreparedInvestmentPlan: milestone, work,
   future-stage identities, incremental stress triggers, null numeric blueprints
   and source-bound operands/bindings. No financial narrative or final recommendation.
2. Python verifies quotes, nonnegative numeric tokens, dimensions/currency and
   plan consistency; copy/quantity-times-price are the only permitted operations.
   It constructs ReviewedRange/CostItem/ScheduleTask/InvestmentScenario/StressScenario
   and computes budgets, dependency-path time, funding gaps and stress increments.
3. `investment` / 2.0.0 / InvestmentExplanation: financial interpretation of
   the fixed plan and calculations, not new work, stages, triggers or numerical inputs.
   Python inserts fixed records into InvestmentAnalysis and then RoleResult.

Invalid planning data stops before call 2. No automatic retry/replanning loop in
this node; shared adapter retry behavior belongs to R2. Second schema forbids
replacement plan fields; duplicate planning claim/risk IDs and unknown stage/event
references are rejected. Detached adapter payloads prevent accidental mutation of
canonical records. fixed_plan_hash identifies the fixed narrative plan (not a
semantic audit or a hash of all source/numeric metadata).

Numeric provenance preserves target path, quote, source tokens, units, operation,
applicability/assumptions and Python-resolved range. All new extraction remains
`source_tokens_checked_semantic_review_pending`; overall numeric_review_status
is semantic_review_pending, including supplied inputs. Source-token equality does
not establish applicability, legal truth, complete budget scope or factual accuracy.
Partial capital stays null with known subtotal. Diligence remains separate.
Known baseline delays are not numeric stresses; numeric stresses require incremental
triggers tied to work. No mandatory three invented numeric scenarios.

## Integration owners

- R2: the loader now resolves `investment_plan` 1.0.0 and `investment` 2.0.0.
  Pipeline calls the node once, which makes two ordered adapter calls. Common
  snapshot/date and full clinical/market/IP/partnerships outputs are wired;
  prompt hashes/usage are recorded. Shared runtime is implemented by R2,
  not modified by this R5 documentation update.
- R3: audit actual support and applicability of numeric bindings/analogues, scope
  and coverage, and new claims. Exact quote/number/unit checks do not replace audit.
- R4: review milestone/success criteria, work/resource plan, graph and delays.
- R1: display fixed plan, financial interpretation, numeric provenance/pending
  status, dates/currency/scale, partial subtotals and full-budget unknowns.
- IP specialist: review transfer/licensing rights and retained obligations.
  Partner fit does not prove interest or committed funding.

Fixtures in docs/examples/investment-synthetic.json contain both mock responses and
replay without caller-supplied scenarios. Tests exercise arithmetic, preparation,
source errors, missing inputs, fixed records, schema boundaries, upstream examples
and a manually assembled synthetic Report in the original node fixtures.
Current R2 integration tests additionally exercise the real Report builder with
prepared provider responses. Neither test style proves live reasoning quality,
hallucination/prompt-injection defense or profitability.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/api/src /private/tmp/r5-ip-licensing-venv/bin/python -m pytest services/api/tests -q -p no:cacheprovider
```

The original node implementation changed only R5 investment files/prompts/tests/docs/examples. Shared contracts,
llm.py, pipeline, report_builder, OpenAPI, frontend and other nodes are untouched.
Codex.code-workspace is preserved without staging.

Historical implementation validation against main 3cca985 after regression fixes: 514 backend tests passed, including 205 investment tests.

## Numeric narrative and source-sign regression fixes

`assemble_investment_analysis` now calls `validate_explanation_numbers`: all
free-form second-response narrative must be qualitative without numeric literals.
Amounts, durations and other numeric outputs remain in `calculated_financials`.
Structured reference fields and team names R1–R5 remain allowed. A global number
whitelist would still permit wrong scenario/unit attribution, so even input-matching
numbers are rejected in narrative. Update adapter consumers to use structured
calculations for number display. This lexical check does not audit number words
or qualitative factual claims; semantic review remains required.

Source parsing rejects ASCII/Unicode negative signs with optional whitespace,
while preserving positive ranges such as 100–200. Regression coverage includes
Unicode/fullwidth signs, Unicode digits, nested explanation fields and references.
No shared files, live API calls or commits were added.
