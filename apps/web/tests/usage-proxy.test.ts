import assert from "node:assert/strict";
import test from "node:test";
import { proxyBackend } from "../lib/api/backend-proxy.ts";

test("usage list and traces forward through authenticated server transport", async () => {
  for (const path of ["runs", "runs/run-test/trace"]) {
    const response = await proxyBackend(
      new Request(`http://localhost/api/backend/${path}`),
      path.split("/"),
      {
        baseUrl: "http://backend.internal",
        apiSharedSecret: "server-secret",
        fetcher: async (url, options) => {
          assert.equal(String(url), `http://backend.internal/${path}`);
          assert.equal(
            new Headers(options?.headers).get("X-API-Key"),
            "server-secret",
          );
          assert.equal(options?.cache, "no-store");
          return Response.json({ ok: true });
        },
      },
    );
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  }
});
