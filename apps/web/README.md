# Committee frontend (R1)

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

Dependencies are pinned in `package.json` and `package-lock.json`. For Python API assessments, copy `.env.example` to `.env.local` and set server-only `API_BASE_URL` to the Python service (normally `http://127.0.0.1:8000`). Restart Next.js after changing it. Preview workflows need no environment variables. Inter needs browser access to Google Fonts; when unavailable, the interface uses its Arial/sans-serif fallback.

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

## Python API integration (#8)

The form defaults to **Python API assessment**. One submission creates a case, starts one run with `mode: live`, then opens `/cases/{caseId}?flow=api&run={runId}`. Status reads and the final report version pass through the same-origin `/api/backend` route. Refreshing or **Check existing run again** performs reads only; no POST is automatically retried. Navigation aborts polling. Status checks pause after ten minutes and can resume against the same run.

Start the Python API using `services/api/README.md`, copy `.env.example` to `.env.local`, then run Next.js. `API_BASE_URL` is read only in the server route; never give it a `NEXT_PUBLIC_` prefix. Provider secrets remain in Python. The proxy allows only the four assessment operations, rejects cross-origin mutations and redirects, strips browser credentials and upstream cookies, disables caching, and gives upstream requests an eight-second deadline. Browser requests have a ten-second deadline. Backend errors retain their status and error envelope. Missing configuration returns an explicit 503; no request falls back to a fixture.

The backend on current main is still the R2-01 skeleton: real HTTP returns a fixed synthetic report, not analysis of the submitted input. The report scope and synthetic flags come from Python, even when the skeleton's fixed programme scope differs from the submitted approach. Reports and runs are stored in memory and disappear on Python restart. Real pipeline verification and durable storage remain R2 dependencies; this change does not close #8. Authentication with `API_SHARED_SECRET` is pending R2's agreed header contract; the current skeleton does not enforce it. Deployment remains a later task.

## Verification

```sh
npm test
npm run typecheck
npm run contracts:check
npm run format:check
npm run build
# With Python and Next.js running:
npm run test:api
```

`test:api` uses real HTTP via Next.js: creates a case/run, reads the correct report version, repeats reads to simulate reopening, verifies no additional mutation, and checks 422/404. With the current synthetic skeleton it also reads the seeded failed run. Set `WEB_BASE_URL` if Next.js uses a different local port. This command creates test records in the running Python repository.

Browser verification: submit the fictional example in API mode; check that one POST case and one POST run are followed by GET status/report; reload the URL and verify GET-only reads; open `/cases/case-synthetic-01?flow=api&run=run-synthetic-failed` to inspect a terminal failure. Unit tests cover request deadlines, cancellation, terminal polling, backend error decoding, proxy restrictions, and report validation.

## Data boundary and previews

- `app/api/backend/[...path]/route.ts`: server environment and Next.js proxy handler.
- `lib/api/backend-proxy.ts`: restricted transport, errors and cancellation.
- `lib/api/http-client.ts`: typed HTTP operations; no automatic mutation retries.
- `lib/api/types.ts`: shared OpenAPI status/stage types and client interfaces.
- `lib/api/poll-run.ts`: sequential cancellable GET-only polling.
- `lib/contracts/report.ts`: validates received reports and preserves all 11 sections, claims, roles, references and synthetic flags. `mapSyntheticReport` additionally enforces fixture-only previews.
- `lib/contracts/generated.ts`: shared wire types generated from `contracts/openapi.json`; regenerate with `npm run contracts:generate` after agreed changes.
- `components/ApiCase.tsx`: existing-run lifecycle, report loading, warnings and errors.
- `scripts/check-python-api.ts`: repeatable HTTP integration verification.

**Fixed fictional report preview** and **Mock API workflow** remain explicit local options. Mock scenarios cover completion, failure, missing records, validation, connection interruption, malformed responses, unavailable sources and polling timeout. Their tab-local storage is separate from the API workflow. `/cases/sample` opens the shared synthetic fixture without contacting Python.

Shared fixtures and API-owned display text use English, as specified in `docs/implementation-contract.md`. Fixture translations are made in the Python generator and regenerated with their source hashes and exact evidence excerpts. Restart Python and rebuild/restart the frontend to pick up fixture changes. Previously saved report snapshots are not translated in place; create a new assessment or open the rebuilt example report.

Uploads and before/after comparison belong to #15. Live analysis and persisted reload after a Python restart still require R2's pipeline/storage work.
