import assert from "node:assert/strict";
import test from "node:test";
import reportV1 from "../../../contracts/fixtures/report-v1.json" with { type: "json" };
import reportV2 from "../../../contracts/fixtures/report-v2.json" with { type: "json" };
import reportR5 from "../../../contracts/fixtures/report-r5.json" with { type: "json" };
import caseInput from "../../../contracts/fixtures/case.json" with { type: "json" };
import { mapSyntheticReport, mapApiReport } from "../lib/contracts/report.ts";
import { getPreviewReport } from "../lib/preview.ts";
import { validateContract } from "../lib/contracts/validate.ts";

test("API mapping preserves real and synthetic report flags without fabricating fixture data", () => {
  const real = structuredClone(reportV1);
  real.synthetic = false;
  real.sources.forEach((s) => {
    s.synthetic = false;
  });
  const result = mapApiReport(real);
  assert.equal(result.synthetic, false);
  assert.equal(result.scope, real.scope);
  assert.deepEqual(result.contract, real);
  assert.equal(
    result.sections.find((s) => s.key === "scientific_thesis")?.status,
    "Uncertain",
  );
  assert.equal(mapApiReport(reportV1).synthetic, true);
  const broken = structuredClone(real);
  broken.evidence[0].source_id = "missing";
  assert.throws(() => mapApiReport(broken));
});

test("all seven R5 roles and R3/R4 perspectives retain their reasoning and evidence", () => {
  validateContract("Report", reportR5);
  const result = mapSyntheticReport(reportR5, caseInput);
  assert.equal(result.sections.length, 11);
  assert.equal(result.roles.length, 11);
  for (const id of [
    "market",
    "investment",
    "failure_miner",
    "chair",
    "investment_threshold",
    "partnerships",
    "ip_licensing",
    "science",
    "translation",
    "clinical",
    "audit",
  ]) {
    const actual = result.roles.find((r) => r.id === id)!;
    const original = reportR5.roles.find((r) => r.role_id === id)!;
    assert.ok(actual.name && actual.initials, id);
    assert.deepEqual(actual.claims, original.claims);
    assert.deepEqual(actual.risks, original.risks);
    assert.deepEqual(actual.unknowns, original.unknowns);
    assert.deepEqual(actual.change_conditions, original.change_conditions);
    assert.deepEqual(actual.section_content, original.section_content);
    for (const claim of actual.claims) {
      for (const evidenceId of claim.evidence_ids) {
        const evidence = result.evidence.find((e) => e.id === evidenceId)!;
        assert.ok(evidence);
        assert.ok(result.sources.some((s) => s.id === evidence.source_id));
      }
    }
  }
});

test("future roles display safely, while strict contract validation still rejects them", () => {
  for (const id of ["future_expert", "constructor", "__proto__"]) {
    const data = structuredClone(reportR5);
    data.roles[0].role_id = id;
    data.disagreements[0].role_ids[0] = id;
    // __proto__ is not a valid expert identifier and is rejected at the boundary.
    if (id === "__proto__") {
      assert.throws(() => mapSyntheticReport(data, caseInput));
      continue;
    }
    assert.throws(() => validateContract("Report", data));
    const result = mapSyntheticReport(data, caseInput);
    assert.equal(result.roles[0].name, `Additional perspective (${id})`);
    assert.equal(result.roles[0].initials, "AI");
    assert.deepEqual(result.roles[0].claims, data.roles[0].claims);
    assert.deepEqual(
      result.roles[0].change_conditions,
      data.roles[0].change_conditions,
    );
    assert.ok(result.disagreements.includes(data.disagreements[0].summary));
  }
});

test("future role fallback keeps other validation and reference checks strict", () => {
  for (const defect of [
    "status",
    "evidence",
    "role-evidence",
    "risk",
    "field",
    "empty-id",
  ]) {
    const data = structuredClone(reportR5);
    data.roles[0].role_id = "future_expert";
    if (defect === "status")
      data.roles[0].claims[0].support_status = "invented";
    if (defect === "evidence") data.claims[0].evidence_ids = ["missing"];
    if (defect === "role-evidence")
      data.roles[0].claims[0].evidence_ids = ["missing"];
    if (defect === "risk")
      data.roles[0].risks[0].claim_ids = ["science.missing"];
    if (defect === "field") Object.assign(data.roles[0], { unexpected: true });
    if (defect === "empty-id") data.roles[0].role_id = "";
    assert.throws(() => mapSyntheticReport(data, caseInput), Error, defect);
  }
});

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
