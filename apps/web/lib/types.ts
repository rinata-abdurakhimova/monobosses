/** Provisional UI view models, not an implementation of R2's API contract.
 * Replace/adapt at the data boundary when R2 publishes contracts v1.
 */
export type Scope = "approach" | "program";
export type PreviewMode = "complete" | "failed" | "unavailable";
export type CaseInput = {
  indication: string;
  mechanism: string;
  scope: Scope;
  modality: string;
  development_stage: string;
  program_data: string;
};
export type Recommendation = "Invest" | "Conditional" | "Do Not Invest";
export type SectionKey =
  | "recommendation"
  | "scientific_thesis"
  | "human_translation_thesis"
  | "clinical_development_plan"
  | "competitive_landscape"
  | "commercial_opportunity"
  | "capital_to_milestone"
  | "key_risks"
  | "critical_unknowns"
  | "diligence_questions"
  | "sources";
export type ClaimStatus = "supported" | "mixed" | "unknown" | "unverified";
export type Claim = {
  id: string;
  text: string;
  provenance: "source" | "ai";
  support_status: ClaimStatus;
  evidence_ids: string[];
  assumptions: string[];
};
export type Source = {
  id: string;
  title: string;
  type: string;
  available: boolean;
  limitation: string;
};
export type Evidence = {
  id: string;
  source_id: string;
  excerpt: string;
  locator: string;
};
export type ReportSection = {
  key: SectionKey;
  title: string;
  summary: string;
  status:
    "Supported in sample" | "Uncertain" | "Data needed" | "Illustrative plan";
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
  priority: "Critical" | "Material";
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
