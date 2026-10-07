import type * as Contract from "./contracts/generated";

/** Presentation models mapped from the shared R2 contract at the data boundary. */
export type Scope = Contract.Scope;
export type PreviewMode = "complete" | "failed" | "unavailable";
export type CaseInput = Pick<
  Contract.CaseInput,
  "indication" | "mechanism" | "scope"
> & {
  modality: string;
  development_stage: string;
  program_data: string;
};
export type Recommendation = Contract.Recommendation;
export type SectionKey = Contract.SectionKey;
export type ClaimStatus = Contract.SupportStatus;
export type Claim = Contract.Claim & {
  evidence_ids: string[];
  assumptions: string[];
};
export type Source = Contract.Source & {
  available: boolean;
  limitation: string;
};
export type Evidence = Contract.Evidence;
export type ReportSection = {
  key: SectionKey;
  title: string;
  summary: string;
  status:
    | "Supported in sample"
    | "Contradicted in sample"
    | "Uncertain"
    | "Data needed"
    | "Illustrative plan";
  points: string[];
  claim_ids: string[];
  limitation?: string;
};
export type RoleResult = {
  id: string;
  name: string;
  initials: string;
  summary: string;
  position: string;
  unknown: string;
};
export type Risk = {
  id: string;
  title: string;
  priority: "Critical" | "Material" | "Minor";
  impact: string;
  next_check: string;
};
export type DiligenceQuestion = {
  question: string;
  why: string;
  evidence_needed: string;
  positive: string;
  negative: string;
};
export type Report = {
  contract: Contract.Report;
  version: number;
  id: string;
  title: string;
  recommendation: Recommendation;
  scope: Scope;
  synthetic: true;
  rationale: string;
  conditions: string[];
  sections: ReportSection[];
  claims: Claim[];
  sources: Source[];
  evidence: Evidence[];
  roles: RoleResult[];
  risks: Risk[];
  unknowns: string[];
  diligence_questions: DiligenceQuestion[];
  disagreements: string;
};
