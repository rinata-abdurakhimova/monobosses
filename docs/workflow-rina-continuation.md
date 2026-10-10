# Frozen workflow continuation, 10 October 2026

Continues Uliana's comment on PR #56:
https://github.com/rinata-abdurakhimova/monobosses/pull/56#issuecomment-6095703510

Branch: `codex/whole-workflow-testing`. Case: `case-bba4adb11384`.
Snapshot: `snap-run-81c3bf4976ff`. No retrieval.

Transferred artifacts were extracted separately into
`artifacts/uliana-transfer/artifacts/r2-whole-workflow-55/`; the original local
artifacts were preserved. Both frozen `vic.sqlite3` files have SHA-256
`cb82a04d26e030624fd645f9071e84bc2d611ad2f9d2626788ee36790911bbc7`.
The HTTP harness uses its separate transferred `http-frozen.sqlite3`.

Market feedback partitioning now checks the complete serialized request against
the existing initial budget. If all findings fit, existing claim identities are
preserved. Otherwise exact finding groups are recursively divided and measured
with schema, evidence and exact Clinical records intact. A finding that cannot
fit alone still fails explicitly. Caps remain 13,500 initial / 18,000 repair.

First continuation run `run-982269ec431c` passed the previous planning blocker.
It subsequently failed during Market schema repair: an invalid risk Identifier
caused replay of the model's large invalid answer, producing a 26,248-byte
request, rejected locally before transmission. Market schema repairs now use
bounded fresh error feedback, retaining the original request and audit findings
without replaying the invalid answer.

The final code was loaded for `run-131813eb8cba`. Specialist results are reused
only on first execution; Audit, affected repair nodes and Chair execute live.
Market repair passed final validation and was saved as
`http-frozen/run-131813eb8cba-market.json`. The workflow then failed with
`context_record_budget` before downstream repair calls, repeat Audit or Chair.
The merged Market summary alone requires a **22,964-byte** `briefing_payload`
against the context-review payload limit of **10,500 bytes**. The next change
must let the context reviewer process this summary in complete source-linked
parts, preserving its position, full source coverage and canonical output.
Large repaired Market claim/risk inventories also need downstream sizing checks.
The final run recorded 62 Competitive and 92 Commercial Market HTTP calls,
plus four Audit calls, all HTTP 200. Actual request sizes were 6,069–13,498 bytes.
No final HTTP report was produced. This is a verified stopping point, not a
completed workflow or live revision.

Validation after both fixes: **1,099 backend tests passed** with
`SEED_SYNTHETIC=true`. Tests cover feedback smaller than the previous fixed
2,500-byte threshold that nevertheless overflows the complete envelope, stable
claim identities when splitting is unnecessary, and large invalid Market output
corrected without replay. Financial and domain validators are unchanged.

Windows reproduction requires `PYTHONUTF8=1` for the transferred scripts. The
HTTP probe now accepts `FROZEN_RUN_ID` to reconnect to an existing run and retries
polling read timeouts without creating duplicate runs. Logs and outputs are in
the transferred directory's `http-frozen/`.

Changes are local and uncommitted; PR #56 has not been updated.

Ruff passes on the changed Python files; `git diff --check` passes. The server
was stopped after the terminal failure so no model calls remain running.

## Oversized Market summary fix

Canonical summaries remain unchanged. Their review representation splits long
text into exact segments with character offsets and the original role and
position. UTF-8 bytes and JSON escapes determine segment size. Segment membership
is validated exhaustively through the existing brief consolidation; position is
retained explicitly as note status. Context cache version is now v3.

Context-review batches also measure the complete serialized request with the
real response schema and envelope, retaining the 10,500-byte payload ceiling,
configured initial ceiling and 512-byte schema-repair reserve.

The targeted live probe `probe_market_downstream.py` uses the validated repaired
Market artifact from `run-131813eb8cba`, without rerunning retrieval or reusing old
dependent results. Attempt `market-downstream-1791624232` passed the former
summary-budget blocker and processed context-review requests, then stopped in
IP/licensing context review with provider HTTP 502 after adapter retries.
Partnerships and subsequent nodes have not completed this continuation.
Diagnostic outputs are in `market-downstream/` and `http-frozen/` under the
transferred artifact directory. No final HTTP report was generated.

Focused verification: 60 context-protocol tests passed, including ASCII/Unicode
and escaped text, exact reconstruction, unchanged canonical inputs, missing-part
rejection, actual envelope sizes, exhaustive live-adapter membership and retained
Market position. Ruff and diff checks pass.
Final full backend suite after the summary fix: **1,102 tests passed**.
The targeted live check recorded 58 successful context-review responses;
request sizes ranged from 4,677 to 13,484 bytes. Gateway 502 failures prevented
completion of IP/licensing. All probe processes have exited.

## IP/licensing completed

The subsequent IP continuation passed on the same frozen snapshot using the
validated repaired Market output. Saved result:
`market-downstream/market-downstream-1791626243-ip_licensing.json`.
Position: **insufficient_data**; FTO: **unresolved**; six claims and nine risks.
The saved RoleResult, reconstructed IPLicensingAnalysis and unchanged
`validate_ip_licensing_result` were independently revalidated without LLM or
retrieval calls. Output SHA-256:
`ecd84c167d93c3252cbbd60f4e46c3159565381593d7d4d0aa1e4a091c95ec08`.

