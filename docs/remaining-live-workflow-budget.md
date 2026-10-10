# Frozen Investment and Investment Threshold verification

Verified on 2026-10-10, branch `codex/whole-workflow-testing`, using case
`case-bba4adb11384` and snapshot `snap-run-81c3bf4976ff` from Rina's transferred
`artifacts/r2-whole-workflow-55/` directory. No new retrieval was performed.
The frozen SQLite SHA-256 remains
`cb82a04d26e030624fd645f9071e84bc2d611ad2f9d2626788ee36790911bbc7`.

## Results and stopping point

- Investment completed live component generation and final
  `validate_investment_result`; saved as `remaining-nodes/investment.json`.
- Investment Threshold completed live component generation and final
  `validate_threshold_result`; saved as `remaining-nodes/investment_threshold.json`.
  Its position is `insufficient_data`. Both gates have status `unknown`.
  The now gate has three criteria and three actionable gaps; next_stage has
  four criteria and four gaps. Each gate assesses all seven upstream roles.
- An independent offline pass revalidated both saved RoleResults, analysis
  schemas and domain validators. `remaining-nodes/saved-validation.json`
  records output hashes. It makes zero retrieval or LLM calls.
- At the initial Threshold verification's stopping point, Failure Miner, Semantic Audit, Chair
  and a complete live HTTP workflow were **not run**. A final committee report
  and live revision remain unverified.

The subsequent authorized Failure Miner continuation is recorded in
[failure-miner-live-request-budget.md](failure-miner-live-request-budget.md).

Valid cached live components were reused and revalidated. This is a continuation
of the transferred run, not a fresh uninterrupted end-to-end run. A dangling
Translation risk reference to an absent optional claim required a small live
reference correction; the other risk fields were preserved. The corrected
RoleResult is `remaining-nodes/translation.json`; original upstream artifacts
remain available.

## Request budgets and corrections

The existing node hard cap remains **15,500 UTF-8 bytes**, and the completion cap
remains **4,096 tokens**. The initial planning target remains 13,500 bytes;
component requests may exceed that soft target. Context fitting now requires an
initial request of at most **14,988 bytes**, reserving 512 bytes for repair.
Compact repair feedback is capped at 400 JSON-encoded bytes and does not replay
the invalid answer. Clinical/Market configuration and caps were not increased.

Measurements below are from saved traces of component attempts; they are not a
complete log of every retry or every cached component in the continuation.

| Node | Recorded initial request bytes | Recorded repair request bytes |
| --- | ---: | ---: |
| Investment | 13,803–14,500 | 14,250–14,659 |
| Investment Threshold | 8,530–14,988 | 13,491–15,007 |
| Context brief | 1,593–11,079 | — |

`remaining-nodes/saved-request-measurements.json` extracts exact sizes from
`investment-paths-stress-trace.json`, `investment-failed-trace.json`,
`investment_threshold-gates-live-trace.json` and
`investment_threshold-continuation-trace.json`. Some recorded responses were
rejected by validators, even when they fit the gateway. Provider diagnostics
also showed earlier HTTP 200 responses with `finish_reason=length`, no content
and all 4,096 completion tokens spent on reasoning. A gateway success alone
therefore does not establish a usable response.

Investment Financial Paths are generated individually. Dependencies distinguish
upstream claims from real candidate/asset/license/option record IDs; an absent
record can use `[]`. Early checks reject invented scenario IDs and non-Market
commercial constraints before accepting cached or fresh components.

Threshold splits by horizon, then gate component, individual criterion evidence
assessment/gap and upstream dependency. Long Findings are bounded on the wire.
Later rule requests use exact target/gap tables instead of repeated field names.
Full Findings, limitations and gaps remain in the assembled output. Canonical
inputs remain unchanged; context synopses are AI-derived and may be shortened.
Reference metadata, scope, support status, priority and numeric operands stay
separate and intact. Early validation rejects documented findings citing unknown
claims, claim/record namespace errors, risk/claim identity collisions, and an
unknown gate with a non-unknown achievement assessment. Final domain validators
are unchanged.

## Reproduction and validation

From `services/api`, configure the live LLM locally and point `DATABASE_URL` at
the transferred frozen `vic.sqlite3`:

```sh
.venv/bin/python ../../artifacts/r2-whole-workflow-55/probe_remaining.py --through investment_threshold --reuse-components
.venv/bin/python ../../artifacts/r2-whole-workflow-55/validate_saved_remaining.py
SEED_SYNTHETIC=true .venv/bin/pytest -q
```

Final backend regression result: **1,071 tests passed**. Ruff passed on all
changed Python files; `git diff --check` passed. The seed override is for tests:
the local live `.env` disables synthetic seeding, while a seeded-fixture test
expects it enabled. Tests use their own temporary databases.

The probe's wire-context cache is local verification tooling: cache keys include
the payload, schema, system prompt, model and byte cap. Reuse requires identical
non-synopsis metadata and a freshly measured request within the repair reserve.
Production behavior does not rely on this disk cache.

This synthetic snapshot has no financial budget/time operands. The live result
checks honest missing-data behavior; a numeric live happy path remains separate.
Structural/domain validation does not establish clinical, commercial or
financial truth. Semantic and specialist review remain pending. Fine-grained
batching and context rewriting increase calls, latency and potential cost;
saved traces do not support a complete cost or latency estimate.

The continuation code changes are local and uncommitted; they have not been
pushed to PR #56. Artifacts are ignored by Git and must be transferred separately
for another checkout to reproduce this continuation.
