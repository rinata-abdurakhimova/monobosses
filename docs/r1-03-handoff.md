# R1-03: evidence and report revisions

Related to [issue #15](https://github.com/rinata-abdurakhimova/monobosses/issues/15). This implements the frontend and transport preparation; it does not close the live task.

## Implemented

- Recommendation → actual linked claim → exact excerpt/source. Scope, provenance, status, assumptions, dates and limitations remain visible; private uploads have no public links.
- Saved report/run/snapshot identifiers and version. `/cases/{id}?flow=api&version={version}` performs reads only.
- Before/after recommendations, rationales, changed claims and new evidence. Comparisons validate parent ID, case, categories, complete claim snapshots and new evidence references. Equal categories say “Recommendation unchanged”; mismatches show errors.
- `/cases/revision-sample?version=1` and `?version=2` display the shared, fixed synthetic fixtures separately and compare them.
- Text/PDF import controls use the agreed endpoints and show source/evidence IDs. Import errors never start a run; requests are not automatically retried.
- A separate review action sends `parent_report_id`. Users choose supplied evidence only or live source retrieval. Duplicate clicks are guarded. The old report remains accessible during review, on failure and after reload through the review URL's `previous` version.
- The restricted proxy supports multipart PDF uploads (10 MiB file, 10 MiB + 64 KiB total body) and JSON evidence (64 KiB body). Streamed bodies respect limits, deadlines and cancellation. Origin checks, credential stripping and redirect rejection remain active.

## Verification

From `apps/web`: `npm test`, `npm run typecheck`, `npm run contracts:check`, `npm run format:check`, `npm run build`.

With Python and Next.js running: `npm run test:evidence-api` (optional `WEB_BASE_URL`). It targets the current synthetic R2-01 skeleton and verifies HTTP text import, no implicit run on import/failure, PDF 501 propagation, one parented review, immutable v1, v1/v2 reads, and the lack of evidence-driven revisions. Update its expectations when R2 connects the real pipeline.

All 38 frontend tests pass, along with TypeScript, contract drift, formatting, production build and `git diff --check`. The real HTTP smoke check also passes. The unit suite covers unchanged categories, wrong parents/cases, incorrect/omitted changes, import errors, multipart handling, limits, origins and stalled upload deadlines. Browser checks cover fixture versions, exact excerpts, API text import and explicit review, parent reopening, a visible review failure, PDF 501, and oversized PDF rejection. Layout checks at 390px and 1280px show no horizontal overflow.

## Remaining dependencies

- **R2 #7/#14:** persistent storage, pipeline/report assembly, connection of R3's importer to the endpoints, and evidence-driven revisions. PDF currently returns 501. Runs copy fixed synthetic reports and ignore uploaded evidence; unrelated evidence also produces the fixed safety revision.
- **R3 #12:** complete semantic/leakage audit and final-chair claim auditing.
- **R5 #13:** final decision/claim links and explanation from chair synthesis.
- **R1:** verify safety/unrelated updates, readable/unreadable PDFs, private provenance, wrong parents, failures, persistence and reload against the integrated pipeline before closing #15.

There is no report-by-ID endpoint: the parent version defaults to the preceding version and can be selected for a branch from an older report. Comparisons require the selected report's ID to match `parent_report_id`.

No shared API schemas or Python code are changed. Existing uncommitted sample/role-preview changes were preserved.
