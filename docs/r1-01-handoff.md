# R1-01 frontend handoff

R1-01 now uses R2's merged shared contracts and synthetic fixture from PR #25.
The form and report remain explicitly fictional previews; live API integration is R1-02 (#8).

## Shared data boundary

- `contracts/openapi.json` is the wire-schema source of truth.
- `apps/web/scripts/generate-contracts.mjs` generates TypeScript types. Run `npm run contracts:generate` after agreed schema changes; `npm run contracts:check` detects drift.
- `apps/web/lib/contracts/validate.ts` checks schema structure, allowed values and field constraints. It does not replace backend Pydantic validation, evidence audit or domain evaluation.
- `apps/web/lib/contracts/report.ts` maps the shared report to presentation models, rejecting duplicate/missing sections, invalid references and evidence-backed claims without links. Raw contract data remains available.
- `apps/web/lib/fixtures/report-v1.ts` reads shared report and case JSON directly. There is no separate frontend report fixture.
- `apps/web/lib/types.ts` uses shared scope/recommendation/section/claim/source/evidence types. Form state keeps empty strings for editing optional fields.

Original Ukrainian fixture content is preserved: five role perspectives, six diligence questions and eleven sections. Counts come from data. Submitted input never changes this fixed report.

Claims preserve user provenance and contradicted status. Missing evidence links are explained. Sources retain publication/retrieval dates and hashes, labelled as fictional metadata.

## Form and scenarios

Required indication/mechanism are trimmed and checked before submission. Programme scope requires at least 40 trimmed characters of programme data, matching R2's current rule; length is a validation threshold, not proof of sufficient scientific evidence. Modality and development stage remain optional.

`/cases/sample` opens the shared report. The form supports fixed preview and the separate R1-02 browser mock workflow. Loading, failed, missing-preview and unavailable-source scenarios remain labelled. Source outage is a presentation simulation over the cached company excerpt; it does not change shared JSON.

Session namespaces were versioned so old provisional snapshots cannot appear as the current fixture. Older preview URLs may require creating a new preview. Storage is tab-local and temporary.

## Visual direction

Preserve the sage workspace, pine navigation, white cards, emerald actions, coral preview pill, teal synthetic banner, gold warnings and Inter typography. Keep the sticky breadcrumb bar, readable body text and responsive spacing. The personal profile footer stays removed. Scope is a category; unknowns are not negative findings.

## Run and validation

From `apps/web`: `npm ci`, then `npm run dev`. Production: `npm run build`, then `npm start`.

- `npm run contracts:check`
- `npm run typecheck`
- `npm test`: transport/polling/persistence, shared fixture mapping and invalid-reference/enum/section regression checks.
- `npm run format:check`
- `npm run build`

Browser review covers all 11 sections, source metadata/evidence dialogs, form validation, failure/source outage/missing preview and desktop/mobile readability. Screenshots belong in Git-ignored `apps/web/artifacts`.

## Remaining work outside R1-01

- R1-02: server proxy, live report adapter and real runtime checks; R2-02's live pipeline remains a dependency.
- R1-03: uploads, backend evidence drill-down and revision comparison.
- R1-04: deployment.
- R4/R5: domain quality review and their outstanding issue requirements. Fixture tests do not establish recommendation quality.

After this alignment PR is merged, R1-01 (#3) can be closed. Do not close R1-02 (#8) on synthetic results.
