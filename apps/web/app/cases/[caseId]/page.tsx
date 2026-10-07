import { CasePreview } from "@/components/CasePreview";
import { ApiCase } from "@/components/ApiCase";
import Link from "next/link";

export default async function CasePage({
  params,
  searchParams,
}: {
  params: Promise<{ caseId: string }>;
  searchParams: Promise<{ flow?: string; run?: string }>;
}) {
  const { caseId } = await params;
  const query = await searchParams;
  if (query.flow === "mock-api" || query.flow === "api")
    return (
      <ApiCase
        flow={query.flow}
        caseId={caseId}
        runId={typeof query.run === "string" ? query.run : null}
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
