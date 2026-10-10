import type { Run } from "./contracts/generated.ts";

export function summarizeUsage(runs: Run[]) {
  const completed = runs.filter(
    (run) =>
      run.status === "completed" &&
      run.mode === "live" &&
      run.usage &&
      (run.usage.calls ?? 0) > 0 &&
      run.model_version &&
      !["mock", "stub"].includes(run.model_version),
  );
  const priced = completed.filter(
    (run) =>
      typeof run.cost_usd === "number" &&
      Number.isFinite(run.cost_usd) &&
      run.cost_usd >= 0,
  );
  const costs = priced.map((run) => run.cost_usd as number);
  return {
    completed: completed.length,
    priced: priced.length,
    average: costs.length
      ? costs.reduce((a, b) => a + b, 0) / costs.length
      : null,
    min: costs.length ? Math.min(...costs) : null,
    max: costs.length ? Math.max(...costs) : null,
    calls: runs.reduce((sum, run) => sum + (run.usage?.calls ?? 0), 0),
  };
}
