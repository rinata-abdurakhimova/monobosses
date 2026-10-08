"use client";

import { Icon } from "@/components/Icon";
import type { Report } from "@/lib/types";
import { useState } from "react";
import { EvidenceDialog } from "@/components/EvidenceDialog";
import type { Claim } from "@/lib/types";

export function RecommendationCard({ report }: { report: Report }) {
  const [claim, setClaim] = useState<Claim | null>(null);
  const decisiveIds =
    report.sections.find((section) => section.key === "recommendation")
      ?.claim_ids ?? [];
  return (
    <section
      className="recommendation-card"
      aria-labelledby="recommendation-heading"
    >
      <div className="recommendation-top">
        <span className="eyebrow">COMMITTEE CONCLUSION</span>
        <span className="recommendation-label">
          <span />
          {report.recommendation}
        </span>
      </div>
      <h2 id="recommendation-heading">
        {report.recommendation === "Do Not Invest"
          ? "The thesis is not supported."
          : report.recommendation === "Invest"
            ? "The report supports investment."
            : "Important conditions remain."}
        <br />
        Review the evidence and conditions.
      </h2>
      <p className="recommendation-rationale">{report.rationale}</p>
      <div className="conditions">
        <span className="eyebrow">WHAT NEEDS TO BE TRUE</span>
        <ol>
          {report.conditions.map((condition, i) => (
            <li key={condition}>
              <span>{String(i + 1).padStart(2, "0")}</span>
              {condition}
            </li>
          ))}
        </ol>
      </div>
      <div className="decisive-claims">
        <span className="eyebrow">CLAIMS LINKED TO THIS DECISION</span>
        {decisiveIds.length === 0 && (
          <p>No decisive claims were linked by the report provider.</p>
        )}
        {decisiveIds.map((id) => {
          const item = report.claims.find((c) => c.id === id);
          return (
            item && (
              <button
                className="claim-button"
                type="button"
                key={id}
                onClick={() => setClaim(item)}
              >
                <span>
                  {item.text}
                  <small>
                    {item.provenance === "ai"
                      ? "AI inference"
                      : item.provenance === "user"
                        ? "User-provided · unverified"
                        : "Source statement"}{" "}
                    · {item.support_status}
                  </small>
                </span>
                <Icon
                  name="arrow"
                  size={17}
                />
              </button>
            )
          );
        })}
      </div>
      <EvidenceDialog
        claim={claim}
        report={report}
        onClose={() => setClaim(null)}
      />
    </section>
  );
}
