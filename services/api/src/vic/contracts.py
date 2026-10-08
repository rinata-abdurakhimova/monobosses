"""Shared technical contract v1. Owner: R2.

Every role imports its types from here. Any change to this file must be agreed with R2
and the consumers (R1 UI, R3 evidence, R4 science, R5 business) before merging.
"""
from dataclasses import dataclass, field
from datetime import date, datetime
import time
from enum import Enum
from typing import Annotated, Any, Literal, Protocol, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

MIN_PROGRAM_DATA_CHARS = 40  # placeholder threshold for "sufficient program data"

Id = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128,
                                      pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")]
# Claim IDs are stable semantic keys, e.g. "science.target_validation".
ClaimId = Annotated[str, StringConstraints(strip_whitespace=True, max_length=128,
                                           pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class VicModel(BaseModel):
    # extra="forbid": a typo in another role's output fails loudly instead of being dropped.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())


# ------------------------------------------------------------------ enums
class Scope(str, Enum):
    APPROACH = "approach"
    PROGRAM = "program"


class Recommendation(str, Enum):
    INVEST = "Invest"
    CONDITIONAL = "Conditional"
    DO_NOT_INVEST = "Do Not Invest"


class SectionKey(str, Enum):  # declaration order == report order
    RECOMMENDATION = "recommendation"
    SCIENTIFIC_THESIS = "scientific_thesis"
    HUMAN_TRANSLATION_THESIS = "human_translation_thesis"
    CLINICAL_DEVELOPMENT_PLAN = "clinical_development_plan"
    COMPETITIVE_LANDSCAPE = "competitive_landscape"
    COMMERCIAL_OPPORTUNITY = "commercial_opportunity"
    CAPITAL_TO_MILESTONE = "capital_to_milestone"
    KEY_RISKS = "key_risks"
    CRITICAL_UNKNOWNS = "critical_unknowns"
    DILIGENCE_QUESTIONS = "diligence_questions"
    SOURCES = "sources"


class Provenance(str, Enum):
    SOURCE = "source"
    USER = "user"
    AI = "ai"


class SupportStatus(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    MIXED = "mixed"
    UNVERIFIED = "unverified"
    UNKNOWN = "unknown"  # "unknown" is NOT a negative experimental result


class Importance(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunStage(str, Enum):
    VALIDATE = "validate"
    RETRIEVE = "retrieve"
    ANALYZE = "analyze"
    AUDIT = "audit"
    SYNTHESIZE = "synthesize"
    FINALIZE = "finalize"


class RunMode(str, Enum):
    LIVE = "live"
    EVIDENCE_ONLY = "evidence_only"


class RoleId(str, Enum):  # prompt IDs from the contract
    SCIENCE = "science"
    TRANSLATION = "translation"
    CLINICAL = "clinical"
    MARKET = "market"
    INVESTMENT = "investment"
    CHAIR = "chair"
    AUDIT = "audit"


# Open question for R3: final list of source types.
SourceType = Literal["peer_reviewed", "preprint", "registry", "regulatory", "company",
                     "patent", "database", "user_upload", "synthetic"]


# ------------------------------------------------------------------ input
class CaseInput(VicModel):
    indication: Text
    mechanism: Text
    scope: Scope
    program_data: str | None = None
    modality: str | None = None
    development_stage: str | None = None
    as_of_date: date | None = None

    @field_validator("program_data", "modality", "development_stage")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value

    @model_validator(mode="after")
    def _program_needs_data(self) -> "CaseInput":
        if self.scope == Scope.PROGRAM and len(self.program_data or "") < MIN_PROGRAM_DATA_CHARS:
            raise ValueError(
                f"scope=program requires sufficient program_data (at least {MIN_PROGRAM_DATA_CHARS} characters)")
        return self


# ------------------------------------------------------------------ evidence (R3)
class Source(VicModel):
    id: Id
    title: Text
    url: str | None = None  # null for private upload / synthetic
    type: SourceType
    published_at: date | None = None
    retrieved_at: datetime
    content_hash: Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]
    synthetic: bool
    document_id: Id | None = None


class Evidence(VicModel):
    id: Id
    source_id: Id
    excerpt: Text
    locator: Text  # page / section / record field
    scope: Scope
    limitations: list[str] = Field(default_factory=list)


class EvidencePack(VicModel):
    sources: list[Source]
    evidence: list[Evidence]
    retrieval_warnings: list[str] = Field(default_factory=list)
    snapshot_id: Id
    synthetic: bool


# ------------------------------------------------------------------ analysis (R4/R5)
class Claim(VicModel):
    id: ClaimId
    text: Text
    provenance: Provenance
    support_status: SupportStatus
    evidence_ids: list[Id] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    scope: Scope
    importance: Importance

    @model_validator(mode="after")
    def _no_invented_links(self) -> "Claim":
        if self.provenance == Provenance.SOURCE and not self.evidence_ids:
            raise ValueError(f"claim {self.id}: provenance=source requires evidence_ids")
        if self.support_status in (SupportStatus.SUPPORTED, SupportStatus.CONTRADICTED,
                                   SupportStatus.MIXED) and not self.evidence_ids:
            raise ValueError(f"claim {self.id}: support_status={self.support_status.value} "
                             "requires evidence_ids")
        return self


class SectionContent(VicModel):
    key: SectionKey
    summary: Text
    claim_ids: list[ClaimId] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    structured_data: dict[str, Any] | None = None


class Risk(VicModel):
    id: Id
    description: Text
    priority: Importance
    claim_ids: list[ClaimId] = Field(default_factory=list)
    impact: Text
    next_check: Text


class DiligenceQuestion(VicModel):
    question: Text
    why_it_matters: Text
    evidence_needed: Text
    decision_if_positive: Text
    decision_if_negative: Text


class Disagreement(VicModel):  # open question for R5: final shape
    topic: Text
    role_ids: list[RoleId]
    summary: Text
    resolution: Text


class RoleResult(VicModel):
    role_id: RoleId
    summary: Text
    position: Text
    claims: list[Claim] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    change_conditions: list[str] = Field(default_factory=list)
    section_content: list[SectionContent] = Field(default_factory=list)


class AuditFinding(VicModel):
    claim_id: ClaimId
    verdict: SupportStatus  # open question for R3: reuse SupportStatus for now
    reason: Text
    evidence_ids: list[Id] = Field(default_factory=list)
    blocking: bool


class AuditResult(VicModel):
    findings: list[AuditFinding] = Field(default_factory=list)
    unresolved_critical_claim_ids: list[ClaimId] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CommitteeDecision(VicModel):
    recommendation: Recommendation
    rationale: Text
    conditions: list[str] = Field(default_factory=list)
    disagreements: list[Disagreement] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    questions: list[DiligenceQuestion] = Field(default_factory=list)
    additional_claims: list[Claim] = Field(default_factory=list)


# ------------------------------------------------------------------ report
class ClaimChange(VicModel):
    claim_id: ClaimId
    before: Claim | None = None
    after: Claim | None = None


class Revision(VicModel):
    parent_report_id: Id
    new_evidence_ids: list[Id]
    changed_claims: list[ClaimChange]
    previous_recommendation: Recommendation
    new_recommendation: Recommendation
    explanation: Text


class Report(VicModel):
    id: Id
    case_id: Id
    run_id: Id
    version: int = Field(ge=1)
    scope: Scope
    synthetic: bool
    snapshot_id: Id
    recommendation: Recommendation
    rationale: Text
    decision_conditions: list[str] = Field(default_factory=list)
    sections: list[SectionContent]
    roles: list[RoleResult]
    claims: list[Claim]
    evidence: list[Evidence]
    sources: list[Source]
    disagreements: list[Disagreement] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    diligence_questions: list[DiligenceQuestion] = Field(min_length=5, max_length=10)
    revision: Revision | None = None

    @model_validator(mode="after")
    def _structure(self) -> "Report":
        keys = [s.key for s in self.sections]
        if len(keys) != len(SectionKey) or set(keys) != set(SectionKey):
            raise ValueError("report must contain each of the 11 section keys exactly once")
        if self.version == 1 and self.revision is not None:
            raise ValueError("version 1 cannot have a revision block")
        if self.version > 1 and self.revision is None:
            raise ValueError("version > 1 requires a revision block")
        return self


# ------------------------------------------------------------------ run
class ErrorBody(VicModel):
    code: str
    message: str
    retryable: bool = False


class ErrorEnvelope(VicModel):
    error: ErrorBody


class Usage(VicModel):
    calls: int = 0
    input_tokens: int | None = None   # None = unavailable (never fake 0)
    output_tokens: int | None = None


class Run(VicModel):
    id: Id
    case_id: Id
    status: RunStatus
    stage: RunStage | None = None
    report_version: int | None = None
    warnings: list[str] = Field(default_factory=list)
    error: ErrorBody | None = None
    trace_id: Id
    usage: Usage = Field(default_factory=Usage)
    latency_ms: dict[str, int] = Field(default_factory=dict)  # per stage + "total"
    cost_usd: float | None = None  # None = unavailable (never fake 0)
    model_version: str | None = None
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    config_version: str | None = None
    # Additive fields (not in the contract table; agreed as open question 8):
    mode: RunMode | None = None
    parent_report_id: Id | None = None

    @model_validator(mode="after")
    def _consistency(self) -> "Run":
        if self.status == RunStatus.COMPLETED and self.report_version is None:
            raise ValueError("completed run requires report_version")
        if self.status == RunStatus.FAILED and self.error is None:
            raise ValueError("failed run requires error")
        return self


# ------------------------------------------------------------------ API bodies
class RunCreate(VicModel):
    mode: RunMode
    parent_report_id: Id | None = None


class CaseCreated(VicModel):
    case_id: Id


class RunCreated(VicModel):
    run_id: Id


class EvidenceCreate(VicModel):
    title: Text
    text: Text
    published_at: date | None = None
    synthetic: bool = False


class EvidenceCreated(VicModel):
    source_id: Id
    evidence_ids: list[Id]


class HealthStatus(VicModel):
    status: Literal["ok"]


class UploadedDocument(VicModel):  # passed to R3: import_document(...)
    filename: str
    content_type: str
    content: bytes
    title: str
    synthetic: bool = False


T = TypeVar("T", bound=BaseModel)


class LlmAdapter(Protocol):
    async def generate_structured(self, prompt_id: str, payload: dict[str, Any],
                                  response_model: type[T], ctx: "RunContext") -> T: ...


@dataclass
class RunBudget:
    max_cost_usd: float | None = None
    max_seconds: int = 600
    deadline: float | None = None       # time.monotonic() value, set when the run starts
    spent_cost_usd: float = 0.0
    cost_unavailable: bool = False      # True once any call had no usable usage/price

    def remaining_seconds(self) -> float | None:
        if self.deadline is None:
            return None
        return self.deadline - time.monotonic()


@dataclass
class TraceCollector:
    """Collects stage events and usage. Must never contain secrets or raw prompts/outputs."""
    events: list[dict[str, Any]] = field(default_factory=list)
    usage: list[dict[str, Any]] = field(default_factory=list)

    def log(self, stage: RunStage, message: str) -> None:
        self.events.append({"stage": stage.value, "message": message})

    def record_usage(self, prompt_id: str, input_tokens: int | None,
                     output_tokens: int | None, **extra: Any) -> None:
        self.usage.append({"prompt_id": prompt_id, "input_tokens": input_tokens,
                           "output_tokens": output_tokens, **extra})


@dataclass
class RunContext:
    case_id: str
    run_id: str
    snapshot_id: str | None
    as_of_date: date | None
    mode: RunMode
    model: LlmAdapter | None = None
    budget: RunBudget = field(default_factory=RunBudget)
    trace: TraceCollector = field(default_factory=TraceCollector)
    # Audit findings per role id for the single repair round (agents MAY read it).
    feedback: dict[str, list[Any]] = field(default_factory=dict)
    # Non-fatal notes any module may add; copied into Run.warnings.
    warnings: list[str] = field(default_factory=list)