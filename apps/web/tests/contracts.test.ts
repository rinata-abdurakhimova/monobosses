import assert from "node:assert/strict";
import test from "node:test";
import reportV1 from "../../../contracts/fixtures/report-v1.json" with { type: "json" };
import reportV2 from "../../../contracts/fixtures/report-v2.json" with { type: "json" };
import caseInput from "../../../contracts/fixtures/case.json" with { type: "json" };
import { mapSyntheticReport } from "../lib/contracts/report.ts";
import { getPreviewReport } from "../lib/preview.ts";

test("shared fixture renders all sections and preserves claims, evidence and metadata", () => {
  const result = mapSyntheticReport(reportV1, caseInput);
  assert.equal(result.sections.length, 11);
  assert.equal(result.roles.length, reportV1.roles.length);
  assert.equal(result.scope, "program");
  assert.deepEqual(
    result.claims.map((c) => c.id),
    reportV1.claims.map((c) => c.id),
  );
  assert.deepEqual(result.evidence, reportV1.evidence);
  assert.equal(
    result.sources[0].published_at,
    reportV1.sources[0].published_at,
  );
  assert.equal(
    result.sources[0].content_hash,
    reportV1.sources[0].content_hash,
  );
  assert.equal(
    result.claims.find((c) => c.id === "user.program_summary")?.provenance,
    "user",
  );
  assert.deepEqual(
    result.diligence_questions.map((q) => q.why),
    reportV1.diligence_questions.map((q) => q.why_it_matters),
  );
  assert.deepEqual(result.contract, reportV1);
});

test("shared v2 contradictions retain their status and revision metadata", () => {
  const result = mapSyntheticReport(reportV2, caseInput);
  assert.equal(result.version, 2);
  assert.equal(result.recommendation, "Do Not Invest");
  assert.equal(
    result.claims.find((c) => c.id === "translation.safe_exposure")
      ?.support_status,
    "contradicted",
  );
  assert.equal(
    result.sections.find((s) => s.key === "human_translation_thesis")?.status,
    "Contradicted in sample",
  );
  assert.deepEqual(result.contract.revision, reportV2.revision);
});

test("invalid fields and missing sections cannot silently disappear from the report", () => {
  for (const defect of [
    "status",
    "provenance",
    "section",
    "duplicate",
    "questions",
    "source",
    "role-risk",
    "claim-evidence",
    "real",
  ]) {
    const data = structuredClone(reportV1);
    if (defect === "status") data.claims[0].support_status = "made_up";
    if (defect === "provenance") data.claims[0].provenance = "made_up";
    if (defect === "section") data.sections.pop();
    if (defect === "duplicate") data.sections[1] = data.sections[0];
    if (defect === "questions") data.diligence_questions = [];
    if (defect === "source") data.evidence[0].source_id = "missing";
    if (defect === "role-risk")
      data.roles[0].risks[0].claim_ids = ["science.missing"];
    if (defect === "claim-evidence") data.claims[0].evidence_ids = [];
    if (defect === "real") data.synthetic = false;
    assert.throws(() => mapSyntheticReport(data, caseInput), Error, defect);
  }
  assert.throws(() =>
    mapSyntheticReport(reportV1, { ...caseInput, scope: "approach" }),
  );
});

test("source outage is a labelled presentation simulation and leaves the shared fixture intact", () => {
  const result = getPreviewReport("unavailable");
  assert.equal(result.sources.filter((s) => !s.available).length, 1);
  assert.equal(
    result.sources.find((s) => s.id === "src-synthetic-04")?.available,
    false,
  );
  assert.equal(
    result.claims.find((c) => c.id === "market.company_claims")?.support_status,
    "unverified",
  );
  assert.ok(getPreviewReport("complete").sources.every((s) => s.available));
});
