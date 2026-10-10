# Semantic Audit live check on the frozen snapshot

On 2026-10-10, the actual Semantic Audit node completed against snapshot
`snap-run-81c3bf4976ff`, case `case-bba4adb11384`, using the saved live results
through Failure Miner. No retrieval ran. The probe now stops explicitly at
`--through semantic_audit`, before Chair.

Four initial OpenAI-compatible gateway requests measured 10,227, 10,425,
10,460 and 6,069 UTF-8 bytes, below the 13,500-byte batching target and
15,500-byte hard limit. All returned HTTP 200 with finish reason `stop`;
all structured outputs validated on attempt zero. No repair request was
needed, so this run does not establish live repair behavior.

The final AuditResult contains all 106 unique upstream claims. All 40 claims
eligible for semantic checking have an LLM-assisted finding. The other 66
retain their exact deterministic findings. Offline validation checks schema,
claim identities and coverage, preservation of ineligible findings, blocking
list consistency, and absence of unavailable/invalid-output warnings.

Final verdicts: 35 supported, 4 mixed, 17 unverified, 50 unknown. One critical
claim, `market.commercial_program_stage_e4339ce5ae9c`, was downgraded from
supported to unverified and is blocking. Four supported claims became mixed.
Two eligible mixed claims became supported under existing audit behavior;
this run does not assert that those upgrades are domain-correct. No claim
that failed deterministic checks was rescued. Semantic judgments require
review and do not establish clinical or commercial truth.

Artifacts under `artifacts/r2-whole-workflow-55/remaining-nodes/`:
- `semantic-audit.json`: final schema-valid AuditResult.
- `semantic-audit-trace.json`: all four request measurements and usage.
- `semantic-audit-validation.json`: offline validation counts and changes.
- `provider-response-metadata.json`: status and finish reasons, without secrets.

The probe overwrites its component/last-response files per prompt, so those
files retain only the final audit batch. The final findings and trace retain
coverage and measurements for all four calls. The reproducible offline check
is `artifacts/r2-whole-workflow-55/validate_semantic_saved.py`.

Database SHA256 remains
`cb82a04d26e030624fd645f9071e84bc2d611ad2f9d2626788ee36790911bbc7`.
The focused deterministic and semantic audit regression suite passes: 22 tests.
No production source change was needed for this node. Artifacts and probe
scripts are ignored by git and must be transferred separately. Continuation
changes remain local. Chair and the full HTTP workflow were not run.
