"use client";

import { useEffect, useId, useRef } from "react";
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
  const titleId = useId();
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
      aria-labelledby={titleId}
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
          <h2 id={titleId}>Inspect the reasoning</h2>
          <p className="dialog-claim">{claim.text}</p>
          <div className="claim-tags">
            <span className={`tag status-${claim.support_status}`}>
              {claim.support_status}
            </span>
            <span className="tag">
              {claim.provenance === "ai"
                ? "AI inference"
                : claim.provenance === "user"
                  ? "User-provided statement · unverified"
                  : "Source statement"}
            </span>
            <span className="tag">{claim.scope} scope</span>
            {report.synthetic && <span className="tag">Synthetic report</span>}
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
                <div className="claim-tags">
                  <span className="tag">{evidence.scope} scope</span>
                  {source.type === "user_upload" && (
                    <span className="tag">
                      Private user upload · unverified
                    </span>
                  )}
                  {source.synthetic && (
                    <span className="tag">Synthetic source</span>
                  )}
                </div>
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
                {(evidence.limitations ?? []).map((limitation) => (
                  <p
                    className="evidence-limitation"
                    key={limitation}
                  >
                    {limitation}
                  </p>
                ))}
                {(!evidence.limitations?.length || !source.available) && (
                  <p>{source.limitation}</p>
                )}
                <small>
                  {source.synthetic ? "Fictional source" : "Source document"} ·
                  Publication date: {source.published_at ?? "unknown"} ·
                  Retrieved: {source.retrieved_at}.
                  {source.synthetic
                    ? " No external link is provided for this synthetic document."
                    : ""}
                </small>
                {!source.synthetic &&
                  source.type !== "user_upload" &&
                  source.url &&
                  /^https?:\/\//i.test(source.url) && (
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Open source
                    </a>
                  )}
                {!source.synthetic &&
                  (source.type === "user_upload" || !source.url) && (
                    <p>No public source link is available.</p>
                  )}
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
