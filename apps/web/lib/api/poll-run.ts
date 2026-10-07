import { ApiError, abortableDelay, throwIfAborted } from "./errors.ts";
import { decodeRun } from "./decode.ts";
import type { ApiClient, Run } from "./types";

/** GET-only, sequential polling. It never creates a case or starts a run. */
export async function pollRun(
  client: Pick<ApiClient, "getRun">,
  runId: string,
  options: {
    signal?: AbortSignal;
    intervalMs?: number;
    maxWaitMs?: number;
    onUpdate?: (run: Run) => void;
  } = {},
): Promise<Run> {
  const controller = new AbortController();
  const cancel = () => controller.abort(options.signal?.reason);
  options.signal?.addEventListener("abort", cancel, { once: true });
  if (options.signal?.aborted) cancel();
  const deadline = setTimeout(
    () =>
      controller.abort(
        new ApiError(
          "POLL_TIMEOUT",
          "Status checks paused after the waiting limit. The existing run was not restarted.",
          null,
          true,
        ),
      ),
    options.maxWaitMs ?? 15000,
  );
  try {
    while (true) {
      throwIfAborted(controller.signal);
      const run = decodeRun(
        await client.getRun(runId, { signal: controller.signal }),
      );
      throwIfAborted(controller.signal);
      if (run.id !== runId)
        throw new ApiError(
          "INVALID_RESPONSE",
          "The response belongs to a different run.",
        );
      options.onUpdate?.(run);
      if (run.status === "completed" || run.status === "failed") return run;
      await abortableDelay(options.intervalMs ?? 650, controller.signal);
    }
  } catch (error) {
    if (controller.signal.aborted)
      throw (
        controller.signal.reason ??
        new DOMException("Request cancelled", "AbortError")
      );
    throw error;
  } finally {
    clearTimeout(deadline);
    options.signal?.removeEventListener("abort", cancel);
  }
}
