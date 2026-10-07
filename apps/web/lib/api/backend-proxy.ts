/** Server transport. Only the route handler supplies server environment values. */
export async function proxyBackend(
  request: Request,
  segments: string[],
  options: {
    baseUrl?: string;
    fetcher?: typeof fetch;
    timeoutMs?: number;
  } = {},
): Promise<Response> {
  const path = segments.join("/");
  const id = "[A-Za-z0-9][A-Za-z0-9._-]{0,127}";
  const allowed =
    request.method === "POST"
      ? path === "cases" || new RegExp(`^cases/${id}/runs$`).test(path)
      : request.method === "GET" &&
        (new RegExp(`^runs/${id}$`).test(path) ||
          new RegExp(`^cases/${id}/reports/[1-9][0-9]*$`).test(path));
  const fail = (
    status: number,
    code: string,
    message: string,
    retryable = false,
  ) =>
    Response.json(
      { error: { code, message, retryable } },
      {
        status,
        headers: { "Cache-Control": "no-store" },
      },
    );
  if (!allowed || new URL(request.url).search)
    return fail(404, "not_found", "This API operation is not available.");
  // Reject cross-origin mutations; no browser credentials are forwarded upstream.
  const origin = request.headers.get("origin");
  // Next can construct request.url with localhost while the browser uses 127.0.0.1.
  const requestUrl = new URL(request.url);
  const publicOrigin = `${requestUrl.protocol}//${request.headers.get("host") ?? requestUrl.host}`;
  if (
    request.method === "POST" &&
    ((origin && origin !== publicOrigin) ||
      request.headers.get("sec-fetch-site") === "cross-site")
  )
    return fail(403, "forbidden", "Use this application's assessment form.");
  let base: URL;
  try {
    if (!options.baseUrl) throw new Error();
    base = new URL(options.baseUrl);
    if (
      !["http:", "https:"].includes(base.protocol) ||
      base.username ||
      base.password ||
      base.search ||
      base.hash
    )
      throw new Error();
  } catch {
    return fail(
      503,
      "API_NOT_CONFIGURED",
      "The Python API connection is not configured on the server.",
    );
  }
  const controller = new AbortController();
  const cancel = () => controller.abort(request.signal.reason);
  request.signal.addEventListener("abort", cancel, { once: true });
  if (request.signal.aborted) cancel();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs ?? 8000);
  try {
    let body: string | undefined;
    if (request.method === "POST") {
      if (
        !request.headers
          .get("content-type")
          ?.toLowerCase()
          .startsWith("application/json")
      )
        return fail(
          415,
          "invalid_content_type",
          "Send assessment input as JSON.",
        );
      body = await request.text();
      if (new TextEncoder().encode(body).length > 64 * 1024)
        return fail(
          413,
          "input_too_large",
          "The assessment input is too large.",
        );
      try {
        JSON.parse(body);
      } catch {
        return fail(
          400,
          "invalid_json",
          "The assessment input is not valid JSON.",
        );
      }
    }
    const upstream = await (options.fetcher ?? fetch)(
      `${base.href.replace(/\/$/, "")}/${path}`,
      {
        method: request.method,
        headers: {
          Accept: "application/json",
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body,
        cache: "no-store",
        redirect: "error",
        signal: controller.signal,
      },
    );
    let data: unknown;
    try {
      data = await upstream.json();
    } catch {
      return fail(
        502,
        "INVALID_RESPONSE",
        "The Python API returned an unreadable response.",
        true,
      );
    }
    return Response.json(data, {
      status: upstream.status,
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return fail(
      controller.signal.aborted ? 504 : 502,
      controller.signal.aborted ? "REQUEST_TIMEOUT" : "BACKEND_UNAVAILABLE",
      "The Python API request could not finish. It was not automatically resubmitted.",
      true,
    );
  } finally {
    clearTimeout(timer);
    request.signal.removeEventListener("abort", cancel);
  }
}
