// Generated from contracts/openapi.json. Run npm run contracts:generate.
export type Body_upload_document_cases__case_id__documents_post = {
  file: string;
  synthetic?: boolean;
  title: string;
};

export type CaseCreated = {
  case_id: string;
};

export type CaseInput = {
  as_of_date?: string | null;
  development_stage?: string | null;
  indication: string;
  mechanism: string;
  modality?: string | null;
  program_data?: string | null;
  scope: Scope;
};

export type Claim = {
  assumptions?: Array<string>;
  evidence_ids?: Array<string>;
  id: string;
  importance: Importance;
  provenance: Provenance;
  scope: Scope;
  support_status: SupportStatus;
  text: string;
};

export type ClaimChange = {
  after?: Claim | null;
  before?: Claim | null;
  claim_id: string;
};

export type DiligenceQuestion = {
  decision_if_negative: string;
  decision_if_positive: string;
  evidence_needed: string;
  question: string;
  why_it_matters: string;
};

export type Disagreement = {
  resolution: string;
  role_ids: Array<RoleId>;
  summary: string;
  topic: string;
};

export type ErrorBody = {
  code: string;
  message: string;
  retryable?: boolean;
};

export type ErrorEnvelope = {
  error: ErrorBody;
};

export type Evidence = {
  excerpt: string;
  id: string;
  limitations?: Array<string>;
  locator: string;
  scope: Scope;
  source_id: string;
};

export type EvidenceCreate = {
  published_at?: string | null;
  synthetic?: boolean;
  text: string;
  title: string;
};

export type EvidenceCreated = {
  evidence_ids: Array<string>;
  source_id: string;
};

export type HealthStatus = {
  status: "ok";
};

export type Importance = "critical" | "major" | "minor";

export type Provenance = "source" | "user" | "ai";

export type Recommendation = "Invest" | "Conditional" | "Do Not Invest";

export type Report = {
  case_id: string;
  claims: Array<Claim>;
  decision_conditions?: Array<string>;
  diligence_questions: Array<DiligenceQuestion>;
  disagreements?: Array<Disagreement>;
  evidence: Array<Evidence>;
  id: string;
  rationale: string;
  recommendation: Recommendation;
  revision?: Revision | null;
  risks?: Array<Risk>;
  roles: Array<RoleResult>;
  run_id: string;
  scope: Scope;
  sections: Array<SectionContent>;
  snapshot_id: string;
  sources: Array<Source>;
  synthetic: boolean;
  version: number;
};

export type Revision = {
  changed_claims: Array<ClaimChange>;
  explanation: string;
  new_evidence_ids: Array<string>;
  new_recommendation: Recommendation;
  parent_report_id: string;
  previous_recommendation: Recommendation;
};

export type Risk = {
  claim_ids?: Array<string>;
  description: string;
  id: string;
  impact: string;
  next_check: string;
  priority: Importance;
};

export type RoleId =
  | "science"
  | "translation"
  | "clinical"
  | "market"
  | "investment"
  | "chair"
  | "audit"
  | "failure_miner"
  | "investment_threshold"
  | "partnerships"
  | "ip_licensing";

export type RoleResult = {
  change_conditions?: Array<string>;
  claims?: Array<Claim>;
  position: string;
  risks?: Array<Risk>;
  role_id: RoleId;
  section_content?: Array<SectionContent>;
  summary: string;
  unknowns?: Array<string>;
};

export type Run = {
  case_id: string;
  config_version?: string | null;
  cost_usd?: number | null;
  error?: ErrorBody | null;
  id: string;
  latency_ms?: Record<string, number>;
  mode?: RunMode | null;
  model_version?: string | null;
  parent_report_id?: string | null;
  prompt_versions?: Record<string, string>;
  report_version?: number | null;
  stage?: RunStage | null;
  status: RunStatus;
  trace_id: string;
  usage?: Usage;
  warnings?: Array<string>;
};

export type RunCreate = {
  mode: RunMode;
  parent_report_id?: string | null;
};

export type RunCreated = {
  run_id: string;
};

export type RunMode = "live" | "evidence_only";

export type RunStage =
  "validate" | "retrieve" | "analyze" | "audit" | "synthesize" | "finalize";

export type RunStatus = "queued" | "running" | "completed" | "failed";

export type Scope = "approach" | "program";

export type SectionContent = {
  claim_ids?: Array<string>;
  key: SectionKey;
  limitations?: Array<string>;
  structured_data?: Record<string, unknown> | null;
  summary: string;
};

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

export type Source = {
  content_hash: string;
  document_id?: string | null;
  id: string;
  published_at?: string | null;
  retrieved_at: string;
  synthetic: boolean;
  title: string;
  type:
    | "peer_reviewed"
    | "preprint"
    | "registry"
    | "regulatory"
    | "company"
    | "patent"
    | "database"
    | "user_upload"
    | "synthetic";
  url?: string | null;
};

export type SupportStatus =
  "supported" | "contradicted" | "mixed" | "unverified" | "unknown";

export type Usage = {
  calls?: number;
  input_tokens?: number | null;
  output_tokens?: number | null;
};
