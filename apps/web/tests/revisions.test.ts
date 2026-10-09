import assert from "node:assert/strict";
import test from "node:test";
import first from "../../../contracts/fixtures/report-v1.json" with { type: "json" };
import second from "../../../contracts/fixtures/report-v2.json" with { type: "json" };
import { mapApiReport } from "../lib/contracts/report.ts";
import { validateRevisionPair } from "../lib/revisions.ts";
import { createHttpApiClient } from "../lib/api/http-client.ts";

test("shared safety revision matches its immutable parent and exact changed claims", () => {
  const before = mapApiReport(first),
    after = mapApiReport(second);
  validateRevisionPair(before, after);
  assert.equal(before.recommendation, "Conditional");
  assert.equal(after.recommendation, "Do Not Invest");
  const mismatched = structuredClone(after);
  mismatched.contract.revision!.parent_report_id = "other-parent";
  assert.throws(() => validateRevisionPair(before, mismatched));
  const altered = structuredClone(after);
  altered.contract.revision!.changed_claims[0].before!.text =
    "Invented prior claim";
  assert.throws(() => validateRevisionPair(before, altered));
  const differentCase = structuredClone(before);
  differentCase.contract.case_id = "another-case";
  assert.throws(() => validateRevisionPair(differentCase, after));
  const incomplete = structuredClone(after);
  incomplete.contract.revision!.changed_claims = [];
  assert.throws(() => validateRevisionPair(before, incomplete));
});

test("an unchanged backend recommendation is valid without inventing a change", () => {
  const before = mapApiReport(first),
    after = mapApiReport(second);
  after.recommendation = before.recommendation;
  after.contract.recommendation = before.recommendation;
  after.contract.revision!.new_recommendation = before.recommendation;
  after.contract.revision!.explanation = "The category is unchanged.";
  validateRevisionPair(before, after);
});

test("text/PDF imports never start a run; explicit review forwards the parent and mode once", async () => {
  const requests: { path: string; init?: RequestInit }[] = [];
  const client = createHttpApiClient({
    fetcher: async (url, init) => {
      requests.push({ path: String(url), init });
      return Response.json(
        String(url).endsWith("runs")
          ? { run_id: "run-2" }
          : { source_id: "source-1", evidence_ids: ["evidence-1"] },
      );
    },
  });
  await client.addEvidence("case-1", {
    title: "Private text",
    text: "Some evidence",
    synthetic: false,
  });
  await client.uploadDocument(
    "case-1",
    new File(["%PDF-1.4"], "update.pdf", { type: "application/pdf" }),
    "Safety update",
    true,
    { publishedAt: "2026-10-08", scope: "program" },
  );
  assert.equal(requests.length, 2);
  assert.ok(requests[1].init?.body instanceof FormData);
  assert.equal(
    new Headers(requests[1].init?.headers).get("content-type"),
    null,
  );
  assert.equal((requests[1].init!.body as FormData).get("synthetic"), "true");
  assert.equal(
    (requests[1].init!.body as FormData).get("published_at"),
    "2026-10-08",
  );
  assert.equal((requests[1].init!.body as FormData).get("scope"), "program");
  await client.startRun("case-1", {
    parentReportId: "report-1",
    mode: "evidence_only",
  });
  assert.deepEqual(JSON.parse(String(requests[2].init?.body)), {
    parent_report_id: "report-1",
    mode: "evidence_only",
  });
  assert.equal(requests.filter((r) => r.path.endsWith("runs")).length, 1);
});

test("PDF parsing failure remains an error and creates no follow-up request", async () => {
  let calls = 0;
  const client = createHttpApiClient({
    fetcher: async () => {
      calls++;
      return Response.json(
        {
          error: {
            code: "unreadable_document",
            message: "No readable text",
            retryable: false,
          },
        },
        { status: 422 },
      );
    },
  });
  await assert.rejects(
    client.uploadDocument(
      "case-1",
      new File(["%PDF-1.4"], "scan.pdf", { type: "application/pdf" }),
      "Scan",
      false,
    ),
    { code: "unreadable_document", status: 422 },
  );
  assert.equal(calls, 1);
});
