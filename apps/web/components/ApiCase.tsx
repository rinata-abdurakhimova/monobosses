"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ReportRevisionTools } from "@/components/ReportRevisionTools";
import {
  createMockApiClient,
  createHttpApiClient,
  pollRun,
  ApiError,
} from "@/lib/api";
import { asApiError } from "@/lib/api/errors";
import type { LoadedReport, Run, RunStage } from "@/lib/api/types";
import type { Report } from "@/lib/types";
import { ReportView } from "@/components/ReportView";
import { RunProgress } from "@/components/RunProgress";

import { mapApiReport } from "@/lib/contracts/report";

const stages: RunStage[] = [
  "validate",
  "retrieve",
  "analyze",
  "audit",
  "synthesize",
  "finalize",
];

export function ApiCase({
  caseId,
  runId,
  flow = "mock-api",
  requestedVersion = null,
  previousVersion = null,
}: {
  caseId: string;
  runId: string | null;
  flow?: "mock-api" | "api";
  requestedVersion?: number | null;
  previousVersion?: number | null;
}) {
  const router = useRouter();
  const client = useMemo(
    () =>
      flow === "api"
        ? createHttpApiClient({ mapReport: mapApiReport })
        : createMockApiClient(),
    [flow],
  );
  const [attempt, setAttempt] = useState(0);
  const [run, setRun] = useState<Run | null>(null);
  const [report, setReport] = useState<LoadedReport<Report> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    setPending(true);
    setReport((previous) =>
      previous?.case_id === caseId && !requestedVersion ? previous : null,
    );
    setRun(null);
    if (!runId && !requestedVersion) {
      setPending(false);
      setError(
        new ApiError(
          "MISSING_RUN_ID",
          "This link has no saved run identifier. Start an assessment from the form.",
        ),
      );
      return () => controller.abort();
    }
    async function loadExistingRun() {
      try {
        if (requestedVersion) {
          const loaded = await client.getReport(caseId, requestedVersion, {
            signal: controller.signal,
          });
          if (!controller.signal.aborted) setReport(loaded);
          return;
        }
        if (previousVersion) {
          try {
            const previous = await client.getReport(caseId, previousVersion, {
              signal: controller.signal,
            });
            if (!controller.signal.aborted) setReport(previous);
          } catch {
            /* The new run can still be checked if its prior snapshot is unavailable. */
          }
        }
        const completed = await pollRun(client, runId!, {
          signal: controller.signal,
          maxWaitMs: flow === "api" ? 600000 : 8000,
          intervalMs: flow === "api" ? 1500 : 650,
          onUpdate(next) {
            if (next.case_id !== caseId)
              throw new ApiError(
                "INVALID_RESPONSE",
                "This run belongs to a different case.",
              );
            setRun(next);
          },
        });
        if (completed.status === "failed") {
          throw new ApiError(
            completed.error?.code ?? "RUN_FAILED",
            completed.error?.message ?? "The run failed.",
            null,
            false,
          );
        }
        const loaded = await client.getReport(
          caseId,
          completed.report_version!,
          { signal: controller.signal },
        );
        if (loaded.run_id !== runId)
          throw new ApiError(
            "INVALID_RESPONSE",
            "The report belongs to a different run.",
          );
        if (!controller.signal.aborted) setReport(loaded);
      } catch (failure) {
        if (!controller.signal.aborted) setError(asApiError(failure));
      } finally {
        if (!controller.signal.aborted) setPending(false);
      }
    }
    void loadExistingRun();
    return () => controller.abort();
  }, [caseId, runId, client, attempt, flow, requestedVersion, previousVersion]);

  const notice = (
    <div
      className="mock-api-notice"
      role="status"
    >
      <strong>
        {flow === "api"
          ? "Python API assessment"
          : "Mock API workflow · synthetic data only"}
      </strong>
      <p>
        {flow === "api"
          ? "This assessment is stored by the Python service. Synthetic reports are examples and do not assess your input. Refreshing reads the same run."
          : "Requests are simulated in this browser tab. No Python service or model is connected. Submitted input does not change the fixed fictional report."}
      </p>
    </div>
  );

  if (report) {
    return (
      <>
        <div className="page-container mock-notice-container">
          {notice}
          {run?.warnings.map((warning, index) => (
            <p
              role="status"
              key={index}
            >
              {warning}
            </p>
          ))}
          <p className="mock-version">
            Saved report · version {report.version}
          </p>
          {pending && (
            <p role="status">
              Checking the review run. Saved v{report.version} remains available
              below.
            </p>
          )}
          {error && (
            <div role="alert">
              <p>
                Review could not finish: {error.message}. Saved v
                {report.version} remains available.
              </p>
              {error.retryable && (
                <button
                  className="button button-secondary"
                  type="button"
                  onClick={() => setAttempt((value) => value + 1)}
                >
                  Check existing run again
                </button>
              )}
            </div>
          )}
          {flow === "api" && (
            <ReportRevisionTools
              key={report.content.id}
              report={report.content}
              disabled={pending}
              onRunStarted={(nextRun) => {
                setPending(true);
                router.push(
                  `/cases/${encodeURIComponent(caseId)}?flow=api&run=${encodeURIComponent(nextRun)}&previous=${report.version}`,
                  { scroll: false },
                );
              }}
            />
          )}
        </div>
        <ReportView
          key={report.content.id}
          report={report.content}
          submitted={null}
        />
      </>
    );
  }
  if (error) {
    return (
      <div className="page-container">
        {notice}
        <section
          className="panel state-panel"
          role="alert"
        >
          <span className="eyebrow">
            {flow === "api" ? "API ASSESSMENT" : "MOCK WORKFLOW"} ·{" "}
            {error.status ?? error.code}
          </span>
          <h1>
            {error.status === 404
              ? "This run could not be found."
              : error.code === "POLL_TIMEOUT"
                ? "Status checks are paused."
                : run?.status === "failed"
                  ? "The assessment failed."
                  : "The request could not finish."}
          </h1>
          <p>{error.message}</p>
          <p>
            Refreshing or resuming checks the identifiers in this URL; it does
            not start another run.
          </p>
          <div className="state-actions">
            {error.retryable && runId && (
              <button
                className="button button-primary"
                type="button"
                onClick={() => setAttempt((value) => value + 1)}
              >
                Check existing run again
              </button>
            )}
            <Link
              className="button button-secondary"
              href="/"
            >
              Back to assessment
            </Link>
            <Link
              className="button button-text"
              href="/cases/sample"
            >
              Open fixture preview
            </Link>
          </div>
        </section>
      </div>
    );
  }
  return (
    <div className="page-container">
      {notice}
      <RunProgress
        step={run?.stage ? stages.indexOf(run.stage) : 0}
        mode={flow}
      />
    </div>
  );
}
