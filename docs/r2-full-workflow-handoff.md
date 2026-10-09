# R2 full workflow integration

Branch: `codex/r2-full-workflow`, based on main `7c31fc8` (9 October 2026).

## Connected behavior

The HTTP background pipeline now runs science and translation, clinical, market
with clinical context, IP/licensing, partnerships, investment (planning and
explanation), investment threshold, failure miner, specialist audit, Chair,
new Chair claim audit, and canonical report assembly. Every business node receives
its actual upstream RoleResults. An audit repair reruns every affected downstream
node before synthesizing again.

The Chair bridge supplies case, complete evidence pack, all nine specialist
results and audit. Its CommitteeDecision and rich RoleResult are retained.
The final report contains 11 sections and 11 perspectives, including the audit
findings. The frontend shows their claims, risks, unknowns, conditions and expandable
structured analyses. Metadata and repeated upstream records are retained in the
contract, while the detail viewer shows the node's own analysis.

PDF HTTP upload now calls R3's parser. A successful import stores excerpts,
page locators and canonical document text in SQLite without starting a run.
Repeated identical imports are idempotent; conflicting provenance is rejected.
Publication date can be supplied for historical assessments. PDF evidence defaults
to approach scope; users can explicitly identify program evidence in a program
assessment, subject to applicability audit. Parsing errors return 422; size/type
errors retain 413/415. An explicit rerun includes imported evidence in a new
snapshot and preserves the old report.

The runtime selects R3's semantic audit on top of structural checks, passing
persisted imported documents for exact excerpt/locator checks. Retrieved sources
without persisted canonical documents retain R3's existing audit limitations.
Automated audit does not replace domain review.

## Verification

From `services/api` with dependencies installed:

```powershell
python scripts/check_wiring.py
python -m pytest tests -q
```

From `apps/web`:

```powershell
npm test
npm run typecheck
npm run contracts:check
npm run format:check
npm run build
```

`tests/test_full_workflow.py` uses all real domain functions and the shared
StructuredLlm adapter through HTTP with a deterministic provider. It checks rich
upstream transfer, a validated report, unchanged recommendation on an unrelated
update, immutable v1/v2, SQLite reopening, evaluation exports, and evaluator-label
isolation. It does not establish live analysis quality.

`scripts/check_workflow.py` is the separate live HTTP check. Start the API with
`RUN_BACKEND=pipeline`, `DEV_STUBS=false`, a separate persistent test database and
the configured model provider, then:

```powershell
python scripts/check_workflow.py --base-url http://127.0.0.1:8000 --output ../../artifacts/r2-live --revision
```

For the frontend proxy, use `--base-url http://127.0.0.1:3000/api/backend`.
This creates a labelled synthetic case but uses real model calls. It exports run
and report JSON, checks all perspectives, reads the saved report again, and can
upload a readable PDF before an explicit revision. Domain reviewers must assess
the resulting claims and recommendation change; the script does not force one.

## Live provider blocker observed

The configured mentor gateway accepts a short connectivity call and a standalone
science call. Market requests are rejected with HTTP 400 and the provider message
`Input exceeds the conservative input limit. Shorten the conversation or tool schemas.`
Output allowances of 8192 and 16000 were also rejected; 4096 was accepted on a
short request. These are observed gateway restrictions, not a claim about the
underlying model's general context capacity.

The adapter now emits compact JSON and removes schema display titles without
removing fields, constraints or instructions. The market diagnostic still exceeded
the gateway limit. This specific rejection becomes `provider_context_limit`, without
exposing the provider response or credentials. A completed live committee report
has not been verified. The agreed next step is to reduce and split Market requests
within the existing gateway limits while preserving the public output contract.
Uliana owns [issue #51](https://github.com/rinata-abdurakhimova/monobosses/issues/51).
No domain prompts or outputs were silently trimmed to fit.

An additional diagnostic with `gpt-5-mini` through the same gateway returned the
same conservative input-limit rejection. The saved model configuration was not
changed. Final local verification: 970 backend tests and 40 frontend tests pass;
TypeScript, contract drift, formatting, production build and diff checks pass.
Browser inspection of the actual integrated test report confirms all 11
perspectives and expandable financial-plan details. This is a deterministic
integration report, not a completed live committee analysis.

## Frozen evaluation runner

From the repository root, with `vic` installed and provider settings available:

```powershell
python evals/run.py manifest.json --output artifacts/evaluation
```

The manifest is a JSON object with `cases`. Each row has a unique safe `id`,
`family`, `split` (`development` or `holdout`), `input`, and `pack`. Input/pack can
be inline JSON or file paths relative to the manifest. Pack is either a shared
EvidencePack or `{"documents": [...]}` containing R3 JSON documents. `parent`
optionally names an earlier case row for a paired revision using the same family
and input. Related families cannot cross splits.

Expectations, identity maps and leakage metadata remain evaluator-only. The
runner always uses evidence-only mode and exports each run, report, trace,
snapshot, manifest, non-secret config and a summary with exact statuses,
usage, latency and available cost. Each invocation gets a fresh results directory
and database. It does not implement or invent R5's expert scoring/rubric.

Deployment and issue closure still require the successful live run, actual
deployment restart/volume checks, and R3/R4/R5 domain review.
