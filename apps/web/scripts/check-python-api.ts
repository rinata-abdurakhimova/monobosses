import assert from "node:assert/strict";
import { createHttpApiClient } from "../lib/api/http-client.ts";
import { mapApiReport } from "../lib/contracts/report.ts";
import { pollRun } from "../lib/api/poll-run.ts";
import { ApiError } from "../lib/api/errors.ts";

// Run with both servers started. Uses real HTTP through the Next.js route.
const origin = process.env.WEB_BASE_URL ?? "http://127.0.0.1:3000";
const requests: { method: string; url: string }[] = [];
const client = createHttpApiClient({
  mapReport: mapApiReport,
  fetcher: async (path, init) => {
    requests.push({ method: init?.method ?? "GET", url: String(path) });
    return fetch(new URL(String(path), origin), init);
  },
});
const input = {
  indication: "Synthetic HTTP integration check",
  mechanism: "Synthetic target",
  scope: "approach" as const,
  modality: "",
  development_stage: "",
  program_data: "",
};
const created = await client.createCase(input);
const started = await client.startRun(created.case_id);
const completed = await pollRun(client, started.run_id, { maxWaitMs: 600000 });
assert.equal(completed.status, "completed");
const report = await client.getReport(
  created.case_id,
  completed.report_version!,
);
assert.equal(report.run_id, started.run_id);
assert.equal(report.content.sections.length, 11);
const postCount = requests.filter((r) => r.method === "POST").length;
const reloaded = await pollRun(client, started.run_id);
assert.deepEqual(
  await client.getReport(created.case_id, reloaded.report_version!),
  report,
);
assert.equal(requests.filter((r) => r.method === "POST").length, postCount);
assert.equal(postCount, 2);
for (const status of [422, 404]) {
  await assert.rejects(
    status === 422
      ? client.createCase({ ...input, indication: "" })
      : client.getRun("missing-http-check"),
    (error) => error instanceof ApiError && error.status === status,
  );
}
// The current skeleton provides a failed run for a real HTTP failure check.
if (completed.warnings.some((warning) => warning.startsWith("MOCK:"))) {
  const failed = await pollRun(client, "run-synthetic-failed");
  assert.equal(failed.status, "failed");
  assert.ok(failed.error?.message);
}
console.log(
  JSON.stringify(
    {
      case_id: created.case_id,
      run_id: started.run_id,
      version: report.version,
      synthetic: report.content.synthetic,
      refresh_created_new_run: false,
      errors_checked: [422, 404],
    },
    null,
    2,
  ),
);
