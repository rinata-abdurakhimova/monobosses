# Failure Miner live verification on the frozen snapshot

Verified on 2026-10-10 in `codex/whole-workflow-testing`, continuing the saved
Investment and Investment Threshold results. Case: `case-bba4adb11384`;
snapshot: `snap-run-81c3bf4976ff`. No new retrieval was performed.

## Result

The real `analyze_failure_miner` call completed and passed `FailureAnalysis`,
`validate_failure_result` and the assembled `RoleResult` contracts. Output:
`artifacts/r2-whole-workflow-55/remaining-nodes/failure_miner.json`.

- Position: `insufficient_data`, not an observed program failure.
- Eight failure chains, six conditional risk interactions and eight ranked
  diligence checks.
- Eight domain reviews account for **all 72 upstream risks** using explicit
  included/deferred dispositions. Market required two risk-review slices.
- Every failure has a prioritized check; any question citing an interaction
  covers both endpoints. Included risks match the frozen failure origins.
- Independent offline schema/domain revalidation passed for Investment,
  Investment Threshold and Failure Miner; output hashes are recorded in
  `remaining-nodes/saved-validation.json`.

Valid live components were reused after schema/reference checks. This is a
resumed component run, not a fresh uninterrupted HTTP workflow. Semantic Audit,
Chair and the complete live HTTP workflow remain unverified and were not run
in this continuation.

## Problems found and changes

The initial combined failure-modes call fit the byte cap but exhausted the
unchanged 4,096-token completion allowance with `finish_reason=length`. Failure
chains now use separate domain requests, each returning at most one material
chain or an empty list if none is justified. The final analysis still requires
at least one chain and complete risk accounting. Other risks can be explicitly
deferred; the change does not establish exhaustive semantic failure discovery.

Interaction generation first produces a small plan with exact frozen endpoints
and relationship identities, then explains each selected link separately. The
plan receives exact problem Findings; individual explanations also receive the
exact consequence and investment-impact premises for both endpoints. Final
interaction contracts and validators remain unchanged.

A domain-review request reached 16,190 bytes and was blocked locally. Reviews
now receive the relevant domain's frozen failure origins and associated own
claims, plus supported own observations. They retain the complete supplied
risk slice. Requests are fitted with repair reserve before provider dispatch.

Early component validation now rejects namespace mixups, invented endpoints,
unknown Findings with factual claim references, unsupported documented Findings,
unknown claims without gap assumptions, missing diligence coverage, invalid rank
order, single-endpoint interaction questions and risk dispositions inconsistent
with frozen origins. These enforce existing final domain rules before accepting
fresh or cached components; the final financial/domain validators were not
weakened. The probe saves domain-review components by role and risk-slice hash
and preserves earlier nonempty traces when reusing whole results.

## Byte measurements and validation

Node hard cap remains **15,500 UTF-8 bytes**; initial component fitting reserves
512 bytes, giving an initial ceiling of **14,988 bytes**. The existing 13,500-byte
planning target, 4,096-token completion cap and configured reasoning effort were
not increased. Repair feedback remains bounded and does not replay a large
invalid answer.

The selected saved traces record these request ranges:

| Request type | UTF-8 bytes |
| --- | ---: |
| Failure chains by domain | 8,818–11,153 |
| Interaction blueprint | 12,575 |
| Individual interaction explanations | 12,592–14,029 |
| Domain-review risk slices | 7,348–8,710 |
| Initial node requests within the hard cap, selected traces | 7,348–14,985 |
| Repair requests, selected traces | 14,558–14,911 |

`remaining-nodes/failure_miner-request-measurements.json` extracts measured sizes
from `failure_miner-chains-live-trace.json`,
`failure_miner-interactions-reviews-live-trace.json` and
`failure_miner-continuation-trace.json`. It retains the locally blocked 16,190-byte
attempt with `within_hard_cap=false`. The ranges include some provider responses
subsequently rejected by validators; they are not a complete retry, cost or
latency history. Fitting rechecks actual request size before cached-context reuse.

Final checks: **1,079 backend tests passed**, Ruff passed on changed Python files,
and `git diff --check` passed. Tests used `SEED_SYNTHETIC=true` and temporary
databases. The frozen SQLite SHA-256 remains
`cb82a04d26e030624fd645f9071e84bc2d611ad2f9d2626788ee36790911bbc7`.

From `services/api`, with local LLM configuration and the frozen database:

```sh
.venv/bin/python ../../artifacts/r2-whole-workflow-55/probe_remaining.py --through failure_miner --reuse-components
.venv/bin/python ../../artifacts/r2-whole-workflow-55/validate_saved_remaining.py
SEED_SYNTHETIC=true .venv/bin/pytest -q
```

The snapshot is synthetic and has no financial budget/time operands. Schema and
domain checks establish reference/structural consistency, not clinical,
commercial or financial truth. AI context synopses and domain interpretation
still need semantic and specialist review. Batching increases calls and potential
cost. These changes remain local and uncommitted; artifacts are ignored by Git
and must be transferred separately for another checkout.
