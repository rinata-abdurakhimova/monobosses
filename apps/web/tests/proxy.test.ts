import assert from "node:assert/strict";
import test from "node:test";
import { proxyBackend } from "../lib/api/backend-proxy.ts";

const baseUrl = "http://python.internal/v1";
test("proxy accepts the browser host when Next uses localhost internally", async () => {
  const response = await proxyBackend(
    new Request("http://localhost:3000/api/backend/cases", {
      method: "POST",
      headers: {
        Host: "127.0.0.1:3000",
        Origin: "http://127.0.0.1:3000",
        "Content-Type": "application/json",
      },
      body: "{}",
    }),
    ["cases"],
    {
      baseUrl,
      fetcher: async () =>
        Response.json({ case_id: "case-1" }, { status: 201 }),
    },
  );
  assert.equal(response.status, 201);
});
function request(path = "cases", init: RequestInit = {}) {
  return new Request(`http://localhost:3000/api/backend/${path}`, init);
}

test("proxy forwards JSON and status without browser secrets or upstream cookies", async () => {
  const response = await proxyBackend(
    request("cases", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Cookie: "private=1",
        Authorization: "browser-secret",
        Origin: "http://localhost:3000",
      },
      body: JSON.stringify({ indication: "Disease" }),
    }),
    ["cases"],
    {
      baseUrl,
      fetcher: async (url, init) => {
        assert.equal(url, `${baseUrl}/cases`);
        assert.equal(init?.method, "POST");
        assert.equal(init?.redirect, "error");
        assert.equal(init?.cache, "no-store");
        const headers = new Headers(init?.headers);
        assert.equal(headers.get("cookie"), null);
        assert.equal(headers.get("authorization"), null);
        assert.deepEqual(JSON.parse(String(init?.body)), {
          indication: "Disease",
        });
        return Response.json(
          { case_id: "case-1" },
          { status: 201, headers: { "Set-Cookie": "upstream=secret" } },
        );
      },
    },
  );
  assert.equal(response.status, 201);
  assert.equal(response.headers.get("set-cookie"), null);
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("proxy preserves backend error envelopes for 422/404/500", async () => {
  for (const status of [422, 404, 500]) {
    const error = {
      error: {
        code: "backend_error",
        message: "Useful explanation",
        retryable: false,
      },
    };
    const response = await proxyBackend(
      request("runs/run-1"),
      ["runs", "run-1"],
      {
        baseUrl,
        fetcher: async () => Response.json(error, { status }),
      },
    );
    assert.equal(response.status, status);
    assert.deepEqual(await response.json(), error);
  }
});

test("proxy rejects unsupported routes, origins, query strings and malformed input before forwarding", async () => {
  let calls = 0;
  const options = {
    baseUrl,
    fetcher: async () => {
      calls++;
      return Response.json({});
    },
  };
  for (const [req, path, status] of [
    [request("https://evil.example"), ["https:", "evil.example"], 404],
    [request("cases/case-1/evidence"), ["cases", "case-1", "evidence"], 404],
    [request("runs/run-1?url=https://evil.example"), ["runs", "run-1"], 404],
    [
      request("cases", {
        method: "POST",
        headers: { Origin: "https://evil.example" },
      }),
      ["cases"],
      403,
    ],
    [request("cases", { method: "POST" }), ["cases"], 415],
    [
      request("cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "oops",
      }),
      ["cases"],
      400,
    ],
  ] as const) {
    assert.equal((await proxyBackend(req, [...path], options)).status, status);
  }
  assert.equal(calls, 0);
});

test("proxy configuration and network failures are useful and never expose the upstream URL", async () => {
  for (const url of [
    undefined,
    "file:///private",
    "http://user:secret@python.internal",
    "http://python.internal?secret=1",
  ]) {
    const response = await proxyBackend(
      request("runs/run-1"),
      ["runs", "run-1"],
      { baseUrl: url },
    );
    assert.equal(response.status, 503);
  }
  const response = await proxyBackend(
    request("runs/run-1"),
    ["runs", "run-1"],
    {
      baseUrl,
      fetcher: async () => {
        throw new Error(baseUrl);
      },
    },
  );
  assert.equal(response.status, 502);
  assert.ok(!(await response.text()).includes(baseUrl));
});

