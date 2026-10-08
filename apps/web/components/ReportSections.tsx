"use client";

import { useState } from "react";
import { Icon } from "@/components/Icon";
import { EvidenceDialog } from "@/components/EvidenceDialog";
import type { Claim, Report } from "@/lib/types";

export function ReportSections({ report }: { report: Report }) {
  const [claim, setClaim] = useState<Claim | null>(null);
  const linkedIds = new Set(report.sections.flatMap((s) => s.claim_ids));
  const additionalClaims = report.claims.filter((c) => !linkedIds.has(c.id));
  return (
    <>
      <div className="section-list">
        {report.sections.map((section, index) => (
          <details
            className="report-section"
            id={`section-${section.key}`}
            key={section.key}
            open={index < 3 ? true : undefined}
          >
            <summary>
              <span className="section-number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3>{section.title}</h3>
              <span
                className={`section-status ${section.status === "Data needed" ? "needs-data" : ""}`}
              >
                {section.status}
              </span>
              <Icon
                name="chevron"
                size={17}
              />
            </summary>
            <div className="section-content">
              <p>{section.summary}</p>
              {section.points.length > 0 && (
                <ul className="section-points">
                  {section.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              )}
              {section.key === "key_risks" && (
                <div className="risk-list">
                  {report.risks.map((risk) => (
                    <article
                      className="risk-item"
                      key={risk.id}
                    >
                      <div>
                        <span
                          className={`risk-priority ${risk.priority === "Critical" ? "critical" : ""}`}
                        >
                          {risk.priority}
                        </span>
                        <h4>{risk.title}</h4>
                      </div>
                      <p>{risk.impact}</p>
                      <small>
                        <strong>Next check:</strong> {risk.next_check}
                      </small>
                    </article>
                  ))}
                </div>
              )}
              {section.key === "critical_unknowns" && (
                <ul className="unknown-list">
                  {report.unknowns.map((x) => (
                    <li key={x}>
                      <span className="tag status-unknown">Unknown</span>
                      {x}
                    </li>
                  ))}
                </ul>
              )}
              {section.key === "diligence_questions" && (
                <ol className="question-list">
                  {report.diligence_questions.map((q) => (
                    <li key={q.question}>
                      <h4>{q.question}</h4>
                      <p>{q.why}</p>
                      <small>
                        <strong>Evidence needed:</strong> {q.evidence_needed}
                      </small>
                      <div className="question-outcomes">
                        <p>
                          <strong>If supported</strong>
                          {q.positive}
                        </p>
                        <p>
                          <strong>If not supported</strong>
                          {q.negative}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
              {section.key === "sources" && (
                <div className="source-list">
                  {report.sources.map((source) => (
                    <article key={source.id}>
                      <Icon
                        name="file"
                        size={18}
                      />
                      <div>
                        <h4>{source.title}</h4>
                        <small>
                          {source.type} ·{" "}
                          {source.synthetic ? "Synthetic" : "Source document"} ·{" "}
                          {source.published_at ?? "Publication date unknown"}
                        </small>
                        <p>{source.limitation}</p>
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
                      </div>
                      <span
                        className={`tag ${source.available ? "" : "status-unverified"}`}
                      >
                        {source.available
                          ? source.synthetic
                            ? "Fixture available"
                            : "Evidence available"
                          : "Unavailable"}
                      </span>
                    </article>
                  ))}
                </div>
              )}
              {section.limitation && (
                <p className="section-limitation">
                  <Icon
                    name="warning"
                    size={15}
                  />
                  {section.limitation}
                </p>
              )}
              {section.claim_ids.length > 0 && (
                <div className="claims-list">
                  <span className="eyebrow">SUPPORTING CLAIMS</span>
                  {section.claim_ids.map((id) => {
                    const item = report.claims.find((x) => x.id === id);
                    return item ? (
                      <button
                        key={id}
                        className="claim-button"
                        type="button"
                        onClick={() => setClaim(item)}
                      >
                        <span
                          className={`claim-dot status-${item.support_status}`}
                        />
                        <span>
                          {item.text}
                          <small>
                            {item.support_status === "unknown"
                              ? "Unknown · not a negative finding"
                              : item.support_status === "supported"
                                ? report.synthetic
                                  ? "Supported within synthetic fixture"
                                  : "Supported"
                                : item.support_status === "mixed"
                                  ? report.synthetic
                                    ? "Mixed support within synthetic fixture"
                                    : "Mixed support"
                                  : item.support_status === "contradicted"
                                    ? report.synthetic
                                      ? "Contradicted within synthetic fixture"
                                      : "Contradicted"
                                    : item.provenance === "user"
                                      ? "Unverified user-provided statement"
                                      : "Unverified inference"}
                          </small>
                        </span>
                        <Icon
                          name="arrow"
                          size={16}
                        />
                      </button>
                    ) : null;
                  })}
                </div>
              )}
            </div>
          </details>
        ))}
      </div>
      {additionalClaims.length > 0 && (
        <section className="panel section-content">
          <h3>Additional report claims</h3>
          <p>
            Statements included in the shared report without a section link.
          </p>
          <div className="claims-list">
            {additionalClaims.map((item) => (
              <button
                className="claim-button"
                type="button"
                key={item.id}
                onClick={() => setClaim(item)}
              >
                <span className={`claim-dot status-${item.support_status}`} />
                <span>
                  {item.text}
                  <small>
                    {item.provenance} · {item.support_status}
                  </small>
                </span>
                <Icon
                  name="arrow"
                  size={16}
                />
              </button>
            ))}
          </div>
        </section>
      )}
      <EvidenceDialog
        claim={claim}
        report={report}
        onClose={() => setClaim(null)}
      />
    </>
  );
}
