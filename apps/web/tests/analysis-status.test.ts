import assert from "node:assert/strict";
import test from "node:test";
import { analysisStatus } from "../lib/analysis-status.ts";

test("distinguishes rejected output from a substantive analysis with evidence gaps", () => {
  const gap = analysisStatus({ position: "insufficient_data" });
  const rejected = analysisStatus({
    position: "insufficient_data",
    section_content: [
      {
        structured_data: {
          node_recovery: {
            status: "analysis_unavailable",
            error_code: "scope_mismatch",
          },
        },
      },
    ],
  });
  assert.match(gap.label, /Evidence gaps/);
  assert.match(rejected.label, /output rejected/);
  assert.match(rejected.explanation!, /analysis error/);
  assert.notEqual(gap.label, rejected.label);
});

test("does not treat ordinary structured analysis or null data as recovery", () => {
  assert.equal(
    analysisStatus({
      position: "moderate",
      section_content: [{ structured_data: null }],
    }).label,
    "moderate",
  );
  assert.match(
    analysisStatus({
      position: "insufficient_data",
      section_content: [{ structured_data: { coverage: "insufficient_data" } }],
    }).label,
    /Evidence gaps/,
  );
});

test("saved market analysis with evidence-backed claims shows preliminary conclusions", () => {
  const result = analysisStatus({
    role_id: "market",
    position: "insufficient_data",
    claims: [{ support_status: "supported", evidence_ids: ["ev-1"] }],
  });
  assert.match(result.label, /Preliminary conclusions/);
  assert.match(
    analysisStatus({ position: "partial_assessment" }).label,
    /Preliminary conclusions/,
  );
  assert.match(
    analysisStatus({
      role_id: "market",
      position: "insufficient_data",
      claims: [{ support_status: "unknown", evidence_ids: [] }],
    }).label,
    /Evidence gaps/,
  );
});