test("proxy deadline cancels a hanging mutation after one request", async () => {
  let calls = 0;
  const response = await proxyBackend(
    request("cases/case-1/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: '{"mode":"live"}',
    }),
    ["cases", "case-1", "runs"],
    {
      baseUrl,
      timeoutMs: 5,
      fetcher: async (_url, init) => {
        calls++;
        return new Promise((_resolve, reject) =>
          init!.signal!.addEventListener(
            "abort",
            () => reject(init!.signal!.reason),
            { once: true },
          ),
        );
      },
    },
  );
  assert.equal(response.status, 504);
  assert.equal(calls, 1);
});

test("proxy forwards bounded PDF multipart uploads and backend parsing failures", async () => {
  const form = new FormData();
  form.set(
    "file",
    new File(["%PDF-1.4"], "private.pdf", { type: "application/pdf" }),
  );
  form.set("title", "Private PDF");
  form.set("synthetic", "false");
  const response = await proxyBackend(
    request("cases/case-1/documents", { method: "POST", body: form }),
    ["cases", "case-1", "documents"],
    {
      baseUrl,
      fetcher: async (url, init) => {
        assert.equal(url, `${baseUrl}/cases/case-1/documents`);
        assert.ok(init?.body instanceof FormData);
        assert.equal(new Headers(init?.headers).get("content-type"), null);
        assert.equal((init!.body as FormData).get("title"), "Private PDF");
        return Response.json(
          {
            error: {
              code: "not_implemented",
              message: "PDF parser not connected",
              retryable: false,
            },
          },
          { status: 501 },
        );
      },
    },
  );
  assert.equal(response.status, 501);
  assert.equal((await response.json()).error.code, "not_implemented");
});

test("proxy rejects oversized PDF and cross-origin evidence import without forwarding", async () => {
  let calls = 0;
  const options = {
    baseUrl,
    fetcher: async () => {
      calls++;
      return Response.json({});
    },
  };
  const oversized = new FormData();
  oversized.set(
    "file",
    new File([new Uint8Array(10 * 1024 * 1024 + 1)], "big.pdf", {
      type: "application/pdf",
    }),
  );
  oversized.set("title", "Big");
  oversized.set("synthetic", "false");
  assert.equal(
    (
      await proxyBackend(
        request("cases/case-1/documents", { method: "POST", body: oversized }),
        ["cases", "case-1", "documents"],
        options,
      )
    ).status,
    413,
  );
  assert.equal(
    (
      await proxyBackend(
        request("cases/case-1/evidence", {
          method: "POST",
          headers: {
            Origin: "https://evil.example",
            "Content-Type": "application/json",
          },
          body: "{}",
        }),
        ["cases", "case-1", "evidence"],
        options,
      )
    ).status,
    403,
  );
  assert.equal(calls, 0);
});

test("upload body deadline cancels a stalled stream without forwarding", async () => {
  let cancelled = false,
    calls = 0;
  const stream = new ReadableStream({
    cancel() {
      cancelled = true;
    },
  });
  const req = new Request(
    "http://localhost:3000/api/backend/cases/case-1/documents",
    {
      method: "POST",
      headers: { "Content-Type": "multipart/form-data; boundary=stalled" },
      body: stream,
      duplex: "half",
    } as RequestInit,
  );
  const result = await proxyBackend(req, ["cases", "case-1", "documents"], {
    baseUrl,
    timeoutMs: 5,
    fetcher: async () => {
      calls++;
      return Response.json({});
    },
  });
  assert.equal(result.status, 504);
  assert.equal(cancelled, true);
  assert.equal(calls, 0);
});
