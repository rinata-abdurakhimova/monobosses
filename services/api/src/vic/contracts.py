#fake file to test r4-01

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class Source:
    id: str
    title: str
    type: str
    published_at: Optional[str] = None
    synthetic: bool = False

@dataclass
class Evidence:
    id: str
    source_id: str
    excerpt: str
    scope: str
    locator: Optional[str] = None
    limitations: Optional[str] = None

@dataclass
class EvidencePack:
    evidence: List[Evidence] = field(default_factory=list)
    sources: List[Source] = field(default_factory=list)
    retrieval_warnings: List[str] = field(default_factory=list)

@dataclass
class CaseInput:
    indication: str
    mechanism: str
    scope: str
    modality: Optional[str] = None
    development_stage: Optional[str] = None
    program_data: Optional[str] = None

@dataclass
class RunContext:
    model: Any = None

@dataclass
class Claim:
    id: str
    text: str
    provenance: str
    support_status: str
    evidence_ids: List[str]
    assumptions: List[str]
    scope: str
    importance: str

@dataclass
class Risk:
    id: str
    description: str
    priority: str
    claim_ids: List[str]
    impact: str
    next_check: str

@dataclass
class SectionContent:
    key: str
    summary: str
    claim_ids: List[str]
    limitations: List[str]
    structured_data: Dict[str, Any]

@dataclass
class RoleResult:
    role_id: str
    summary: str
    position: str
    claims: List[Claim]
    risks: List[Risk]
    unknowns: List[str]
    change_conditions: List[str]
    section_content: SectionContent