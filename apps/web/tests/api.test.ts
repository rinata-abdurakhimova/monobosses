import assert from "node:assert/strict";
import test from "node:test";
import { createPersistedMockClient } from "../lib/api/mock-client.ts";
import { createHttpApiClient } from "../lib/api/http-client.ts";
import { pollRun } from "../lib/api/poll-run.ts";
import { ApiError } from "../lib/api/errors.ts";
import { sampleInput } from "../lib/preview.ts";
import type { MockScenario, Run } from "../lib/api/types.ts";

test("HTTP reports stay unknown unless an explicit mapper is supplied", async () => {
  const client = createHttpApiClient({
    fetcher: async () =>
      Response.json({ case_id: "case-1", run_id: "run-1", version: 1 }),
    mapReport: () => ({ label: "Mapped output" }),
  });
  assert.equal(
    (await client.getReport("case-1", 1)).content.label,
    "Mapped output",
  );
  const invalid = createHttpApiClient({
    fetcher: async () =>
      Response.json({ case_id: "case-1", run_id: "run-1", version: 1 }),
    mapReport: () => {
      throw new Error("Mapping failed");
    },
  });
  await assert.rejects(
    invalid.getReport("case-1", 1),
    code("INVALID_RESPONSE"),
  );
});

test("HTTP requests have a deadline and mutations are not resubmitted", async () => {
  let calls = 0;
  const client = createHttpApiClient({
    requestTimeoutMs: 5,
    fetcher: (_url, options) => {
      calls++;
      return new Promise((_resolve, reject) =>
        options!.signal!.addEventListener(
          "abort",
          () => reject(options!.signal!.reason),
          { once: true },
        ),
      );
    },
  });
  await assert.rejects(client.createCase(sampleInput), code("REQUEST_TIMEOUT"));
  assert.equal(calls, 1);
});

function mockSetup(scenario: MockScenario = "complete") {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
  let clock = 0;
  let ids = 0;
  const options = {
    scenario,
    storage: () => storage,
    now: () => clock,
    newId: () => String(++ids),
    latencyMs: 0,
  };
  return {
    client: createPersistedMockClient(options),
    resume: () => createPersistedMockClient(options),
    advance: () => {
      clock = 4000;
    },
    values,
  };
}
function run(status: Run["status"]): Run {
  return {
    id: "run-1",
    case_id: "case-1",
    status,
    stage: "analyze",
    report_version: status === "completed" ? 1 : null,
    warnings: [],
    error:
      status === "failed"
        ? { code: "RUN_FAILED", message: "Failed", retryable: false }
        : null,
  };
}
function code(expected: string) {
  return (error: unknown) =>
    error instanceof ApiError && error.code === expected;
}

test("mock completion persists one case/run and reload reads the same version", async () => {
  const setup = mockSetup();
  const created = await setup.client.createCase({
    ...sampleInput,
    indication: "Custom input",
  });
  const started = await setup.client.startRun(created.case_id);
  assert.equal((await setup.client.getRun(started.run_id)).status, "queued");
  setup.advance();
  const completed = await setup.client.getRun(started.run_id);
  assert.equal(completed.report_version, 1);
  const report = await setup.client.getReport(created.case_id, 1);
  assert.equal(report.run_id, started.run_id);
  assert.equal(
    report.content.title,
    `${sampleInput.indication} · ${sampleInput.mechanism}`,
  );
  assert.equal(report.content.synthetic, true);
  const reloaded = setup.resume();
  await reloaded.getRun(started.run_id);
  assert.deepEqual(await reloaded.getReport(created.case_id, 1), report);
  assert.equal(
    [...setup.values.keys()].filter((key) => key.includes(":case:")).length,
    1,
  );
  assert.equal(
    [...setup.values.keys()].filter((key) => key.includes(":run:")).length,
    1,
  );
});

test("an explicit second run gets another version without replacing version one", async () => {
  const setup = mockSetup();
  const created = await setup.client.createCase(sampleInput);
  const first = await setup.client.startRun(created.case_id);
  setup.advance();
  await setup.client.getRun(first.run_id);
  const original = await setup.client.getReport(created.case_id, 1);
  const second = await setup.client.startRun(created.case_id);
  // The second run started at the advanced clock; inject a later clock for reads.
  const later = createPersistedMockClient({
    storage: () => ({
      getItem: (key) => setup.values.get(key) ?? null,
      setItem: (key, value) => {
        setup.values.set(key, value);
      },
    }),
    now: () => 8000,
    latencyMs: 0,
  });
  assert.equal((await later.getRun(second.run_id)).report_version, 2);
  assert.deepEqual(await later.getReport(created.case_id, 1), original);
  assert.equal(
    (await later.getReport(created.case_id, 2)).run_id,
    second.run_id,
  );
});

test("network recovery checks the same mock run rather than creating another", async () => {
  const setup = mockSetup("network");
  const created = await setup.client.createCase(sampleInput);
  const started = await setup.client.startRun(created.case_id);
  await assert.rejects(
    setup.client.getRun(started.run_id),
    code("NETWORK_ERROR"),
  );
  setup.advance();
  assert.equal(
    (await setup.resume().getRun(started.run_id)).status,
    "completed",
  );
  assert.equal(
    [...setup.values.keys()].filter((key) => key.includes(":run:")).length,
    1,
  );
});

test("mock validation exposes field errors without creating a case", async () => {
  const setup = mockSetup("validation");
  await assert.rejects(
    setup.client.createCase(sampleInput),
    (error) =>
      error instanceof ApiError &&
      error.status === 422 &&
      !!error.fieldErrors.mechanism,
  );
  assert.equal(setup.values.size, 0);
});

