# Clinical request reduction and live verification

Clinical originally exceeded the configured gateway's input limit. A shorter
prompt alone still failed. Large Clinical requests now use two task-specific
calls: trial design and development/safety. Both receive the complete evidence
and prior Science/Translation context; evidence and upstream text are not
truncated. Small requests retain the single-call path.

The shared strict output models supply the partial schemas. Each pass restricts
claims to its assigned stable keys. The combined output is validated against
the original `ClinicalPlanAnalysis`, so the report/API contract is unchanged.
Risk assessments with the same ID retain both descriptions, impacts, next
checks and related claims, with the stronger priority. Unknowns, limitations,
change conditions and science gaps are combined without dropping either pass.
Clinical audit feedback is supplied to both requests. Prompts remain evidence
only, preserve scope and safety gaps, and treat supplied text as untrusted data.

## Request sizes

Measured on identical cached real synthetic-case Science/Translation outputs:

| Request | UTF-8 bytes |
| --- | ---: |
| Original full request, reconstructed offline | 22,436 |
| Shorter full request | 18,083 |
| Trial design, accepted live | 14,305 |
| Development/safety, accepted live | 15,147 |

The replacement requests are about 36% and 32% smaller than the original.
The 14,000-byte split threshold is an application choice, not a measured
provider limit. Both calls repeat the upstream context, so total input tokens
can increase even though each request is smaller. Larger evidence packs and
repair/audit feedback can still exceed gateway limits; no information is
silently discarded to force acceptance. Request-size breakdowns enter the trace.

## Completion allowance

The live development call initially returned no JSON: response metadata showed
`finish_reason=length`, 4,096 completion tokens, and 4,096 reasoning tokens.
Clinical OpenAI-compatible calls now default to `CLINICAL_REASONING_EFFORT=low`;
other roles and Anthropic calls keep their existing behavior. The setting is
included in non-secret configuration traces. Set it to an empty value to omit
the parameter for gateways/models that do not support it, or select another
supported effort. The 4,096-token completion cap is unchanged.

OpenAI documents that completion allowances include reasoning tokens and that
lower effort can reduce reasoning token use. Model/gateway support must be
checked; this team's configured `gpt-6-luna` gateway accepted `low` in live tests.
[API reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
and [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna).

## Validation

- Full backend suite: **1,023 tests passed**.
- Tests preserve complete evidence/prior text, Clinical audit feedback, all plan
  fields, risk priority and stable IDs. Transport tests verify that effort is
  scoped to Clinical, can be omitted, and measured bytes match sent JSON.
- Live Clinical probe: both requests returned JSON and the combined RoleResult
  validated. Sparse synthetic evidence retained unknown safety and patient
  benefit; trial size remained `has_basis=false`, `estimate=null`.
- Full live HTTP rerun `run-fe19f197ffe7`: Science, Translation, Clinical design
  and Clinical development all succeeded. Its Clinical calls measured 14,725
  and 15,567 bytes with that run's newly generated upstream text.
- The workflow then stopped at **`market_request_budget`**, before a completed
  report or live revision. Whole-workflow acceptance remains incomplete.

Local non-secret records are under `artifacts/r2-whole-workflow-55/clinical-probe/`
and `artifacts/r2-whole-workflow-55/clinical-final/`. They include actual prompt
hashes, usage, request sizes and response metadata, not credentials. Live checks
used synthetic cases and the configured provider without stubs. Model quality,
including the effect of lower reasoning effort, still requires domain review.
