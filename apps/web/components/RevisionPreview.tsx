"use client";

import Link from "next/link";
import beforeWire from "../../../contracts/fixtures/report-v1.json";
import afterWire from "../../../contracts/fixtures/report-v2.json";
import { mapApiReport } from "@/lib/contracts/report";
import { RevisionComparison } from "@/components/RevisionComparison";
import { ReportView } from "@/components/ReportView";

const before = mapApiReport(beforeWire);
const after = mapApiReport(afterWire);
export function RevisionPreview({ version }: { version: number }) {
  return (
    <>
      <div className="page-container revision-preview">
        <div className="mock-api-notice">
          <strong>Synthetic revision preview</strong>
          <p>
            These are the shared, fixed v1/v2 fixtures. No upload or model call
            produced this comparison.
          </p>
        </div>
        <nav
          className="state-actions"
          aria-label="Fixture versions"
        >
          <Link
            className="button button-secondary"
            href="/cases/revision-sample?version=1"
          >
            Open v1
          </Link>
          <Link
            className="button button-secondary"
            href="/cases/revision-sample?version=2"
          >
            Open v2
          </Link>
        </nav>
        <RevisionComparison
          before={before}
          after={after}
        />
        <p>
          Text/PDF imports and explicit reviews are available on Python API case
          pages. Working PDF extraction and evidence-driven revisions require R2
          #14.
        </p>
      </div>
      <ReportView
        key={version}
        report={version === 2 ? after : before}
        submitted={null}
      />
    </>
  );
}
