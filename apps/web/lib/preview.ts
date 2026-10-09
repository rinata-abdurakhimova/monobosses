import { reportR5 } from "./fixtures/report-r5.ts";
import type { CaseInput, PreviewMode, Report } from "@/lib/types";
import sharedCase from "../../../contracts/fixtures/case.json" with { type: "json" };

export const sampleInput: CaseInput = {
  indication: sharedCase.indication,
  mechanism: sharedCase.mechanism,
  scope: reportR5.scope,
  modality: sharedCase.modality ?? "",
  development_stage: sharedCase.development_stage ?? "",
  program_data: sharedCase.program_data ?? "",
};
export const PREVIEW_STEPS = [
  "Preparing the sample",
  "Loading fictional evidence",
  "Previewing committee perspectives",
  "Preparing the report",
];
export const PREVIEW_STEP_MS = 650;
const STORAGE_PREFIX = "vic-r1-preview:contracts-v1:";
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
  if (mode !== "unavailable") return reportR5;
  return {
    ...reportR5,
    sections: reportR5.sections.map((section) =>
      section.key === "sources"
        ? {
            ...section,
            status: "Data needed",
            limitation:
              "One source is unavailable in this scenario. The cached synthetic excerpt must not be treated as a fresh retrieval.",
          }
        : section,
    ),
    sources: reportR5.sources.map((source) =>
      source.id === "src-synthetic-04"
        ? {
            ...source,
            available: false,
            limitation:
              "Simulated unavailable source. The cached excerpt below is a synthetic fixture, not a fresh retrieval.",
          }
        : source,
    ),
    claims: reportR5.claims.map((claim) =>
      claim.id === "market.company_claims"
        ? { ...claim, support_status: "unverified" }
        : claim,
    ),
  };
}
