"use client";

import { isVisibleRole } from "@/lib/visible-roles";

import Link from "next/link";
import { Icon } from "@/components/Icon";
import { RecommendationCard } from "@/components/RecommendationCard";
import { ReportSections } from "@/components/ReportSections";
import { RoleCard } from "@/components/RoleCard";
import type { Report } from "@/lib/types";
import type { PreviewCase } from "@/lib/preview";

export function ReportView({
  report,
  submitted,
}: {
  report: Report;
  submitted: PreviewCase | null;
}) {
  function revealSection(key: string) {
    const section = document.getElementById(`section-${key}`);
    if (section instanceof HTMLDetailsElement) section.open = true;
  }
  const visibleRoles = report.roles.filter((role) => isVisibleRole(role.id));
  return (
    <div className="page-container report-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            INVESTMENT UNDERWRITING ·{" "}
            {report.synthetic ? "SYNTHETIC CASE" : "SAVED REPORT"}
          </span>
          <h1>A thesis, with the evidence in view.</h1>
          <p>{report.title}</p>
        </div>
        <Link
          className="button button-primary"
          href="/"
        >
          <Icon
            name="plus"
            size={17}
          />
          New assessment
        </Link>
      </div>
      {report.synthetic && (
        <div className="synthetic-banner">
          <Icon
            name="flask"
            size={19}
          />
          <div>
            <strong>Synthetic example — not a live recommendation</strong>
            <p>
              This report is marked synthetic by its provider. It is an example
              and does not establish a live assessment of your submitted input.
            </p>
          </div>
          <span className="tiny-tag">Sample v{report.version}</span>
        </div>
      )}
      <div className="panel report-metadata">
        <span className="eyebrow">SAVED REPORT · VERSION {report.version}</span>
        <dl>
          <div>
            <dt>Report</dt>
            <dd>{report.id}</dd>
          </div>
          <div>
            <dt>Run</dt>
            <dd>{report.contract.run_id}</dd>
          </div>
          <div>
            <dt>Snapshot</dt>
            <dd>{report.contract.snapshot_id}</dd>
          </div>
        </dl>
        <Link href="/cases/revision-sample?version=2">
          Explore the synthetic v1 → v2 comparison
        </Link>
      </div>
      {submitted && (
        <details className="submitted-input">
          <summary>
            Your preview input{" "}
            <Icon
              name="chevron"
              size={15}
            />
          </summary>
          <dl>
            <div>
              <dt>Indication</dt>
              <dd>{submitted.input.indication}</dd>
            </div>
            <div>
              <dt>Mechanism</dt>
              <dd>{submitted.input.mechanism}</dd>
            </div>
            <div>
              <dt>Requested scope</dt>
              <dd>{submitted.input.scope}</dd>
            </div>
            {submitted.input.modality && (
              <div>
                <dt>Modality</dt>
                <dd>{submitted.input.modality}</dd>
              </div>
            )}
            {submitted.input.development_stage && (
              <div>
                <dt>Stage</dt>
                <dd>{submitted.input.development_stage}</dd>
              </div>
            )}
            {submitted.input.program_data && (
              <div>
                <dt>Programme data</dt>
                <dd>{submitted.input.program_data}</dd>
              </div>
            )}
          </dl>
          <p>
            Stored in this browser tab only. These details have not been
            analysed.
          </p>
        </details>
      )}
      {report.sources.some((source) => !source.available) && (
        <div
          className="warning-banner"
          role="status"
        >
          <Icon
            name="warning"
            size={19}
          />
          <div>
            <strong>A source is unavailable in this preview</strong>
            <p>
              The company excerpt is a cached synthetic sample. Source failure
              does not establish an absence of competition or risk.
            </p>
          </div>
        </div>
      )}
      <div className="report-overview">
        <RecommendationCard report={report} />
        <aside className="overview-aside">
          <div className="panel overview-facts">
            <span className="eyebrow">ASSESSMENT AT A GLANCE</span>
            <dl>
              <div>
                <dt>Assessment scope</dt>
                <dd>
                  <span className="scope-pill">
                    {report.scope === "approach"
                      ? "Biological approach"
                      : "Specific programme"}
                  </span>
                </dd>
              </div>
              <div>
                <dt>Open unknowns</dt>
                <dd>
                  <span className="metric-count metric-count-warning">
                    {report.unknowns.length}
                  </span>{" "}
                  <span className="metric-description">
                    questions unresolved
                  </span>
                </dd>
              </div>
              <div>
                <dt>Sources</dt>
                <dd>
                  <span className="metric-count">{report.sources.length}</span>{" "}
                  <span className="metric-description">
                    {report.synthetic
                      ? "fictional documents"
                      : "source documents"}
                  </span>
                </dd>
              </div>
              <div>
                <dt>Committee</dt>
                <dd>
                  <span className="metric-count">{visibleRoles.length}</span>{" "}
                  <span className="metric-description">
                    {report.synthetic
                      ? "AI perspectives in fixture"
                      : "AI perspectives"}
                  </span>
                </dd>
              </div>
            </dl>
            <p>
              Unknowns are not negative findings. Agreement between AI
              perspectives is not independent evidence.
            </p>
          </div>
          <div className="next-step-card">
            <Icon
              name="arrow"
              size={22}
            />
            <h3>Ask the question that changes the decision.</h3>
            <p>Start with safe human exposure and target engagement.</p>
            <a
              href="#section-diligence_questions"
              onClick={() => revealSection("diligence_questions")}
            >
              View diligence questions{" "}
              <Icon
                name="arrow"
                size={15}
              />
            </a>
          </div>
        </aside>
      </div>
      <div className="report-layout">
        <aside className="report-nav">
          <span className="eyebrow">IN THIS REPORT</span>
          <nav aria-label="Report sections">
            {report.sections.map((s, i) => (
              <a
                key={s.key}
                href={`#section-${s.key}`}
                onClick={() => revealSection(s.key)}
              >
                <span>{String(i + 1).padStart(2, "0")}</span>
                {s.title}
              </a>
            ))}
            <a href="#committee-perspectives">
              <Icon
                name="layers"
                size={15}
              />
              Committee perspectives
            </a>
          </nav>
        </aside>
        <div className="report-main">
          <div className="section-heading">
            <div>
              <span className="eyebrow">THE FULL PICTURE</span>
              <h2>Underwriting report</h2>
            </div>
            <span className="tiny-tag">11 sections</span>
          </div>
          <ReportSections report={report} />
        </div>
      </div>
      <section
        id="committee-perspectives"
        className="perspectives"
      >
        <div className="section-heading">
          <div>
            <span className="eyebrow">
              MULTIPLE PERSPECTIVES. ONE EXPLAINED DECISION.
            </span>
            <h2>Inside the committee</h2>
          </div>
        </div>
        <p className="perspectives-intro">
          AI perspectives, not independent human experts. Their agreement does
          not establish that a claim is true.
        </p>
        <div className="role-grid">
          {visibleRoles.map((role) => (
            <RoleCard
              key={role.id}
              role={role}
              report={report}
            />
          ))}
        </div>
        <div className="disagreement-note">
          <Icon
            name="layers"
            size={21}
          />
          <div>
            <strong>Where perspectives differ</strong>
            <p>{report.disagreements}</p>
          </div>
        </div>
      </section>
    </div>
  );
}
