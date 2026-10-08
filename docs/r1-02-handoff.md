# R1-02: API workflow and server authentication

Related to issue #8. Branch: `codex/r1-02-proxy-auth`, based on main after PR #42.

## Implemented

- Typed createCase/startRun/getRun/getReport operations through the Next.js proxy.
- One explicit form submission creates one case/run; sequential GET-only polling
  stops on terminal status, navigation or deadline. No automatic mutation retry.
- Correct report version, case and run validation; reopening reads saved records.
- Visible validation, missing-record, provider/run failure, network and timeout states.
- Server-only `API_SHARED_SECRET` forwarded as `X-API-Key` for every allowed backend
  operation, including status/report reads and evidence/PDF uploads. Browser keys,
  Authorization and cookies are ignored; upstream credential headers are stripped.
- HTTP smoke check records observed stages, verifies read-only reopening and
  optionally checks a seeded failed run with `CHECK_SEEDED_FAILURE=true`.

## Local verification — 2026-10-08

40 frontend tests, TypeScript, format check, contract drift, production build and
`git diff --check` passed. The production build's 16 browser asset files contained
none of the synthetic server-key sentinel used for this verification.

Started an isolated SQLite API on port 8043 with `RUN_BACKEND=pipeline`,
`DEV_STUBS=true`, `SEED_SYNTHETIC=true`, `STUB_DELAY_SECONDS=0.3` and authentication
enabled. Next.js production server on port 3043 used the matching server key.
No real keys, provider calls or external retrieval were used.

`check-python-api.ts` passed through real HTTP via Next.js: case
`case-cbb1bf571f1b`, run `run-f243f1b5d195`, saved v1 with 11 sections. Observed
retrieve/analyze/audit/finalize; reopening did not add POSTs. Checked 422, 404 and
the seeded terminal failure. Direct unauthenticated Python GET returned 401.

Browser checks confirmed form submission, background progress, completed synthetic
report and reload preserving run `run-e6a52b210090` / report `rep-e2aa341c92e7`.
A second run visibly showed Retrieve evidence. Opening the seeded failed run showed
“The assessment failed” and interruption explanation without an endless spinner.
Screenshots are ignored local artifacts in `apps/web/artifacts/r1-auth-review/`.

## Configuration and repeatable checks

Set the same `API_SHARED_SECRET` in Python and the Next.js server environment.
Never prefix it with `NEXT_PUBLIC_` or expose it in URLs. Restart services after
configuration changes. Empty credentials are for authentication-disabled development
only; production Python refuses them. A mismatched key returns visible 401.

From `apps/web`, with both services running in isolated synthetic development:

```bash
# Optional when using another port:
export WEB_BASE_URL=http://127.0.0.1:3043
export CHECK_SEEDED_FAILURE=true
npm run test:api
```

PowerShell: `$env:WEB_BASE_URL='http://127.0.0.1:3043'` and
`$env:CHECK_SEEDED_FAILURE='true'`. The script creates test records; the failed
fixture requires `SEED_SYNTHETIC=true` in the development API.

## Remaining acceptance gates

#8 remains open. Its live outcome requires a real analysis, not synthetic output.
R2 now supplies SQLite, background orchestration and authentication; the real R5
committee chair (#13) and end-to-end verification with real model calls remain
pending under #7. Uliana's code/prompts were not changed.

After integration, configure/redeploy both Railway services, test the actual
website happy path and failed run, inspect one case POST plus one run POST followed
by status/report GETs, then reload. Verify saved records after API restart on the
persistent volume. Local checks here do not verify Railway variables, deployment
commit or volume behavior. PDF 501 remains R2-03; evidence/revisions belong to #15.
