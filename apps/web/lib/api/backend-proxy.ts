async function readBoundedBody(
  request: Request,
  limit: number,
  signal: AbortSignal,
): Promise<Uint8Array<ArrayBuffer>> {
  signal.throwIfAborted();
  const reader = request.body?.getReader();
  if (!reader) return new Uint8Array();
  const cancel = () => {
    void reader.cancel().catch(() => {});
  };
  signal.addEventListener("abort", cancel, { once: true });
  const chunks: Uint8Array[] = [];
  let length = 0;
  try {
    while (true) {
      const next = await reader.read();
      signal.throwIfAborted();
      if (next.done) break;
      length += next.value.byteLength;
      if (length > limit) {
        await reader.cancel();
        throw new RangeError("Request body exceeds limit");
      }
      chunks.push(next.value);
    }
    const bytes = new Uint8Array(length);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.length;
    }
    return bytes;
  } finally {
    signal.removeEventListener("abort", cancel);
    reader.releaseLock();
  }
}

/** Server transport. Only the route handler supplies server environment values. */
export async function proxyBackend(
  request: Request,
  segments: string[],
  options: {
    baseUrl?: string;
    publicOrigin?: string;
    apiSharedSecret?: string;
    fetcher?: typeof fetch;
    timeoutMs?: number;
  } = {},
): Promise<Response> {
  const path = segments.join("/");
  const id = "[A-Za-z0-9][A-Za-z0-9._-]{0,127}";
  const allowed =
    request.method === "POST"
      ? path === "cases" ||
        path === "diagnostics/science" ||
        new RegExp(`^runs/${id}/resume$`).test(path) ||
        new RegExp(`^cases/${id}/(runs|evidence|documents)$`).test(path)
      : request.method === "GET" &&
        (new RegExp(`^runs/${id}(/outputs)?$`).test(path) ||
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
  let publicOrigin = `${requestUrl.protocol}//${request.headers.get("host") ?? requestUrl.host}`;
  if (options.publicOrigin !== undefined) {
    try {
      const configured = new URL(options.publicOrigin);
      if (
        !["http:", "https:"].includes(configured.protocol) ||
        configured.username ||
        configured.password ||
        configured.pathname !== "/" ||
        configured.search ||
        configured.hash
      )
        throw new Error();
      publicOrigin = configured.origin;
    } catch {
      return fail(
        503,
        "WEB_ORIGIN_NOT_CONFIGURED",
        "The website origin is not configured correctly on the server.",
      );
    }
  }
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
  const timer = setTimeout(
    () => controller.abort(),
    options.timeoutMs ?? (path === "diagnostics/science" ? 250000 : 8000),
  );
  try {
    let body: string | FormData | undefined;
    if (request.method === "POST") {
      if (path.endsWith("/documents")) {
        const limit = 10 * 1024 * 1024 + 64 * 1024;
        if (
          !request.headers
            .get("content-type")
            ?.toLowerCase()
            .startsWith("multipart/form-data")
        )
          return fail(
            415,
            "invalid_content_type",
            "Send a PDF document upload.",
          );
        if (Number(request.headers.get("content-length")) > limit)
          return fail(413, "payload_too_large", "The upload is too large.");
        // Bound streamed bodies even when Content-Length is missing or incorrect.
        const bytes = await readBoundedBody(request, limit, controller.signal);
        try {
          body = await new Response(bytes, {
            headers: { "Content-Type": request.headers.get("content-type")! },
          }).formData();
        } catch {
          return fail(400, "invalid_upload", "The upload could not be read.");
        }
        const file = body.get("file");
        const title = body.get("title");
        if (
          !(file instanceof File) ||
          typeof title !== "string" ||
          !title.trim()
        )
          return fail(
            422,
            "invalid_upload",
            "Choose a PDF and provide its title.",
          );
        if (file.size > 10 * 1024 * 1024)
          return fail(
            413,
            "payload_too_large",
            "PDF files must be 10 MiB or smaller.",
          );
        if (
          !file.name.toLowerCase().endsWith(".pdf") ||
          !["application/pdf", "application/x-pdf"].includes(file.type)
        )
          return fail(
            415,
            "unsupported_media_type",
            "Only PDF files are supported.",
          );
        const synthetic = body.get("synthetic");
        if (synthetic !== "true" && synthetic !== "false")
          return fail(
            422,
            "invalid_upload",
            "Specify whether this document is synthetic.",
          );
        const sanitized = new FormData();
        sanitized.set("file", file);
        sanitized.set("title", title);
        sanitized.set("synthetic", synthetic);
        const publishedAt = body.get("published_at");
        if (publishedAt !== null && publishedAt !== "") {
          if (
            typeof publishedAt !== "string" ||
            !/^\d{4}-\d{2}-\d{2}$/.test(publishedAt)
          )
            return fail(
              422,
              "invalid_upload",
              "Enter the publication date as YYYY-MM-DD.",
            );
          sanitized.set("published_at", publishedAt);
        }
        const scope = body.get("scope");
        if (scope !== null) {
          if (scope !== "approach" && scope !== "program")
            return fail(
              422,
              "invalid_upload",
              "Select approach or program evidence.",
            );
          sanitized.set("scope", scope);
        }
        body = sanitized;
      } else {
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
        body = new TextDecoder().decode(
          await readBoundedBody(request, 64 * 1024, controller.signal),
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
    }
    const upstream = await (options.fetcher ?? fetch)(
      `${base.href.replace(/\/$/, "")}/${path}`,
      {
        method: request.method,
        headers: {
          Accept: "application/json",
          ...(options.apiSharedSecret
            ? { "X-API-Key": options.apiSharedSecret }
            : {}),
          ...(body === undefined || body instanceof FormData
            ? {}
            : { "Content-Type": "application/json" }),
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
  } catch (error) {
    if (error instanceof RangeError)
      return fail(413, "payload_too_large", "The request is too large.");
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
