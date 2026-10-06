import { CasePreview } from "@/components/CasePreview";

export default async function CasePage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = await params;
  return <CasePreview caseId={caseId} />;
}
