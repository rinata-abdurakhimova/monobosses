import { test } from "node:test";
import assert from "node:assert/strict";
import { summarizeUsage } from "../lib/usage.ts";
import type { Run } from "../lib/contracts/generated.ts";

const run = (id: string, changes: Partial<Run> = {}): Run => ({
  id,
  case_id: "case-test",
  status: "completed",
  report_version: 1,
  trace_id: `trace-${id}`,
  mode: "live",
  model_version: "real-model",
  usage: { calls: 2, input_tokens: 10, output_tokens: 5 },
  cost_usd: null,
  ...changes,
});
test("cost sample excludes unknown, failed and synthetic runs without replacing unknown with zero", () => {
  const summary = summarizeUsage([
    run("one", { cost_usd: 1 }),
    run("two", { cost_usd: 3 }),
    run("unknown"),
    run("failed", { status: "failed", cost_usd: 50 }),
    run("mock", { model_version: "mock", cost_usd: 100 }),
    run("stub", { model_version: "stub", cost_usd: 100 }),
  ]);
  assert.equal(summary.average, 2);
  assert.equal(summary.min, 1);
  assert.equal(summary.max, 3);
  assert.equal(summary.priced, 2);
  assert.equal(summary.completed, 3);
  assert.equal(summary.calls, 12);
  assert.equal(summarizeUsage([run("unknown")]).average, null);
  assert.equal(summarizeUsage([run("zero", { cost_usd: 0 })]).average, 0);
});
