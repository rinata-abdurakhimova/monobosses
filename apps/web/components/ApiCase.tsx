"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { createMockApiClient, pollRun, ApiError } from "@/lib/api";
import { asApiError } from "@/lib/api/errors";
import type { LoadedReport, Run, RunStage } from "@/lib/api/types";
import type { Report } from "@/lib/types";
import { ReportView } from "@/components/ReportView";
import { RunProgress } from "@/components/RunProgress";

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
}: {
  caseId: string;
  runId: string | null;
}) {
  const client = useMemo(() => createMockApiClient(), []);
  const [attempt, setAttempt] = useState(0);
  const [run, setRun] = useState<Run | null>(null);
  const [report, setReport] = useState<LoadedReport<Report> | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    setReport(null);
    setRun(null);
    if (!runId) {
      setError(
        new ApiError(
          "MISSING_RUN_ID",
          "This mock workflow link has no saved run identifier. Start a new mock workflow from the form.",
        ),
      );
      return () => controller.abort();
    }
    async function loadExistingRun() {
      try {
        const completed = await pollRun(client, runId!, {
          signal: controller.signal,
          maxWaitMs: 8000,
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
      }
    }
    void loadExistingRun();
    return () => controller.abort();
  }, [caseId, runId, client, attempt]);

  const notice = (
    <div
      className="mock-api-notice"
      role="status"
    >
      <strong>Mock API workflow · synthetic data only</strong>
      <p>
        Requests are simulated in this browser tab. No Python service or model
        is connected. Submitted input does not change the fixed fictional
        report.
      </p>
    </div>
  );

  if (report) {
    return (
      <>
        <div className="page-container mock-notice-container">
          {notice}
          <p className="mock-version">
            Saved mock report · version {report.version}
          </p>
        </div>
        <ReportView
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
            MOCK WORKFLOW · {error.status ?? error.code}
          </span>
          <h1>
            {error.status === 404
              ? "This mock run could not be found."
              : error.code === "POLL_TIMEOUT"
                ? "Status checks are paused."
                : error.code === "MOCK_RUN_FAILED"
                  ? "The mock run failed."
                  : "The mock request could not finish."}
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
        step={run ? stages.indexOf(run.stage) : 0}
        mode="mock-api"
      />
    </div>
  );
}