Fixes:

- Compatible upstream claim/risk aliases are allocated contiguously. This
  compresses scattered reference sets into exact ranges without deleting IDs,
  findings, metadata or canonical inputs. Round-trip regressions verify it.
- IP non-unknown findings now receive early value, own-claim, support-status and
  assumption checks. Compact corrections show actual wire aliases.
- IP summary/position are generated after the detailed assessment. Frozen FTO
  status/barrier IDs prevent a potential_barriers position with no barriers.
- Coverage receives exact counts for all nine IP domains. Documented coverage
  requires existing entries and supported own claims; missing coverage retains
  explicit gaps. The final domain validator remains unchanged.

The local continuation harness uses bounded gateway retries and immediately
checkpoints accepted schema/domain-validated components, keyed by exact input,
schema, prompt, model and feedback. These are continuation components, not old
dependent role outputs. Invalid cached findings are revalidated and regenerated.
The completed context brief was reused after review; changed components ran live.
This is a checkpointed live node continuation, not a fresh uninterrupted full
HTTP workflow. Existing request/completion caps were not increased.

Final validation: **1,108 backend tests passed**, Ruff and diff checks passed.
Partnerships and subsequent dependents still need rerunning with the new IP
result. Full HTTP report and live revision remain unverified. No PR push or
GitHub comment was made; changes remain local.

## Partnerships completed

`market-downstream-1791626401` ran Partnerships against the same frozen case and
snapshot, using repaired Market `run-131813eb8cba-market.json` and the new,
independently revalidated IP result `market-downstream-1791626243-ip_licensing.json`.
Old dependent Partnerships outputs were not reused. No retrieval occurred.

Saved result: `market-downstream/market-downstream-1791626401-partnerships.json`.
Position: **insufficient_data**; one candidate, five claims and four risks.
Both the live assembly and an independent offline reconstruction passed
`PartnershipsAnalysis` and the unchanged `validate_partnerships_result`.
Output SHA-256:
`357a275ba2577eb552a56d384a521ab02da8f1eaa34ebc2a5001889bc153bdce`.
Independent validation is recorded in
`market-downstream/market-downstream-1791626401-saved-validation.json`.

The run recorded 26 actual model HTTP calls, all HTTP 200, ranging from
1,847 to 13,402 UTF-8 request bytes. These include context review and Partnerships
analysis; they are not a full-workflow call or latency statistic. Prior validated
upstream context briefs were reused when their keys matched.

No additional backend change was needed for Partnerships. The most recent full
backend suite remains **1,108 passing tests**. Investment, Investment Threshold,
Failure Miner, repeat Audit, Chair and the final HTTP report remain pending with
the newly repaired downstream outputs. The probe has exited.

## Investment completed

Investment used the repaired Market, new IP/licensing and new Partnerships
results on `snap-run-81c3bf4976ff`, without retrieval. Saved RoleResult:
`market-downstream/market-downstream-1791627525-investment.json`.
Position: **conditional_path**; five claims, seven risks; own development,
licensing and acquisition paths all validated. This is an Investment node
position, not a committee recommendation.

Prepared-plan validation, Python calculation, final assembly and unchanged
`validate_investment_result` passed. Independent offline verification revalidated
the saved analysis, verified the immutable plan hash and reproduced the Python
calculations exactly. There are zero quantified scenarios and zero quantified
stress scenarios: this snapshot has no financial/time operands. No sums were
invented. Validation record:
`market-downstream/market-downstream-1791627525-saved-validation.json`.
Output SHA-256:
`91d8185654419c9befde6a5f3c991f6150ef7bb911137953b603c109122132a7`.

Continuation fixes:

- Investment summaries explicitly keep wire aliases and numeric identifiers out
  of prose, retaining exact IDs in reference fields.
- Time uses a single unwrapped TimeAssessment wire response to avoid recurring
  malformed wrapper braces. Assembly restores the time field; numeric, scenario
  and domain checks still run. Integration fixtures follow the same wire shape.
- Set-valued upstream_claim_ids and record_ids catalogs now use exact alias
  ranges when smaller. This resolved the oversized Market dependency catalog in
  Commercial Constraints. Tests verify complete references and namespace checks.
- Unknown-finding correction feedback covers every unknown Finding, so null
  values and explicit gaps are corrected across the whole component.

The successful final continuation recorded eleven new HTTP calls, all HTTP 200,
13,968–14,569 request bytes. Exact validated components from earlier attempts
were reused and revalidated; this is not a fresh uninterrupted node run. These
measurements are not total historical calls. Caps and validators were retained.

Final full backend suite: **1,110 tests passed**; Ruff and diff checks pass.
Investment Threshold is next, followed by Failure Miner, repeat Audit, Chair and
the final HTTP report. Those remain unverified with this new Investment result.
The continuation probe has exited; edits are local and uncommitted.
