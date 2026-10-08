"use client";

import { useEffect, useRef, useState } from "react";
import type { ApiClient, EvidenceClient } from "@/lib/api/types";
import type { EvidenceCreated } from "@/lib/contracts/generated";
import type { Report } from "@/lib/types";
import { asApiError } from "@/lib/api/errors";

export function EvidenceUpload({
  report,
  client,
  onRunStarted,
  disabled = false,
}: {
  report: Report;
  client: ApiClient<Report> & EvidenceClient;
  onRunStarted: (runId: string) => void;
  disabled?: boolean;
}) {
  const [kind, setKind] = useState("text");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [synthetic, setSynthetic] = useState(false);
  const [reviewMode, setReviewMode] = useState<"evidence_only" | "live">(
    report.synthetic ? "evidence_only" : "live",
  );
  const [imported, setImported] = useState<EvidenceCreated | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function act(rerun: boolean) {
    if (lock.current || disabled) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    const active = new AbortController();
    controller.current = active;
    try {
      if (rerun) {
        const run = await client.startRun(report.contract.case_id, {
          signal: active.signal,
          parentReportId: report.id,
          mode: reviewMode,
        });
        if (!active.signal.aborted) onRunStarted(run.run_id);
      } else {
        setImported(null);
        const result =
          kind === "text"
            ? await client.addEvidence(
                report.contract.case_id,
                { title: title.trim(), text, synthetic },
                { signal: active.signal },
              )
            : await client.uploadDocument(
                report.contract.case_id,
                file!,
                title.trim(),
                synthetic,
                { signal: active.signal },
              );
        if (!active.signal.aborted) setImported(result);
      }
    } catch (failure) {
      if (!active.signal.aborted) {
        const issue = asApiError(failure);
        setError(`${issue.status ?? issue.code}: ${issue.message}`);
      }
    } finally {
      lock.current = false;
      if (!active.signal.aborted) setBusy(false);
    }
  }
  return (
    <section className="panel evidence-upload">
      <span className="eyebrow">ADD EVIDENCE</span>
      <h2>Bring another document into view.</h2>
      <p>
        Import a document, then explicitly review the conclusion. Your saved
        report remains available. Private uploads do not need a public URL.
      </p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void act(false);
        }}
      >
        <fieldset disabled={busy || disabled}>
          <label htmlFor="evidence-kind">Document format</label>
          <select
            id="evidence-kind"
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              setImported(null);
              setError(null);
            }}
          >
            <option value="text">Text</option>
            <option value="pdf">PDF</option>
          </select>
          <label htmlFor="evidence-title">Document title</label>
          <input
            id="evidence-title"
            required
            maxLength={500}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          {kind === "text" ? (
            <>
              <label htmlFor="evidence-text">Document text</label>
              <textarea
                id="evidence-text"
                required
                maxLength={50000}
                rows={6}
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
            </>
          ) : (
            <>
              <label htmlFor="evidence-file">PDF · up to 10 MiB</label>
              <input
                id="evidence-file"
                type="file"
                accept="application/pdf,.pdf"
                required
                onChange={(event) => {
                  const next = event.target.files?.[0] ?? null;
                  setFile(next);
                  setImported(null);
                  setError(
                    next && next.size > 10 * 1024 * 1024
                      ? "Choose a PDF no larger than 10 MiB."
                      : null,
                  );
                  event.target.setCustomValidity(
                    next && next.size > 10 * 1024 * 1024
                      ? "Choose a PDF no larger than 10 MiB."
                      : "",
                  );
                }}
              />
              <p>
                PDFs must contain readable text. Parsing and size errors appear
                here.
              </p>
            </>
          )}
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={synthetic}
              onChange={(event) => setSynthetic(event.target.checked)}
            />{" "}
            This document is synthetic
          </label>
          <button
            className="button button-secondary"
            type="submit"
          >
            {busy ? "Request in progress…" : "Import evidence"}
          </button>
        </fieldset>
      </form>
      {error && (
        <p
          role="alert"
          className="evidence-limitation"
        >
          {error} No request was automatically retried.
        </p>
      )}
      {imported && (
        <div role="status">
          <p>
            Imported source: <strong>{imported.source_id}</strong>
          </p>
          <p>Evidence: {imported.evidence_ids.join(", ")}</p>
          <p>
            The saved conclusion has not changed. Run a review to include the
            imported evidence.
          </p>
          <label htmlFor="review-mode">Evidence for the review</label>
          <select
            id="review-mode"
            value={reviewMode}
            disabled={busy || disabled}
            onChange={(event) =>
              setReviewMode(event.target.value as "evidence_only" | "live")
            }
          >
            <option value="evidence_only">Use supplied evidence only</option>
            <option value="live">Include live source retrieval</option>
          </select>
          <button
            type="button"
            className="button button-primary"
            disabled={busy || disabled}
            onClick={() => void act(true)}
          >
            Review conclusion from v{report.version}
          </button>
        </div>
      )}
    </section>
  );
}
