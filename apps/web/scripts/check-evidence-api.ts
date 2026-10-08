import assert from "node:assert/strict";
import { createHttpApiClient } from "../lib/api/http-client.ts";
import { mapApiReport } from "../lib/contracts/report.ts";
import { pollRun } from "../lib/api/poll-run.ts";
import { validateRevisionPair } from "../lib/revisions.ts";
import { ApiError } from "../lib/api/errors.ts";

// Real HTTP smoke check for the current R2-01 skeleton. Never proves live analysis.
const origin = process.env.WEB_BASE_URL ?? "http://127.0.0.1:3000";
const requests: { path: string; method: string }[] = [];
const client = createHttpApiClient({
  mapReport: mapApiReport,
  fetcher: async (path, init) => {
    requests.push({ path: String(path), method: init?.method ?? "GET" });
    return fetch(new URL(String(path), origin), init);
  },
});
const created = await client.createCase({
  indication: "Synthetic revision integration check",
  mechanism: "Synthetic target",
  scope: "approach",
  modality: "",
  development_stage: "",
  program_data: "",
});
const first = await client.startRun(created.case_id, { mode: "evidence_only" });
const firstRun = await pollRun(client, first.run_id);
assert.equal(firstRun.status, "completed");
const before = await client.getReport(
  created.case_id,
  firstRun.report_version!,
);
assert.ok(
  firstRun.warnings.some((w) => w.startsWith("MOCK:")),
  "This smoke check expects the synthetic R2-01 skeleton.",
);
const starts = () =>
  requests.filter((r) => r.method === "POST" && r.path.endsWith("/runs"))
    .length;
const count = starts();
const imported = await client.addEvidence(created.case_id, {
  title: "Synthetic unrelated administrative update",
  text: "No new safety or efficacy findings; synthetic test text only.",
  synthetic: true,
});
assert.ok(imported.source_id);
assert.equal(starts(), count);
await assert.rejects(
  client.uploadDocument(
    created.case_id,
    new File(["%PDF-1.4\nSynthetic parser check"], "synthetic.pdf", {
      type: "application/pdf",
    }),
    "Synthetic PDF",
    true,
  ),
  (error: unknown) => error instanceof ApiError && error.status === 501,
);
assert.equal(starts(), count);
const second = await client.startRun(created.case_id, {
  parentReportId: before.content.id,
  mode: "evidence_only",
});
const secondRun = await pollRun(client, second.run_id);
const after = await client.getReport(
  created.case_id,
  secondRun.report_version!,
);
validateRevisionPair(before.content, after.content);
assert.deepEqual(
  await client.getReport(created.case_id, before.version),
  before,
);
assert.deepEqual(await client.getReport(created.case_id, after.version), after);
assert.equal(starts(), count + 1);
assert.ok(
  !after.content.evidence.some((e) => imported.evidence_ids.includes(e.id)),
  "The mock revision does not use the imported document; this limitation must stay explicit.",
);
console.log(
  JSON.stringify(
    {
      case_id: created.case_id,
      first_run: first.run_id,
      second_run: second.run_id,
      versions: [before.version, after.version],
      import_started_run: false,
      pdf_status: 501,
      old_report_unchanged: true,
      reads_started_run: false,
      evidence_driven_revision: false,
    },
    null,
    2,
  ),
);
