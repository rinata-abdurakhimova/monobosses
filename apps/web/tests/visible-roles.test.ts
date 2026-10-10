import assert from "node:assert/strict";
import test from "node:test";
import { isVisibleRole } from "../lib/visible-roles.ts";

test("only the seven specialists and Chair remain visible", () => {
  for (const id of ["audit", "investment_threshold", "failure_miner"])
    assert.equal(isVisibleRole(id), false);
  for (const id of [
    "science",
    "translation",
    "clinical",
    "market",
    "ip_licensing",
    "partnerships",
    "investment",
    "chair",
  ])
    assert.equal(isVisibleRole(id), true);
});
