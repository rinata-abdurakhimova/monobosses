# R1-02 independent preparation

Branch: `codex/r1-02-client-preparation`. This work prepares issue #8 while R2's OpenAPI, server, and authoritative report format are pending.

## Implemented

- Replaceable client interface: createCase, startRun, getRun, getReport.
- Typed local mock and a future HTTP transport, kept separate from the original fixture preview.
- Sequential GET-only polling, navigation cancellation, and bounded waiting.
- Explicit 422 validation, 404, failed-run, network, malformed-response, and timeout states.
- Tab-local saved mock cases/runs/reports. URL identifiers survive reload; reads never start a new run.
- Explicit manual status recovery on the same run. No automatic POST retries or fallback from an API error to a fictional report.
- Report version validation and separate immutable mock snapshots for explicitly started runs.
- Unit tests using Node's built-in test runner; no new runtime/test-runner dependency.

## Try it

From `apps/web`: `npm ci`, `npm run dev`. Node 22.18+ is required for the native TypeScript test command; verified with Node 24.

On the form, choose **Mock API workflow — local simulation**, use the fictional example, and select a scenario under **Preview states**. Start the workflow, then refresh its case page. Try connection interruption and **Check existing run again**; the URL run ID stays unchanged. Try failed, missing, invalid, and timed-out runs. The original **Fixed fictional report preview** remains available independently.

Verification: `npm test`, `npm run typecheck`, `npm run format:check`, `npm run build`.

Verified: 15 automated tests pass, TypeScript and production build pass, and formatting checks pass. Browser checks confirmed mock completion/reload, field-focused 422 errors, same-run connection recovery, terminal failure, 404, malformed responses, the polling deadline, disabled backend flow without fixture fallback, and preservation of the original fixture preview. The mock form has no page-wide horizontal overflow at 390px. This evidence covers the preparation layer, not integration with Python.

## R2 handoff / remaining integration

1. Supply actual OpenAPI, input/run/error response examples, and shared fixtures.
2. Confirm case/run/report routes, field names, run stages, report-version semantics, and validation errors.
3. Agree on a reload-friendly way to find the relevant saved run. The mock URL currently carries both case and run IDs.
4. Supply backend host/startup instructions and server-side auth requirements. Implement the agreed same-origin proxy; `/api/backend` in the HTTP adapter is currently a placeholder, not a functioning route.
5. Supply and validate the wire-report-to-UI mapper. The HTTP client does not assume the frontend's provisional report model matches R2's report.
6. Enable live flow only after real API happy-path, failure, cancellation, and reload tests. Do not close #8 on these mock checks alone.

Mock data is browser-tab-local, synthetic, and temporary. It demonstrates lifecycle behavior, not backend persistence or analysis quality. The fixed report never changes based on submitted input. No Python/model calls are made from the enabled UI flows.
