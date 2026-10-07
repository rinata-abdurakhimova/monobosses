# Committee frontend preview (R1-01)

Next.js App Router + TypeScript UI for the independent part of [R1-01](https://github.com/rinata-abdurakhimova/monobosses/issues/3). No Python service, model key, or R2-generated fixture is required.

## Visual direction

The current reference uses a richer sage workspace, a deep pine navigation sidebar, elevated white cards, and emerald actions. Coral identifies the preview label, teal frames the synthetic banner, and gold highlights conditions and warnings. Unknown counts use terracotta badges; document and perspective counts use violet. Inter is loaded via a Google Fonts CSS import, with Arial/sans-serif fallback. Use the requested 30px/800 dark-green report heading, 20px/700 card headings, 13.5px actions/navigation, 12.5px metrics/callouts, and 10px uppercase categories. Main body/form text remains 16–17px. Metric numbers use tabular figures. Preserve high contrast and adjust spacing rather than shrinking mobile text. The breadcrumb bar sticks to the top; anchor offsets keep report sections visible beneath it. Use custom CSS, not Tailwind. The personal profile footer stays removed. Metrics use actual report counts; the green scope pill identifies a category, not a validated investment outcome.

## Run

Requires Node.js 22.18+ and npm (Node 24 was used for verification). The test command uses Node's built-in TypeScript support. From this directory:

```sh
npm ci
npm run dev
```

Open `http://127.0.0.1:3000`. For a production preview:

```sh
npm run typecheck
npm test
npm run build
npm start
```

Dependencies are pinned in `package.json` and `package-lock.json`. No environment variables are required. Inter needs browser access to Google Fonts; when unavailable, the interface uses its Arial/sans-serif fallback.

## Code formatting

Run `npm run format` to format frontend code, or `npm run format:check` to verify it. Prettier uses two-space indentation, an 80-character preferred line width, and one JSX attribute per line. JSX elements, function bodies, and fixture objects stay readable across multiple lines. Long strings may exceed the preferred line width without being split into different values.

## What to try

1. Submit the empty form: required indication and mechanism validation appears, with focus on the first invalid field.
2. Use **Use fictional example**, then **Preview assessment**. A simulated progress sequence leads to the fixed synthetic report.
3. Open **Additional context** for modality, stage, and programme data. A programme assessment requires supplied programme data; an approach does not.
4. Open **Preview states** and choose a simulated failed run or an unavailable source before submitting.
5. Open `http://127.0.0.1:3000/cases/sample` to view the completed report immediately.
6. Expand the 11 report sections, inspect a claim in the evidence dialog, and read the seven illustrative role cards.
7. Open an unknown `/cases/...` URL: a missing-local-preview state explains how to recover.

The evidence dialog is a local fixture display for review, not an implemented backend evidence drill-down or R1-03 upload/revision flow.

## Data boundary

R1-02 preparation adds a separate **Mock API workflow** selection to the form. It calls `createCase` once, `startRun` once, then polls `getRun` and reads the returned report version with `getReport`. The case/run identifiers remain in the URL; reload and **Check existing run again** only read the existing records. Mock records and completed report snapshots are stored in a separate tab-local namespace from the original fixed fixture preview.

In **Preview states**, the mock workflow can simulate completion, failed runs, missing records, validation errors, one connection interruption, invalid responses, unavailable sources, and an 8-second polling deadline. Cancellation removes timers/listeners and aborts in-flight reads. A connection interruption can be resumed on the same run; a timeout never submits another run.

- `lib/api.ts`: public client boundary and polling exports.
- `lib/api/types.ts`: provisional request/run/client types, pending OpenAPI.
- `lib/api/mock-client.ts`: local simulated service, saved run/report versions.
- `lib/api/http-client.ts`: replaceable HTTP adapter with error decoding, response checks, request deadlines, and no automatic mutation retries.
- `lib/api/poll-run.ts`: sequential, cancellable GET-only polling.
- `components/ApiCase.tsx`: mock lifecycle and recovery UI.
- `tests/api.test.ts`: meaningful transport, polling, and persistence checks.

The HTTP adapter defaults to `/api/backend`, a future same-origin server proxy. That proxy is **not implemented or enabled yet**. Shared OpenAPI is now available, while host/auth configuration and live pipeline verification remain pending. The HTTP report stays unknown until a live `mapReport` adapter is supplied; it is never silently replaced with the synthetic fixture. No backend URL, API key or LLM credential is exposed to the browser.

- `lib/contracts/generated.ts`: TypeScript wire types generated from `contracts/openapi.json`. Run `npm run contracts:generate` after agreed schema changes; `npm run contracts:check` detects drift.
- `lib/contracts/report.ts`: synthetic-report adapter with schema/reference checks and all 11 sections. Raw contract data remains available alongside presentation fields.
- `lib/types.ts`: presentation models using shared scope, recommendation, section, claim, source and evidence types.
- `lib/fixtures/report-v1.ts`: reads R2's shared `report-v1.json` and `case.json`; there is no independent R1 report copy.
- `lib/preview.ts`: explicit local preview storage and fixture selection. It makes no API or model calls.
- `components/CaseForm.tsx`: input and validation.
- `components/CasePreview.tsx`: preview-only lifecycle, error and empty states.
- `components/ReportView.tsx`, `ReportSections.tsx`, `RecommendationCard.tsx`, `RoleCard.tsx`: report rendering.

Input is saved only in this browser tab's session storage; it is not sent to a backend or used to generate recommendations. The report remains R2's fixed fictional disease X / target Y example regardless of entered input. Original Ukrainian content is preserved. A refresh replays the short simulated lifecycle; this is not server persistence. Session namespaces were versioned during alignment, so older preview URLs may require creating a new preview.

## Pending R2 / later tasks

R1-01 is aligned with R2's shared OpenAPI and synthetic fixture. R1-02 still needs the server proxy, live report mapping and verification against the Python runtime; PR #25 provides mock routes only. Uploads and report revisions belong to R1-03; deployment belongs to R1-04. This work does not close #8.
