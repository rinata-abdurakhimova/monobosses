"use client";

import { analysisStatus, visibleFindings } from "@/lib/analysis-status";

import { useState } from "react";
import { EvidenceDialog } from "@/components/EvidenceDialog";
import { AnalysisDetails } from "@/components/AnalysisDetails";
import type { Claim, Report, RoleResult } from "@/lib/types";

export function RoleCard({
  role,
  report,
}: {
  role: RoleResult;
  report: Report;
}) {
  const [claim, setClaim] = useState<Claim | null>(null);
  return (
    <article className="role-card">
      <div className="role-heading">
        <span className="role-initials">{role.initials}</span>
        <h3>{role.name}</h3>
      </div>
      <span className="role-position">{analysisStatus(role).label}</span>
      {analysisStatus(role).explanation && (
        <p>{analysisStatus(role).explanation}</p>
      )}
      <p>{role.summary}</p>
      <div className="role-unknown">
        <span>Key unknown</span>
        <strong>{role.unknowns[0] ?? role.unknown}</strong>
        {role.unknowns.length > 1 && (
          <small>{role.unknowns.length - 1} more in reasoning details</small>
        )}
      </div>
      {role.claims.length > 0 && (
        <div>
          <h4>Findings from this analysis</h4>
          <ul>
            {visibleFindings(role.claims).map((item) => (
              <li key={item.id}>
                {item.text} <small>({item.support_status})</small>
              </li>
            ))}
          </ul>
        </div>
      )}
      <details>
        <summary>All claims, reasoning and decision conditions</summary>
        <div className="claims-list">
          {role.claims.map((item) => (
            <button
              key={item.id}
              type="button"
              className="claim-button"
              onClick={() => setClaim(item)}
            >
              <span className={`claim-dot status-${item.support_status}`} />
              <span>
                {item.text}
                <small>
                  {item.provenance} · {item.support_status} · Inspect evidence
                </small>
              </span>
            </button>
          ))}
        </div>
        {role.risks.map((risk) => (
          <div
            className="risk-item"
            key={risk.id}
          >
            <strong>
              {risk.priority}: {risk.description}
            </strong>
            <p>{risk.impact}</p>
            <small>Next check: {risk.next_check}</small>
            {(risk.claim_ids ?? []).map((id) => {
              const linked = report.claims.find((item) => item.id === id);
              return linked ? (
                <button
                  className="claim-button"
                  type="button"
                  key={id}
                  onClick={() => setClaim(linked)}
                >
                  Inspect supporting claim: {linked.text}
                </button>
              ) : null;
            })}
          </div>
        ))}
        {role.change_conditions.length > 0 && (
          <div className="role-unknown">
            <span>What would change this position</span>
            <ul>
              {role.change_conditions.map((condition, index) => (
                <li key={index}>{condition}</li>
              ))}
            </ul>
          </div>
        )}
        {role.unknowns.length > 0 && (
          <div className="role-unknown">
            <span>Open unknowns</span>
            <ul>
              {role.unknowns.map((unknown, index) => (
                <li key={index}>{unknown}</li>
              ))}
            </ul>
          </div>
        )}
      </details>
      {role.section_content.map((section, index) => (
        <details key={`${section.key}-${index}`}>
          <summary>
            {section.key.replaceAll("_", " ")} — analysis details
          </summary>
          <div className="section-content">
            <p>{section.summary}</p>
            {(section.limitations ?? []).map((item, i) => (
              <p key={i}>{item}</p>
            ))}
            {section.structured_data && (
              <AnalysisDetails
                value={section.structured_data}
                report={report}
                onClaim={setClaim}
              />
            )}
          </div>
        </details>
      ))}
      <EvidenceDialog
        claim={claim}
        report={report}
        onClose={() => setClaim(null)}
      />
    </article>
  );
}