test("polling is sequential and stops at completion", async () => {
  const states = [run("queued"), run("running"), run("completed")];
  let calls = 0;
  let active = 0;
  let maximum = 0;
  const result = await pollRun(
    {
      async getRun() {
        active++;
        maximum = Math.max(maximum, active);
        await Promise.resolve();
        active--;
        return states[calls++];
      },
    },
    "run-1",
    { intervalMs: 0 },
  );
  assert.equal(result.status, "completed");
  assert.equal(calls, 3);
  assert.equal(maximum, 1);
});

test("failed status is terminal and is not automatically retried", async () => {
  let calls = 0;
  const result = await pollRun(
    {
      async getRun() {
        calls++;
        return run("failed");
      },
    },
    "run-1",
  );
  assert.equal(result.status, "failed");
  assert.equal(calls, 1);
});

test("navigation cancellation stops further reads", async () => {
  const controller = new AbortController();
  let calls = 0;
  await assert.rejects(
    pollRun(
      {
        async getRun() {
          calls++;
          return run("running");
        },
      },
      "run-1",
      {
        signal: controller.signal,
        onUpdate() {
          controller.abort();
        },
        intervalMs: 0,
      },
    ),
    (error) => error instanceof DOMException && error.name === "AbortError",
  );
  assert.equal(calls, 1);
});

test("already-cancelled polling makes no request", async () => {
  const controller = new AbortController();
  controller.abort();
  let calls = 0;
  await assert.rejects(
    pollRun(
      {
        async getRun() {
          calls++;
          return run("running");
        },
      },
      "run-1",
      { signal: controller.signal },
    ),
  );
  assert.equal(calls, 0);
});

test("deadline aborts even a hanging status request", async () => {
  await assert.rejects(
    pollRun(
      {
        getRun(_id, options) {
          return new Promise((_resolve, reject) =>
            options!.signal!.addEventListener(
              "abort",
              () => reject(options!.signal!.reason),
              { once: true },
            ),
          );
        },
      },
      "run-1",
      { maxWaitMs: 5 },
    ),
    code("POLL_TIMEOUT"),
  );
});

test("completed runs require a valid version and matching identifier", async () => {
  await assert.rejects(
    pollRun(
      {
        async getRun() {
          return { ...run("completed"), report_version: null };
        },
      },
      "run-1",
    ),
    code("INVALID_RESPONSE"),
  );
  await assert.rejects(
    pollRun(
      {
        async getRun() {
          return { ...run("completed"), id: "different" };
        },
      },
      "run-1",
    ),
    code("INVALID_RESPONSE"),
  );
});

test("HTTP adapter makes only the four explicit operations and maps report metadata", async () => {
  const requests: { url: string; method: string; body: unknown }[] = [];
  const replies = [
    { case_id: "case-1" },
    { run_id: "run-1" },
    run("completed"),
    { case_id: "case-1", run_id: "run-1", version: 1, synthetic: true },
  ];
  const client = createHttpApiClient({
    fetcher: async (url, options) => {
      requests.push({
        url: String(url),
        method: options!.method!,
        body: options!.body ? JSON.parse(String(options!.body)) : null,
      });
      return Response.json(replies.shift());
    },
  });
  await client.createCase(sampleInput);
  await client.startRun("case-1");
  await client.getRun("run-1");
  const report = await client.getReport("case-1", 1);
  assert.equal(report.version, 1);
  assert.deepEqual(
    requests.map((request) => request.method),
    ["POST", "POST", "GET", "GET"],
  );
  assert.equal(requests[3].url, "/api/backend/cases/case-1/reports/1");
  assert.deepEqual(requests[1].body, { mode: "live", parent_report_id: null });
});

test("HTTP validation, missing records, and server failures retain their status", async () => {
  const validation = createHttpApiClient({
    fetcher: async () =>
      Response.json(
        { detail: [{ loc: ["body", "mechanism"], msg: "Invalid target" }] },
        { status: 422 },
      ),
  });
  await assert.rejects(
    validation.createCase(sampleInput),
    (error) =>
      error instanceof ApiError &&
      error.status === 422 &&
      error.fieldErrors.mechanism === "Invalid target",
  );
  for (const status of [404, 503]) {
    const client = createHttpApiClient({
      fetcher: async () =>
        Response.json(
          {
            error: {
              code: `HTTP_${status}`,
              message: "Failure",
              retryable: status === 503,
            },
          },
          { status },
        ),
    });
    await assert.rejects(
      client.getRun("run-1"),
      (error) =>
        error instanceof ApiError &&
        error.status === status &&
        error.retryable === (status === 503),
    );
  }
});

test("network and malformed responses stop without substituting a fixture", async () => {
  const network = createHttpApiClient({
    fetcher: async () => {
      throw new TypeError("Network unavailable");
    },
  });
  await assert.rejects(network.getRun("run-1"), code("NETWORK_ERROR"));
  const malformed = createHttpApiClient({
    fetcher: async () => new Response("not json"),
  });
  await assert.rejects(malformed.getRun("run-1"), code("INVALID_RESPONSE"));
  const wrongVersion = createHttpApiClient({
    fetcher: async () =>
      Response.json({ case_id: "case-1", run_id: "run-1", version: 2 }),
  });
  await assert.rejects(
    wrongVersion.getReport("case-1", 1),
    code("INVALID_RESPONSE"),
  );
  assert.throws(() =>
    createHttpApiClient({ basePath: "https://backend.example" }),
  );
});
