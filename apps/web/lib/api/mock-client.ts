import { ApiError, abortableDelay } from "./errors.ts";
import { getPreviewReport } from "../preview.ts";
import type { CaseInput, Report } from "../types";
import type { ApiClient, MockScenario, Run, RunStage } from "./types";

type StorageLike = Pick<Storage, "getItem" | "setItem">;
type MockCase = {
  id: string;
  input: CaseInput;
  scenario: MockScenario;
  next_version: number;
};
type MockRun = {
  id: string;
  case_id: string;
  started_at: number;
  scenario: MockScenario;
  network_fault_used: boolean;
  version: number;
};
const PREFIX = "vic-r1-mock-api:contracts-v1:";
const STAGES: RunStage[] = [
  "validate",
  "retrieve",
  "analyze",
  "audit",
  "synthesize",
  "finalize",
];

export function createMockApiClient(
  options: {
    scenario?: MockScenario;
    storage?: () => StorageLike;
    now?: () => number;
    newId?: () => string;
    latencyMs?: number;
  } = {},
): ApiClient<Report> {
  const storage = options.storage ?? (() => window.sessionStorage);
  const now = options.now ?? Date.now;
  const newId = options.newId ?? (() => crypto.randomUUID());
  async function delay(signal?: AbortSignal) {
    await abortableDelay(options.latencyMs ?? 80, signal);
  }
  function read<T>(kind: string, id: string): T {
    let text: string | null;
    try {
      text = storage().getItem(`${PREFIX}${kind}:${id}`);
    } catch {
      throw new ApiError(
        "STORAGE_UNAVAILABLE",
        "Mock storage is unavailable in this tab.",
      );
    }
    if (!text)
      throw new ApiError(
        "NOT_FOUND",
        "This mock case, run, or report is not in this browser tab.",
        404,
      );
    try {
      return JSON.parse(text) as T;
    } catch {
      throw new ApiError(
        "INVALID_RESPONSE",
        "The saved mock data could not be read.",
      );
    }
  }
  function save(kind: string, id: string, data: unknown) {
    try {
      storage().setItem(`${PREFIX}${kind}:${id}`, JSON.stringify(data));
    } catch {
      throw new ApiError(
        "STORAGE_UNAVAILABLE",
        "The mock request could not be saved in this browser tab.",
      );
    }
  }
  function status(record: MockRun): Run {
    const elapsed = Math.max(0, now() - record.started_at);
    const done = elapsed >= 2700 && record.scenario !== "timeout";
    const failed = done && record.scenario === "failed";
    return {
      id: record.id,
      case_id: record.case_id,
      status: failed
        ? "failed"
        : done
          ? "completed"
          : elapsed < 300
            ? "queued"
            : "running",
      stage: STAGES[Math.min(STAGES.length - 1, Math.floor(elapsed / 450))],
      report_version: done && !failed ? record.version : null,
      warnings: [
        "Mock API workflow. No Python service or model call is running.",
      ],
      error: failed
        ? {
            code: "MOCK_RUN_FAILED",
            message: "The selected mock scenario ends in a failed run.",
            retryable: false,
          }
        : null,
    };
  }
  return {
    async createCase(input, requestOptions) {
      await delay(requestOptions?.signal);
      if (options.scenario === "validation") {
        throw new ApiError(
          "VALIDATION_ERROR",
          "Simulated API validation: check the highlighted field.",
          422,
          false,
          {
            mechanism:
              "The mock API rejected this target. Choose another mock scenario to continue.",
          },
        );
      }
      if (
        !input.indication.trim() ||
        !input.mechanism.trim() ||
        (input.scope === "program" && input.program_data.trim().length < 40)
      ) {
        throw new ApiError(
          "VALIDATION_ERROR",
          "Indication, mechanism, and any required programme data are missing.",
          422,
        );
      }
      const id = `mock-case-${newId()}`;
      save("case", id, {
        id,
        input,
        scenario: options.scenario ?? "complete",
        next_version: 1,
      } satisfies MockCase);
      return { case_id: id };
    },
    async startRun(caseId, requestOptions) {
      await delay(requestOptions?.signal);
      const record = read<MockCase>("case", caseId);
      const id = `mock-run-${newId()}`;
      save("case", caseId, {
        ...record,
        next_version: record.next_version + 1,
      });
      save("run", id, {
        id,
        case_id: caseId,
        started_at: now(),
        scenario: record.scenario,
        network_fault_used: false,
        version: record.next_version,
      } satisfies MockRun);
      return { run_id: id };
    },
    async getRun(runId, requestOptions) {
      await delay(requestOptions?.signal);
      const record = read<MockRun>("run", runId);
      if (record.scenario === "not-found")
        throw new ApiError(
          "NOT_FOUND",
          "The selected mock scenario returns a missing run.",
          404,
        );
      if (record.scenario === "invalid-response")
        throw new ApiError(
          "INVALID_RESPONSE",
          "The selected mock scenario returns an invalid run response.",
        );
      if (record.scenario === "network" && !record.network_fault_used) {
        save("run", record.id, { ...record, network_fault_used: true });
        throw new ApiError(
          "NETWORK_ERROR",
          "Simulated connection interruption. You can check the same run again.",
          null,
          true,
        );
      }
      return status(record);
    },
    async getReport(caseId, requestedVersion, requestOptions) {
      await delay(requestOptions?.signal);
      const record = read<MockCase>("case", caseId);
      // Reports are saved on completion rather than regenerated on each GET.
      const report = read<{ run_id: string; content: Report }>(
        "report",
        `${caseId}:${requestedVersion}`,
      );
      return {
        case_id: record.id,
        run_id: report.run_id,
        version: requestedVersion,
        content: report.content,
      };
    },
  };
}

/** Wrap the mock GET boundary to persist a completed snapshot once. */
export function createPersistedMockClient(
  options: Parameters<typeof createMockApiClient>[0] = {},
): ApiClient<Report> {
  const client = createMockApiClient(options);
  const storage = options.storage ?? (() => window.sessionStorage);
  return {
    ...client,
    async getRun(runId, requestOptions) {
      const run = await client.getRun(runId, requestOptions);
      if (run.status === "completed") {
        try {
          const key = `${PREFIX}report:${run.case_id}:${run.report_version}`;
          if (!storage().getItem(key)) {
            const record = JSON.parse(
              storage().getItem(`${PREFIX}case:${run.case_id}`) ?? "null",
            ) as MockCase | null;
            if (!record) throw new Error("Case missing");
            storage().setItem(
              key,
              JSON.stringify({
                run_id: run.id,
                content: getPreviewReport(
                  record.scenario === "unavailable"
                    ? "unavailable"
                    : "complete",
                ),
              }),
            );
          }
        } catch {
          throw new ApiError(
            "STORAGE_UNAVAILABLE",
            "The completed mock report could not be saved.",
          );
        }
      }
      return run;
    },
  };
}
