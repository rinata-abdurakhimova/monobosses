import { ApiError, throwIfAborted } from "./errors.ts";
import { decodeRun, identifier, object, version } from "./decode.ts";
import type { ApiClient, RequestOptions } from "./types";

/** Same-origin proxy client.
 * mapReport converts the authoritative wire report into a UI model when supplied.
 */
type HttpOptions = {
  basePath?: string;
  fetcher?: typeof fetch;
  requestTimeoutMs?: number;
};

export function createHttpApiClient<T>(
  options: HttpOptions & {
    mapReport: (wire: unknown) => T;
  },
): ApiClient<T>;
export function createHttpApiClient(options?: HttpOptions): ApiClient<unknown>;
export function createHttpApiClient(
  options: HttpOptions & { mapReport?: (wire: unknown) => unknown } = {},
): ApiClient<unknown> {
  const base = options.basePath ?? "/api/backend";
  if (!base.startsWith("/") || base.startsWith("//") || /[?#\\]/.test(base)) {
    throw new Error("Use a same-origin server proxy path, not a backend URL.");
  }
  const fetcher = options.fetcher ?? fetch;
  async function performRequest(
    path: string,
    method: "GET" | "POST",
    body: unknown,
    requestOptions?: RequestOptions,
  ): Promise<unknown> {
    throwIfAborted(requestOptions?.signal);
    let response: Response;
    try {
      response = await fetcher(`${base.replace(/\/$/, "")}${path}`, {
        method,
        signal: requestOptions?.signal,
        cache: "no-store",
        headers: {
          Accept: "application/json",
          ...(body === undefined ? {} : { "Content-Type": "application/json" }),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      throwIfAborted(requestOptions?.signal);
      throw new ApiError(
        "NETWORK_ERROR",
        "Connection interrupted. No request was automatically resubmitted.",
        null,
        true,
      );
    }
    throwIfAborted(requestOptions?.signal);
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throwIfAborted(requestOptions?.signal);
      throw new ApiError(
        "INVALID_RESPONSE",
        "The API response was not valid JSON.",
        response.status,
      );
    }
    throwIfAborted(requestOptions?.signal);
    if (!response.ok) {
      const raw = object(data);
      const fields: Record<string, string> = {};
      if (Array.isArray(raw.detail)) {
        for (const entry of raw.detail) {
          const detail = object(entry);
          if (Array.isArray(detail.loc) && typeof detail.msg === "string") {
            fields[String(detail.loc.at(-1))] = detail.msg;
          }
        }
      }
      const error =
        raw.error && typeof raw.error === "object" ? object(raw.error) : {};
      throw new ApiError(
        typeof error.code === "string" ? error.code : `HTTP_${response.status}`,
        typeof error.message === "string"
          ? error.message
          : response.status === 422
            ? "The API rejected the input. Please check the fields."
            : response.status === 404
              ? "This case, run, or report was not found."
              : "The API request failed.",
        response.status,
        typeof error.retryable === "boolean"
          ? error.retryable
          : response.status >= 500,
        fields,
      );
    }
    return data;
  }
  async function request(
    path: string,
    method: "GET" | "POST",
    body: unknown,
    requestOptions?: RequestOptions,
  ): Promise<unknown> {
    const controller = new AbortController();
    const cancel = () => controller.abort(requestOptions?.signal?.reason);
    requestOptions?.signal?.addEventListener("abort", cancel, { once: true });
    if (requestOptions?.signal?.aborted) cancel();
    const timer = setTimeout(
      () =>
        controller.abort(
          new ApiError(
            "REQUEST_TIMEOUT",
            "The request timed out. It was not automatically resubmitted.",
            null,
            true,
          ),
        ),
      options.requestTimeoutMs ?? 10000,
    );
    try {
      return await performRequest(path, method, body, {
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
      requestOptions?.signal?.removeEventListener("abort", cancel);
    }
  }
  return {
    async createCase(input, requestOptions) {
      const raw = object(
        await request("/cases", "POST", input, requestOptions),
      );
      return { case_id: identifier(raw.case_id) };
    },
    async startRun(caseId, requestOptions) {
      const raw = object(
        await request(
          `/cases/${encodeURIComponent(caseId)}/runs`,
          "POST",
          { mode: "live", parent_report_id: null },
          requestOptions,
        ),
      );
      return { run_id: identifier(raw.run_id) };
    },
    async getRun(runId, requestOptions) {
      const run = decodeRun(
        await request(
          `/runs/${encodeURIComponent(runId)}`,
          "GET",
          undefined,
          requestOptions,
        ),
      );
      if (run.id !== runId)
        throw new ApiError(
          "INVALID_RESPONSE",
          "The response belongs to a different run.",
        );
      return run;
    },
    async getReport(caseId, requestedVersion, requestOptions) {
      version(requestedVersion);
      const wire = await request(
        `/cases/${encodeURIComponent(caseId)}/reports/${requestedVersion}`,
        "GET",
        undefined,
        requestOptions,
      );
      const raw = object(wire);
      if (raw.case_id !== caseId || version(raw.version) !== requestedVersion) {
        throw new ApiError(
          "INVALID_RESPONSE",
          "The response belongs to a different case or report version.",
        );
      }
      let content: unknown;
      try {
        content = options.mapReport ? options.mapReport(wire) : wire;
      } catch {
        throw new ApiError(
          "INVALID_RESPONSE",
          "The report does not match the agreed UI mapping.",
        );
      }
      return {
        case_id: caseId,
        run_id: identifier(raw.run_id),
        version: requestedVersion,
        content,
      };
    },
  };
}
