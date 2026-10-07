"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/Icon";
import { RunProgress } from "@/components/RunProgress";
import { ReportView } from "@/components/ReportView";
import {
  getPreviewReport,
  readPreviewCase,
  PREVIEW_STEPS,
  PREVIEW_STEP_MS,
  type PreviewCase,
} from "@/lib/preview";

type View = "loading" | "running" | "ready" | "failed" | "missing";
export function CasePreview({ caseId }: { caseId: string }) {
  const [view, setView] = useState<View>("loading");
  const [record, setRecord] = useState<PreviewCase | null>(null);
  const [step, setStep] = useState(0);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const value = caseId === "sample" ? null : readPreviewCase(caseId);
    setRecord(value);
    setStep(0);
    if (caseId === "sample") {
      setView("ready");
      return;
    }
    if (!value) {
      setView("missing");
      return;
    }
    setView("running");
    const timers = PREVIEW_STEPS.slice(1).map((_, i) =>
      window.setTimeout(() => setStep(i + 1), (i + 1) * PREVIEW_STEP_MS),
    );
    timers.push(
      window.setTimeout(
        () => setView(value.mode === "failed" ? "failed" : "ready"),
        PREVIEW_STEPS.length * PREVIEW_STEP_MS,
      ),
    );
    return () => timers.forEach(window.clearTimeout);
  }, [caseId, attempt]);
  if (view === "ready")
    return (
      <ReportView
        report={getPreviewReport(record?.mode ?? "complete")}
        submitted={record}
      />
    );
  if (view === "loading")
    return (
      <div className="page-container">
        <div
          className="loading-placeholder"
          role="status"
        >
          Opening preview…
        </div>
      </div>
    );
  if (view === "running")
    return (
      <div className="page-container">
        <Link
          href="/"
          className="back-link"
        >
          ← Back to input
        </Link>
        <RunProgress step={step} />
      </div>
    );
  return (
    <div className="page-container">
      <section className="panel state-panel">
        <span className="state-icon">
          <Icon
            name={view === "failed" ? "warning" : "file"}
            size={30}
          />
        </span>
        <span className="eyebrow">
          {view === "failed" ? "SIMULATED FAILURE" : "NO LOCAL PREVIEW FOUND"}
        </span>
        <h1>
          {view === "failed"
            ? "The sample run could not finish."
            : "This preview is not in this browser tab."}
        </h1>
        <p>
          {view === "failed"
            ? "This is the failed-run state selected in the form. No analysis or model call failed. Retry repeats this selected scenario; the completed example remains available."
            : "Local previews use session storage. This link may belong to another tab or an earlier browser session. Start a new preview or open the fictional example."}
        </p>
        <div className="state-actions">
          {view === "failed" && (
            <button
              className="button button-secondary"
              onClick={() => setAttempt((x) => x + 1)}
            >
              Retry failed preview
            </button>
          )}
          <Link
            className="button button-primary"
            href="/cases/sample"
          >
            Open completed example
            <Icon
              name="arrow"
              size={17}
            />
          </Link>
          <Link
            href="/"
            className="button button-text"
          >
            New assessment
          </Link>
        </div>
      </section>
    </div>
  );
}
