# Committee frontend preview (R1-01)

Next.js App Router + TypeScript UI for the independent part of [R1-01](https://github.com/rinata-abdurakhimova/monobosses/issues/3). No Python service, model key, or R2-generated fixture is required.

## Visual direction

Rinata's preference is a light, pretty, airy interface with comfortably readable text. Use white surfaces, soft lavender/blush accents, pale report cards, 16–17px body/form text, and secondary labels of at least 12px. Keep large panels light; use stronger colour for small accents and buttons. Mobile layouts must not reduce text to fit.

## Run

Requires Node.js 20.9+ and npm. From this directory:

```sh
npm ci
npm run dev
```

Open `http://127.0.0.1:3000`. For a production preview:

```sh
npm run typecheck
npm run build
npm start
```

Dependencies are pinned in `package.json` and `package-lock.json`. No environment variables or external fonts are required.

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

- `lib/types.ts`: provisional frontend view models, pending R2's contracts v1.
- `lib/fixtures/report-v1.ts`: fixed fictional report, local to R1. It does not create or overwrite `contracts/fixtures/report-v1.json`.
- `lib/preview.ts`: explicit local preview storage and fixture selection. It makes no API or model calls.
- `components/CaseForm.tsx`: input and validation.
- `components/CasePreview.tsx`: preview-only lifecycle, error and empty states.
- `components/ReportView.tsx`, `ReportSections.tsx`, `RecommendationCard.tsx`, `RoleCard.tsx`: report rendering.

Input is saved only in this browser tab's session storage; it is not sent to a backend or used to generate recommendations. The report remains the fictional disease X / AX-17 example regardless of entered input. A refresh replays the short simulated lifecycle; this is not server persistence.

## Pending R2 / later tasks

Adopt R2's OpenAPI and shared fixtures when supplied, with a single adapter at the data boundary. Real API requests/polling belong to R1-02. Uploads and report revisions belong to R1-03; deployment belongs to R1-04. This work does not finish backend-dependent contract alignment or close R1-01 automatically.
