import { ApiError } from "./errors.ts";
import type { Run } from "./types";

export function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ApiError(
      "INVALID_RESPONSE",
      "The API returned an unexpected response.",
    );
  }
  return value as Record<string, unknown>;
}
export function identifier(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ApiError(
      "INVALID_RESPONSE",
      "The API response is missing an identifier.",
    );
  }
  return value;
}
export function version(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 1) {
    throw new ApiError(
      "INVALID_RESPONSE",
      "The API response is missing a valid report version.",
    );
  }
  return value;
}
export function decodeRun(value: unknown): Run {
  const raw = object(value);
  if (
    !["queued", "running", "completed", "failed"].includes(
      String(raw.status),
    ) ||
    (raw.stage !== null &&
      ![
        "validate",
        "retrieve",
        "analyze",
        "audit",
        "synthesize",
        "finalize",
      ].includes(String(raw.stage))) ||
    !Array.isArray(raw.warnings) ||
    raw.warnings.some((x) => typeof x !== "string")
  ) {
    throw new ApiError(
      "INVALID_RESPONSE",
      "The API returned an invalid run status.",
    );
  }
  const reportVersion =
    raw.report_version === null ? null : version(raw.report_version);
  if (raw.status === "completed" && reportVersion === null) {
    throw new ApiError(
      "INVALID_RESPONSE",
      "A completed run has no report version.",
    );
  }
  let error: Run["error"] = null;
  if (raw.error !== null) {
    const failure = object(raw.error);
    if (
      typeof failure.message !== "string" ||
      typeof failure.retryable !== "boolean"
    ) {
      throw new ApiError(
        "INVALID_RESPONSE",
        "The API returned an invalid error description.",
      );
    }
    error = {
      code: identifier(failure.code),
      message: failure.message,
      retryable: failure.retryable,
    };
  }
  if (raw.status === "failed" && !error)
    throw new ApiError(
      "INVALID_RESPONSE",
      "A failed run has no error description.",
    );
  return {
    id: identifier(raw.id),
    case_id: identifier(raw.case_id),
    status: raw.status as Run["status"],
    stage: raw.stage as Run["stage"],
    report_version: reportVersion,
    warnings: raw.warnings as string[],
    error,
  };
}
