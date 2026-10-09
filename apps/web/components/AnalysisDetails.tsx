"use client";

import type { Claim, Report } from "@/lib/types";

const metadata = new Set([
  "upstream_context",
  "input_inventory",
  "sources",
  "evidence",
  "audit",
  "claim_evidence_links",
  "evidence_source_links",
  "context_availability",
  "snapshot_id",
  "as_of_date",
  "synthetic",
  "prompt_version",
  "committee_decision",
]);

function label(key: string): string {
  return key
    .replaceAll("_", " ")
    .replace(/^./, (letter) => letter.toUpperCase());
}

/** Read the node's actual structured analysis, including financial plans and risk chains. */
export function AnalysisDetails({
  value,
  report,
  onClaim,
}: {
  value: unknown;
  report: Report;
  onClaim: (claim: Claim) => void;
}) {
  if (value === null || value === undefined) return <span>Unknown</span>;
  if (typeof value === "string") {
    const claim = report.claims.find((item) => item.id === value);
    return claim ? (
      <button
        type="button"
        className="claim-button"
        onClick={() => onClaim(claim)}
      >
        Inspect claim: {claim.text}
      </button>
    ) : (
      <span>{value}</span>
    );
  }
  if (typeof value === "number")
    return <span>{value.toLocaleString("en-US")}</span>;
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span>None reported</span>;
    return (
      <ul>
        {value.map((item, index) => (
          <li key={index}>
            <AnalysisDetails
              value={item}
              report={report}
              onClaim={onClaim}
            />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object")
    return (
      <dl>
        {Object.entries(value)
          .filter(([key]) => !metadata.has(key))
          .map(([key, item]) => (
            <div
              className="risk-item"
              key={key}
            >
              <dt>
                <strong>{label(key)}</strong>
              </dt>
              <dd>
                <AnalysisDetails
                  value={item}
                  report={report}
                  onClaim={onClaim}
                />
              </dd>
            </div>
          ))}
      </dl>
    );
  return null;
}
