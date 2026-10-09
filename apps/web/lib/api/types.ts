import type { CaseInput } from "../types";
import type * as Contract from "../contracts/generated";

export type RunStatus = Contract.RunStatus;
export type RunStage = Contract.RunStage;
export type RequestOptions = { signal?: AbortSignal };
export type UploadOptions = RequestOptions & {
  publishedAt?: string;
  scope?: Contract.Scope;
};
export type StartRunOptions = RequestOptions & {
  parentReportId?: string;
  mode?: Contract.RunMode;
};
export interface EvidenceClient {
  addEvidence(
    caseId: string,
    input: Contract.EvidenceCreate,
    options?: RequestOptions,
  ): Promise<Contract.EvidenceCreated>;
  uploadDocument(
    caseId: string,
    file: File,
    title: string,
    synthetic: boolean,
    options?: UploadOptions,
  ): Promise<Contract.EvidenceCreated>;
}
export type CreatedCase = { case_id: string };
export type StartedRun = { run_id: string };
export type Run = {
  id: string;
  case_id: string;
  status: RunStatus;
  stage: RunStage | null;
  report_version: number | null;
  warnings: string[];
  error: { code: string; message: string; retryable: boolean } | null;
};
/** Client-level envelope: content is mapped at the transport boundary. */
export type LoadedReport<T> = {
  case_id: string;
  run_id: string;
  version: number;
  content: T;
};
export interface ApiClient<T = unknown> {
  createCase(input: CaseInput, options?: RequestOptions): Promise<CreatedCase>;
  startRun(caseId: string, options?: StartRunOptions): Promise<StartedRun>;
  getRun(runId: string, options?: RequestOptions): Promise<Run>;
  getReport(
    caseId: string,
    version: number,
    options?: RequestOptions,
  ): Promise<LoadedReport<T>>;
}
export type MockScenario =
  | "complete"
  | "failed"
  | "unavailable"
  | "validation"
  | "network"
  | "not-found"
  | "invalid-response"
  | "timeout";
export const MOCK_SCENARIOS: { value: MockScenario; label: string }[] = [
  { value: "complete", label: "Completed mock run" },
  { value: "failed", label: "Failed mock run" },
  { value: "unavailable", label: "Completed with an unavailable source" },
  { value: "validation", label: "Simulated API validation error (422)" },
  { value: "network", label: "Connection interrupted; resume the same run" },
  { value: "not-found", label: "Run not found (404)" },
  { value: "invalid-response", label: "Invalid API response" },
  { value: "timeout", label: "Polling deadline reached" },
];
