export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly retryable: boolean;
  readonly fieldErrors: Record<string, string>;
  constructor(
    code: string,
    message: string,
    status: number | null = null,
    retryable = false,
    fieldErrors: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.retryable = retryable;
    this.fieldErrors = fieldErrors;
  }
}
export function asApiError(error: unknown): ApiError {
  return error instanceof ApiError
    ? error
    : new ApiError("UNEXPECTED_ERROR", "The request could not be completed.");
}
export function throwIfAborted(signal?: AbortSignal): void {
  if (signal?.aborted) {
    throw signal.reason ?? new DOMException("Request cancelled", "AbortError");
  }
}
export function abortableDelay(
  ms: number,
  signal?: AbortSignal,
): Promise<void> {
  throwIfAborted(signal);
  return new Promise((resolve, reject) => {
    const finish = () => {
      signal?.removeEventListener("abort", cancel);
      resolve();
    };
    const timer = setTimeout(finish, ms);
    const cancel = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", cancel);
      reject(
        signal?.reason ?? new DOMException("Request cancelled", "AbortError"),
      );
    };
    signal?.addEventListener("abort", cancel, { once: true });
  });
}
