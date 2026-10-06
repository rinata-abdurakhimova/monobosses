# R1-01 frontend handoff

Implemented by R1 on `codex/r1-01-synthetic-ui`, independently of R2's pending API and fixtures. This document records the working preview, not completion of shared contract alignment.

## Visual direction

Rinata requested a light, pretty design with larger, easy-to-read text. The preview uses white surfaces, soft lavender and blush accents, pale recommendation cards, 16–17px body/form text, and secondary labels of at least 12px. Preserve this direction in subsequent frontend work; adjust spacing rather than shrinking mobile text.

## Run and review

From `apps/web`, run `npm ci`, then `npm run dev`. Open `http://127.0.0.1:3000`; `/cases/sample` opens the fixed fictional report immediately. `npm run typecheck` and `npm run build` pass.

Dependencies: Next.js 16.3.8, React/React DOM 19.3.0, TypeScript 7.0.2; exact versions and lockfile are committed-ready. No backend service, API keys, external fonts, or model calls are needed.

## Components

| File | Responsibility |
| --- | --- |
| `apps/web/components/WorkspaceShell.tsx` | Workspace layout, navigation, visible preview status |
| `CaseForm.tsx` | Required fields, approach/program scope, optional context, UI scenario selector |
| `CasePreview.tsx` / `RunProgress.tsx` | Local simulated lifecycle, missing/failed states, timer cleanup |
| `RecommendationCard.tsx` | Conditional sample rationale and decision conditions |
| `ReportView.tsx` / `ReportSections.tsx` | All 11 sections, risks/unknowns/questions/sources, section navigation |
| `RoleCard.tsx` | Seven illustrative AI perspectives, limitations, and unknowns |
| `EvidenceDialog.tsx` | Local claim/excerpt display with modal keyboard dismissal and focus return |
| `apps/web/lib/types.ts` | Provisional UI types, not R2's authoritative API schema |
| `apps/web/lib/fixtures/report-v1.ts` | Entirely fictional, fixed report with six diligence questions |
| `apps/web/lib/preview.ts` | Session-only storage and preview scenario selection; no HTTP client |

Component paths in the table are relative to `apps/web/components` unless a full repository path is shown.

## Browser checks performed

- Empty form: indication/mechanism errors, no navigation, focus goes to first invalid field.
- Programme scope: missing programme data blocks submission and receives focus.
- Valid input: simulated progress followed by the fixed synthetic report.
- Custom indication: submitted input is kept separate; the displayed report stays fictional disease X / AX-17, with an explicit explanation.
- Completed report: 11 sections, seven perspectives, six diligence questions, visible conditions and unknowns.
- Evidence dialog: exact fictional excerpt, inference/unknown labels, no fabricated external link, Escape closes it and returns focus.
- Reload: a same-tab preview recovers from session storage and replays the simulated lifecycle.
- Failed preview: failure message and completed-example recovery work; no endless spinner.
- Unavailable source: warning, cached synthetic excerpt, unverified claim, and Data needed source section are visible.
- Missing local case: explains tab/session limits and offers recovery.
- Report navigation: choosing diligence questions expands the section and displays six questions.
- Desktop and 390px mobile layouts inspected visually; the report has no page-wide horizontal overflow at 390px or 320px. The mobile section-navigation strip scrolls within itself.
- Browser error/warning log was empty during the final checks.

Screenshots for local review are in `apps/web/artifacts`: `home-desktop.jpg`, `home-mobile.jpg`, `report-desktop.jpg`, `report-mobile.jpg`. These generated review artifacts are git-ignored.

## What R2 needs to provide

1. Authoritative input, report, claim/evidence/source, role-result, error, and run schemas / OpenAPI.
2. Shared fixture files, including `contracts/fixtures/report-v1.json`, and expected unknown/unavailable representations.
3. Working case/run/report endpoints and progress semantics.
4. Agreement on which fields are required for programme scope and how input-validation errors are returned.

Adapt these at one data boundary, then pass normalized data into the existing components. Do not replace the fictional fixture with generated claims about an arbitrary entered target.

## What R5 should review

Check the information hierarchy, the 11 section titles, decision conditions, unknown versus negative wording, prominence of critical risks, and the usefulness of the six illustrative questions. The fictional content demonstrates display behavior; it is not domain validation or an actual underwriting result.

## Remaining scope

- Shared contract and fixture alignment depends on R2-01.
- Real requests, server proxy, and polling: R1-02.
- Actual evidence uploads and report revisions: R1-03.
- Deployment: R1-04.
- Session storage is tab-local and temporary; it is not database persistence or authentication.
- This preview does not perform research, call a model, estimate real investment returns, or analyse submitted programme data.

R1-01 can be reviewed now for its independent frontend work. Do not close the issue as fully contract-aligned until R2 supplies and validates the shared schema/fixture.
