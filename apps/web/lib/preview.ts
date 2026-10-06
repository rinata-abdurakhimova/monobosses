import { reportV1 } from "@/lib/fixtures/report-v1";
import type { CaseInput, PreviewMode, Report } from "@/lib/types";

export const sampleInput: CaseInput = {
  indication: "Inflammatory disease X",
  mechanism: "AX-17 inhibition",
  scope: "approach",
  modality: "Small molecule",
  development_stage: "Preclinical",
  program_data: "",
};
export const PREVIEW_STEPS = [
  "Preparing the sample",
  "Loading fictional evidence",
  "Previewing committee perspectives",
  "Preparing the report",
];
export const PREVIEW_STEP_MS = 650;
const STORAGE_PREFIX = "vic-r1-preview:";
export type PreviewCase = {
  input: CaseInput;
  mode: PreviewMode;
  created_at: string;
};

export function savePreviewCase(input: CaseInput, mode: PreviewMode): string {
  const id = crypto.randomUUID();
  sessionStorage.setItem(
    STORAGE_PREFIX + id,
    JSON.stringify({ input, mode, created_at: new Date().toISOString() }),
  );
  return id;
}
export function readPreviewCase(id: string): PreviewCase | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_PREFIX + id);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<PreviewCase>;
    if (
      !value.input ||
      typeof value.input.indication !== "string" ||
      typeof value.input.mechanism !== "string" ||
      !["approach", "program"].includes(value.input.scope) ||
      !["complete", "failed", "unavailable"].includes(value.mode ?? "")
    )
      return null;
    return value as PreviewCase;
  } catch {
    return null;
  }
}
export function getPreviewReport(mode: PreviewMode): Report {
  if (mode !== "unavailable") return reportV1;
  return {
    ...reportV1,
    sections: reportV1.sections.map((section) =>
      section.key === "sources"
        ? {
            ...section,
            status: "Data needed",
            limitation:
              "One source is unavailable in this scenario. The cached synthetic excerpt must not be treated as a fresh retrieval.",
          }
        : section,
    ),
    sources: reportV1.sources.map((source) =>
      source.id === "src-market"
        ? {
            ...source,
            available: false,
            limitation:
              "Simulated unavailable source. The cached excerpt below is a synthetic fixture, not a fresh retrieval.",
          }
        : source,
    ),
    claims: reportV1.claims.map((claim) =>
      claim.id === "market.differentiation"
        ? { ...claim, support_status: "unverified" }
        : claim,
    ),
  };
}
