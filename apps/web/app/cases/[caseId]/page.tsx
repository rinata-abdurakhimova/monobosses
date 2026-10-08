import { CasePreview } from "@/components/CasePreview";
import { ApiCase } from "@/components/ApiCase";
import Link from "next/link";
import { RevisionPreview } from "@/components/RevisionPreview";

export default async function CasePage({
  params,
  searchParams,
}: {
  params: Promise<{ caseId: string }>;
  searchParams: Promise<{
    flow?: string;
    run?: string;
    version?: string;
    previous?: string;
  }>;
}) {
  const { caseId } = await params;
  const query = await searchParams;
  function parseVersion(value?: string) {
    return value &&
      /^[1-9][0-9]*$/.test(value) &&
      Number.isSafeInteger(Number(value))
      ? Number(value)
      : null;
  }
  if (query.version && !parseVersion(query.version))
    return (
      <div className="page-container">
        <h1>Invalid report version</h1>
        <p>Use a positive whole-number version.</p>
      </div>
    );
  if (caseId === "revision-sample" && !query.flow) {
    const version = parseVersion(query.version) ?? 2;
    if (version > 2)
      return (
        <div className="page-container">
          <h1>Fixture version unavailable</h1>
          <p>This preview contains v1 and v2 only.</p>
        </div>
      );
    return <RevisionPreview version={version} />;
  }
  if (query.flow === "mock-api" || query.flow === "api")
    return (
      <ApiCase
        flow={query.flow}
        caseId={caseId}
        runId={typeof query.run === "string" ? query.run : null}
        requestedVersion={parseVersion(query.version)}
        previousVersion={parseVersion(query.previous)}
      />
    );
  if (query.flow)
    return (
      <div className="page-container">
        <section className="panel state-panel">
          <h1>This workflow is not enabled.</h1>
          <p>
            A backend request will never silently fall back to a fictional
            report.
          </p>
          <Link
            className="button button-primary"
            href="/"
          >
            Back to assessment
          </Link>
        </section>
      </div>
    );
  return <CasePreview caseId={caseId} />;
}
