"use client";

import { useState } from "react";
import { EvidenceDialog } from "@/components/EvidenceDialog";
import { validateRevisionPair } from "@/lib/revisions";
import type { Claim, Report } from "@/lib/types";

export function RevisionComparison({
  before,
  after,
}: {
  before: Report;
  after: Report;
}) {
  const [selection, setSelection] = useState<{
    claim: Claim;
    report: Report;
  } | null>(null);
  try {
    validateRevisionPair(before, after);
  } catch {
    return (
      <section
        className="panel revision-panel"
        role="alert"
      >
        <h2>Comparison unavailable</h2>
        <p>The revision metadata does not match these saved reports.</p>
      </section>
    );
  }
  const revision = after.contract.revision!;
  return (
    <section
      className="panel revision-panel"
      id="revision-comparison"
    >
      <span className="eyebrow">
        BEFORE & AFTER{after.synthetic ? " · SYNTHETIC EXAMPLE" : ""}
      </span>
      <h2>
        {before.recommendation === after.recommendation
          ? "Recommendation unchanged"
          : "The recommendation changed"}
      </h2>
      <div className="revision-grid">
        {[before, after].map((report) => (
          <article key={report.id}>
            <span className="tiny-tag">Version {report.version}</span>
            <h3>{report.recommendation}</h3>
            <p>{report.rationale}</p>
          </article>
        ))}
      </div>
      <p>{revision.explanation}</p>
      <h3>Changed claims</h3>
      {revision.changed_claims.length === 0 && (
        <p>No changed claims were reported by the backend.</p>
      )}
      {revision.changed_claims.map((change) => (
        <div
          className="revision-grid claim-change"
          key={change.claim_id}
        >
          {[before, after].map((report) => {
            const claim = report.claims.find((c) => c.id === change.claim_id);
            return (
              <article key={report.id}>
                <small>
                  Version {report.version} · {change.claim_id}
                </small>
                {claim ? (
                  <>
                    <p>{claim.text}</p>
                    <span className={`tag status-${claim.support_status}`}>
                      {claim.support_status}
                    </span>
                    <button
                      className="button button-text"
                      type="button"
                      onClick={() => setSelection({ claim, report })}
                    >
                      Inspect evidence in v{report.version}
                    </button>
                  </>
                ) : (
                  <p>Claim absent in this version.</p>
                )}
              </article>
            );
          })}
        </div>
      ))}
      <h3>New evidence</h3>
      {revision.new_evidence_ids.length === 0 ? (
        <p>No new evidence was reported.</p>
      ) : (
        revision.new_evidence_ids.map((id) => {
          const evidence = after.evidence.find((e) => e.id === id)!;
          const source = after.sources.find(
            (s) => s.id === evidence.source_id,
          )!;
          return (
            <article
              className="excerpt-card"
              key={id}
            >
              <strong>{source.title}</strong>
              <span className="source-locator">
                {evidence.locator} · {id}
              </span>
              <blockquote>{evidence.excerpt}</blockquote>
              {(evidence.limitations ?? []).map((x) => (
                <p key={x}>{x}</p>
              ))}
            </article>
          );
        })
      )}
      <EvidenceDialog
        claim={selection?.claim ?? null}
        report={selection?.report ?? after}
        onClose={() => setSelection(null)}
      />
    </section>
  );
}
