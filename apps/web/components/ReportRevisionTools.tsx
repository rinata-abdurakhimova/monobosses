"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { createHttpApiClient } from "@/lib/api";
import { mapApiReport } from "@/lib/contracts/report";
import { validateRevisionPair, reportVersionUrl } from "@/lib/revisions";
import { asApiError } from "@/lib/api/errors";
import { RevisionComparison } from "@/components/RevisionComparison";
import { EvidenceUpload } from "@/components/EvidenceUpload";
import type { Report } from "@/lib/types";

export function ReportRevisionTools({
  report,
  disabled,
  onRunStarted,
}: {
  report: Report;
  disabled: boolean;
  onRunStarted: (runId: string) => void;
}) {
  const client = useMemo(
    () => createHttpApiClient({ mapReport: mapApiReport }),
    [],
  );
  const [parentVersion, setParentVersion] = useState(
    Math.max(1, report.version - 1),
  );
  const [attempt, setAttempt] = useState(0);
  const [before, setBefore] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const revision = report.contract.revision;
  useEffect(() => {
    if (!revision) return;
    const controller = new AbortController();
    setBefore(null);
    setError(null);
    void client
      .getReport(report.contract.case_id, parentVersion, {
        signal: controller.signal,
      })
      .then((loaded) => {
        validateRevisionPair(loaded.content, report);
        if (!controller.signal.aborted) setBefore(loaded.content);
      })
      .catch((failure) => {
        if (!controller.signal.aborted)
          setError(
            failure instanceof Error && !("code" in failure)
              ? failure.message
              : asApiError(failure).message,
          );
      });
    return () => controller.abort();
  }, [report, revision, client, parentVersion, attempt]);
  return (
    <div className="revision-tools">
      <nav
        className="state-actions"
        aria-label="Saved report versions"
      >
        <Link
          className="button button-secondary"
          href={reportVersionUrl(report.contract.case_id, report.version)}
        >
          Open saved v{report.version}
        </Link>
        {before && (
          <Link
            className="button button-secondary"
            href={reportVersionUrl(report.contract.case_id, before.version)}
          >
            Open parent v{before.version}
          </Link>
        )}
      </nav>
      {revision && (
        <>
          <div className="panel parent-picker">
            <label htmlFor="parent-version">Parent report version</label>
            <input
              id="parent-version"
              type="number"
              min={1}
              max={report.version - 1}
              value={parentVersion}
              onChange={(event) => {
                const value = Number(event.target.value);
                if (
                  Number.isSafeInteger(value) &&
                  value >= 1 &&
                  value < report.version
                )
                  setParentVersion(value);
              }}
            />
            <p>
              The comparison must match saved parent {revision.parent_report_id}
              . A review may branch from an older version.
            </p>
            {error && <p role="alert">Comparison unavailable: {error}</p>}
            {error && (
              <button
                className="button button-secondary"
                type="button"
                onClick={() => setAttempt((value) => value + 1)}
              >
                Check parent again
              </button>
            )}
            {!before && !error && (
              <p role="status">Loading the saved parent report…</p>
            )}
          </div>
          {before && (
            <RevisionComparison
              before={before}
              after={report}
            />
          )}
        </>
      )}
      <EvidenceUpload
        report={report}
        client={client}
        disabled={disabled}
        onRunStarted={onRunStarted}
      />
    </div>
  );
}
