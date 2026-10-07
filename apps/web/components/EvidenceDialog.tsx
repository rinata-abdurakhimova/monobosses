"use client";

import { useEffect, useRef } from "react";
import { Icon } from "@/components/Icon";
import type { Claim, Report } from "@/lib/types";

export function EvidenceDialog({
  claim,
  report,
  onClose,
}: {
  claim: Claim | null;
  report: Report;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (claim && !dialog.open) dialog.showModal();
    else if (!claim && dialog.open) dialog.close();
  }, [claim]);
  return (
    <dialog
      ref={ref}
      className="evidence-dialog"
      aria-labelledby="evidence-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {claim && (
        <>
          <div className="dialog-heading">
            <span className="eyebrow">CLAIM → EVIDENCE → SOURCE</span>
            <button
              className="icon-button"
              type="button"
              aria-label="Close evidence"
              onClick={onClose}
            >
              <Icon name="close" />
            </button>
          </div>
          <h2 id="evidence-title">Inspect the reasoning</h2>
          <p className="dialog-claim">{claim.text}</p>
          <div className="claim-tags">
            <span className={`tag status-${claim.support_status}`}>
              {claim.support_status}
            </span>
            <span className="tag">
              {claim.provenance === "ai"
                ? "AI inference in fixture"
                : claim.provenance === "user"
                  ? "User-provided statement · unverified"
                  : "Source statement in fixture"}
            </span>
            <span className="tag">Synthetic</span>
          </div>
          {claim.assumptions.map((x) => (
            <p
              className="evidence-limitation"
              key={x}
            >
              {x}
            </p>
          ))}
          {claim.evidence_ids.length === 0 && (
            <p className="evidence-limitation">
              No source evidence is linked to this claim.
            </p>
          )}
          {claim.evidence_ids.map((id) => {
            const evidence = report.evidence.find((x) => x.id === id);
            const source = report.sources.find(
              (x) => x.id === evidence?.source_id,
            );
            if (!evidence || !source)
              return (
                <p
                  key={id}
                  role="status"
                >
                  Evidence unavailable for this claim.
                </p>
              );
            return (
              <article
                className="excerpt-card"
                key={id}
              >
                <div className="source-heading">
                  <Icon
                    name="file"
                    size={18}
                  />
                  <strong>{source.title}</strong>
                </div>
                <span className="source-locator">{evidence.locator}</span>
                {!source.available && (
                  <p className="source-warning">
                    <Icon
                      name="warning"
                      size={15}
                    />
                    Source unavailable · cached synthetic excerpt
                  </p>
                )}
                <blockquote>{evidence.excerpt}</blockquote>
                <p>{source.limitation}</p>
                <small>
                  Fictional source · Publication date:{" "}
                  {source.published_at ?? "unknown"} · Retrieved:{" "}
                  {source.retrieved_at}. No external link is provided for this
                  synthetic document.
                </small>
              </article>
            );
          })}
          <button
            className="button button-secondary"
            type="button"
            onClick={onClose}
          >
            Back to report
          </button>
        </>
      )}
    </dialog>
  );
}
