# Market context budget and live verification

The first full workflow after the Clinical fix stopped at `market_request_budget`.
Replaying its saved real synthetic Clinical output produced requests of 25,301
bytes (Competitive) and 26,497 bytes (Commercial). Projected Clinical context
alone occupied 16,668 bytes, so evidence batching could not make the base fit.

## Changes

Market now partitions the exact projected Clinical claims, risks, unknowns,
limitations, change conditions and unclaimed context when the base is too large.
Each clinical context group reviews all supplied evidence through bounded
evidence batches. Excerpts, locators, source metadata and Clinical records are
not truncated or summarized. Small inputs keep the original two-call path.

Partial Clinical context is explicitly labelled in each batch. Prompts prohibit
treating omitted records as absent facts or asserting complete clinical
alignment. Existing audit feedback is included in every request. Python merges
all results conservatively, preserving contradictions and unresolved gaps.

Clinical context identities join the stable claim/risk namespace for large
inputs. Distinct interpretations of the same evidence in different context
groups cannot overwrite each other. Risk IDs include evidence coverage even
when their claim references are empty. Exact matching facts remain deduplicated.

Competitive differentiation must reference a named listed competitor. With no
identified competitor, the differentiation list must be empty and the missing
comparator/benefit bar remains an explicit gap. Invalid references get one fresh
corrective call carrying the complete original batch and audit feedback, without
replaying the large invalid answer. Persistent defects still fail.

The maximum remains **18,000 UTF-8 bytes**; initial batches remain at or below
**13,500 bytes**, reserving repair headroom. The budget is not raised to bypass
the gateway. The measured envelope and runtime guard include the same JSON
serialization and optional reasoning parameter. Oversized indivisible clinical
records, excerpts, case data or feedback still fail explicitly without paid calls
or silent data loss. Large inputs require more calls and can increase total cost.

## Completion setting

`MARKET_REASONING_EFFORT=low` defaults only for the two OpenAI-compatible Market
prompts, using the same scoped approach as Clinical. Other roles and Anthropic
calls retain their behavior. An empty setting omits the parameter for unsupported
gateways/models. The 4,096-token completion allowance is unchanged and the
setting enters the non-secret config trace. OpenAI documents that completion
tokens include reasoning and that lower effort can reduce reasoning token use:
[API reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
This controls output-budget exhaustion; domain quality still needs review.

## Validation

- Full backend suite: **1,031 tests pass**; Ruff and `git diff --check` pass.
- Tests verify exact Clinical record and evidence coverage, safety contradictions,
  batch-local citations, audit feedback, stable distinct claim/risk IDs, bounded
  repair and exact transport-size accounting. An indivisible large safety record
  is rejected rather than shortened.
- Live replay with the actual configured gateway: **5 Competitive and 6
  Commercial calls** returned valid JSON; the combined Market RoleResult passed
  final validation. Actual requests ranged from **10,049 to 13,467 bytes**.
  Position remained `insufficient_data`; no model-generated numeric scenarios
  were introduced.
- Records: `artifacts/r2-whole-workflow-55/market-probe/corrected-market.json`,
  `corrected-trace.json` and `response-metadata.json`, using saved real Clinical
  results and a labelled synthetic evidence snapshot. No provider credentials
  are stored. This verifies Market execution, not clinical/commercial truth or
  completion of the entire committee workflow.

The full live HTTP rerun `run-2ca94be4563c` passed Science, Translation, both
Clinical calls, and all 5 Competitive plus 6 Commercial Market calls. Market
assembly passed, then **IP/licensing received HTTP 413** from the gateway.
Its trace is saved in `artifacts/r2-whole-workflow-55/market-final/trace.json`.
The Market budget blocker is resolved for this case; a completed committee
report and live revision remain unverified until the downstream workflow passes.
