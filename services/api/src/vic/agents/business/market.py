"""R5-01 market node. One structured LLM call through the shared R2 adapter."""
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vic.contracts import CaseInput, Claim, EvidencePack, Risk, RoleResult, RunContext, SectionContent
from .calculations import MarketScenario, estimate_market_scenarios, summarize_market_ranges

PROMPT_ID = "market"
PROMPT_VERSION = "1.2.0"
PROMPT_PATH = Path(__file__).parent / "prompts" / "market.md"
Category = Literal["standard_of_care", "approved", "clinical_stage", "same_target", "alternative_mechanism", "discontinued"]


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketClaim(StrictOutput):
    id: str = Field(pattern=r"^market\.[a-z0-9_.]+$")
    text: str = Field(min_length=1)
    support_status: Literal["supported", "contradicted", "mixed", "unverified", "unknown"]
    evidence_ids: list[str]
    assumptions: list[str]
    scope: Literal["approach", "program"]
    importance: Literal["critical", "major", "minor"]


class Competitor(StrictOutput):
    name: str = Field(min_length=1)
    # Tags overlap: same-target can also be approved; status is separate.
    categories: list[Category] = Field(min_length=1)
    development_status: Literal["approved", "clinical_stage", "preclinical", "discontinued", "unknown"]
    discontinuation_reason: str | None = Field(min_length=1)
    discontinuation_reason_claim_ids: list[str]
    discontinuation_unknowns: list[str]
    claim_ids: list[str] = Field(min_length=1)


class CoverageFinding(StrictOutput):
    status: Literal["documented", "insufficient_data"]
    claim_ids: list[str]
    unknowns: list[str]


class PricingAnalogue(StrictOutput):
    name: str = Field(min_length=1)
    price_description: str | None = Field(min_length=1)
    geography: str | None = Field(min_length=1)
    as_of_date: str | None = Field(min_length=1)
    comparability: str = Field(min_length=1)
    limitations: list[str]
    claim_ids: list[str] = Field(min_length=1)
    unknowns: list[str]


class AccessAssessment(StrictOutput):
    reimbursement: list[str]
    prescribing: list[str]
    other_access: list[str]
    claim_ids: list[str]
    unknowns: list[str]


class CommercialValue(StrictOutput):
    assessment: Literal["potential_value", "limited_value", "mixed", "insufficient_data"]
    rationale: str = Field(min_length=1)
    unmet_need: str | None = Field(min_length=1)
    willingness_to_pay: str | None = Field(min_length=1)
    claim_ids: list[str]
    unknowns: list[str]


class MarketQuestion(StrictOutput):
    question: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    evidence_needed: str = Field(min_length=1)
    decision_if_positive: str = Field(min_length=1)
    decision_if_negative: str = Field(min_length=1)
    claim_ids: list[str]


class Differentiation(StrictOutput):
    comparator: str = Field(min_length=1)
    dimension: Literal["benefit", "safety", "access", "administration", "other"]
    assessment: str = Field(min_length=1)
    claim_ids: list[str] = Field(min_length=1)


class MarketRisk(StrictOutput):
    id: str = Field(pattern=r"^market\.risk\.[a-z0-9_.]+$")
    description: str
    priority: Literal["critical", "major", "minor"]
    claim_ids: list[str]
    impact: str
    next_check: str


class TargetPopulation(StrictOutput):
    """Patients who may benefit, not customers of the underwriting application.

    Missing facts remain null; all nonempty descriptions reference claims.
    Clinical suitability must be checked against R4 outputs during integration.
    """
    description: str | None = Field(min_length=1)
    indication: str | None = Field(min_length=1)
    eligibility: list[str]
    geography: str | None = Field(min_length=1)
    access_limitations: list[str]
    claim_ids: list[str]
    unknowns: list[str]


class MarketAnalysis(StrictOutput):
    summary: str = Field(min_length=1)
    commercial_summary: str = Field(min_length=1)
    position: Literal["favorable", "mixed", "unfavorable", "insufficient_data"]
    claims: list[MarketClaim]
    competitors: list[Competitor]
    target_population: TargetPopulation
    competitive_coverage: dict[Category, CoverageFinding]
    pricing_analogues: list[PricingAnalogue]
    pricing_unknowns: list[str]
    access: AccessAssessment
    commercial_value: CommercialValue
    diligence_questions: list[MarketQuestion] = Field(min_length=1)
    differentiation: list[Differentiation]
    risks: list[MarketRisk]
    unknowns: list[str]
    change_conditions: list[str]
    limitations: list[str]


def prepare_market_inputs(case: CaseInput, pack: EvidencePack,
                          scenarios: list[MarketScenario] | None = None,
                          clinical: RoleResult | None = None) -> dict:
    """Keep full supplied excerpts and provenance; avoid losing safety context.

    No retrieval is done here. Scenario numbers are caller supplied, never LLM
    generated. R3/R2 control corpus size, historical availability and retrieval.
    """
    if case.scope not in ("approach", "program"):
        raise ValueError("Invalid case scope")
    if clinical is not None:
        if clinical.role_id != "clinical":
            raise ValueError("Clinical input must be a clinical RoleResult")
        # Explicit upstream result, no agent calls here. Its evidence must be in
        # the same snapshot; R4 eligibility is context, not automatic truth.
        if any(not set(c.evidence_ids) <= {e.id for e in pack.evidence}
               for c in clinical.claims):
            raise ValueError("Clinical input requires evidence from the supplied pack")
    sources = {s.id: s for s in pack.sources}
    ids = {e.id for e in pack.evidence}
    if len(sources) != len(pack.sources) or len(ids) != len(pack.evidence):
        raise ValueError("Duplicate source/evidence IDs")
    evidence = []
    for e in pack.evidence:
        if e.source_id not in sources:
            raise ValueError(f"Evidence {e.id} has no source")
        if e.scope not in ("approach", "program"):
            raise ValueError("Invalid evidence scope")
        s = sources[e.source_id]
        evidence.append({"id": e.id, "source_id": e.source_id, "excerpt": e.excerpt,
                         "scope": e.scope, "locator": e.locator, "limitations": e.limitations,
                         "source_title": s.title, "source_type": s.type,
                         "published_at": s.published_at, "synthetic": s.synthetic})
    for scenario in scenarios or []:
        date.fromisoformat(scenario.as_of_date)
        for key in ("population", "eligible_fraction", "access_fraction", "annual_price"):
            links = scenario.input_evidence_ids.get(key, [])
            if getattr(scenario, key) is not None and (not links or not set(links) <= ids):
                raise ValueError(f"Scenario input {key} requires valid evidence IDs")
        if any(not set(links) <= ids for links in scenario.input_evidence_ids.values()):
            raise ValueError("Unknown scenario evidence ID")
    return {"prompt_version": PROMPT_VERSION,
            "case": {k: getattr(case, k, None) for k in
                     ("indication", "mechanism", "scope", "modality", "development_stage", "program_data", "as_of_date")},
            "evidence": evidence, "retrieval_warnings": pack.retrieval_warnings,
            "clinical_input": asdict(clinical) if clinical is not None else None,
            "clinical_alignment": "R4 input supplied; reconcile eligibility" if clinical else "R4 review pending",
            "calculated_scenarios": estimate_market_scenarios(scenarios or [])}


def classify_competitors(analysis: MarketAnalysis) -> dict[str, list[dict]]:
    """Group model-extracted competitors by tags; never infer approval from name."""
    groups = {k: [] for k in ("standard_of_care", "approved", "clinical_stage", "same_target", "alternative_mechanism", "discontinued")}
    for c in analysis.competitors:
        for tag in dict.fromkeys(c.categories):
            groups[tag].append(c.model_dump())
    return groups


def assess_differentiation(analysis: MarketAnalysis) -> list[dict]:
    """Attach evidence and support labels to comparator-specific assessments."""
    claims = {c.id: c for c in analysis.claims}
    return [{**d.model_dump(),
             "evidence_ids": sorted({e for cid in d.claim_ids for e in claims[cid].evidence_ids}),
             "support_statuses": {cid: claims[cid].support_status for cid in d.claim_ids}}
            for d in analysis.differentiation]


def identify_market_gaps(analysis: MarketAnalysis, calculations: list[dict]) -> list[str]:
    """Combine reported unknowns and explicitly missing scenario inputs."""
    gaps = [*analysis.unknowns, *analysis.target_population.unknowns,
            *analysis.pricing_unknowns, *analysis.access.unknowns,
            *analysis.commercial_value.unknowns]
    for finding in analysis.competitive_coverage.values():
        gaps.extend(finding.unknowns)
    for competitor in analysis.competitors:
        gaps.extend(competitor.discontinuation_unknowns)
    for analogue in analysis.pricing_analogues:
        gaps.extend(analogue.unknowns)
    if not analysis.target_population.eligibility:
        gaps.append("Clinical eligibility is unknown; request R4 review.")
    if not analysis.target_population.indication:
        gaps.append("Target population indication is unknown.")
    if analysis.target_population.description is None:
        gaps.append("Target patient population is unknown; request population evidence from R3/R4.")
    if analysis.target_population.geography is None:
        gaps.append("Target geography is unknown; request geographic scope and access evidence.")
    if not calculations:
        gaps.append("No reviewed numeric inputs: market size and pricing remain unknown; request population, eligibility, access and pricing evidence from R3.")
    for result in calculations:
        for key in result["missing_inputs"]:
            gaps.append(f"{result['inputs']['name']}: missing {key}; request evidence from R3.")
    for c in analysis.claims:
        if c.support_status in ("unknown", "unverified"):
            gaps.append(f"Requires verification: {c.id}: {c.text}")
    return list(dict.fromkeys(gaps))


def validate_market_result(analysis: MarketAnalysis, case: CaseInput, pack: EvidencePack) -> None:
    """Reject broken links, scope escalation and contradictory status tags.

    This checks structure, not semantic truth. R3 must audit each excerpt's
    actual support before an investment decision is finalized.
    """
    if not pack.evidence and (analysis.position != "insufficient_data" or analysis.competitors or analysis.differentiation or analysis.pricing_analogues):
        raise ValueError("Empty evidence requires insufficient_data and no factual competitors")
    claims = {c.id: c for c in analysis.claims}
    if len(claims) != len(analysis.claims):
        raise ValueError("Duplicate claim IDs")
    evidence = {e.id: e for e in pack.evidence}
    for c in analysis.claims:
        if not set(c.evidence_ids) <= evidence.keys():
            raise ValueError(f"Unknown evidence ID in {c.id}")
        if case.scope == "approach" and c.scope == "program":
            raise ValueError("Program claim cannot expand approach scope")
        if c.support_status in ("supported", "contradicted", "mixed") and not c.evidence_ids:
            raise ValueError(f"Evidence required for {c.id}")
        if c.scope == "program" and c.support_status in ("supported", "contradicted", "mixed"):
            if not any(evidence[eid].scope == "program" for eid in c.evidence_ids):
                raise ValueError("Program claim requires program evidence")
    population = analysis.target_population
    if not any((population.description, population.indication, population.eligibility, population.geography, population.access_limitations)) and not population.unknowns:
        raise ValueError("Unknown target population must explain missing data")
    if any((population.description, population.indication, population.eligibility, population.geography, population.access_limitations)) and not population.claim_ids:
        raise ValueError("Target population statements require claim references")
    for item in [population, analysis.access, analysis.commercial_value,
                 *analysis.competitive_coverage.values(), *analysis.pricing_analogues,
                 *analysis.diligence_questions, *analysis.competitors,
                 *analysis.differentiation, *analysis.risks]:
        if not set(item.claim_ids) <= claims.keys():
            raise ValueError("Unknown claim reference")
    if len({r.id for r in analysis.risks}) != len(analysis.risks):
        raise ValueError("Duplicate risk IDs")
    for c in analysis.competitors:
        for tag in ("approved", "clinical_stage", "discontinued"):
            if tag in c.categories and c.development_status != tag:
                raise ValueError("Competitor category conflicts with development status")
        if c.development_status in ("approved", "clinical_stage", "discontinued") and c.development_status not in c.categories:
            raise ValueError("Competitor status must have matching category")
    required_categories = set(Category.__args__)
    if set(analysis.competitive_coverage) != required_categories:
        raise ValueError("Coverage must explain every competitor category")
    for category, finding in analysis.competitive_coverage.items():
        matches = [c for c in analysis.competitors if category in c.categories]
        if finding.status == "documented" and (not finding.claim_ids or not matches):
            raise ValueError("Documented competitor category requires entries and claims")
        if finding.status == "insufficient_data" and not finding.unknowns:
            raise ValueError("Missing competitor coverage requires an explicit gap")
    for competitor in analysis.competitors:
        if not set(competitor.discontinuation_reason_claim_ids) <= claims.keys():
            raise ValueError("Unknown discontinuation reason claim reference")
        if competitor.development_status == "discontinued":
            if competitor.discontinuation_reason is None and not competitor.discontinuation_unknowns:
                raise ValueError("Unknown discontinuation reason must be explicit")
            if competitor.discontinuation_reason is not None and not competitor.discontinuation_reason_claim_ids:
                raise ValueError("Discontinuation reason requires claim references")
        elif competitor.discontinuation_reason is not None or competitor.discontinuation_reason_claim_ids or competitor.discontinuation_unknowns:
            raise ValueError("Discontinuation fields apply only to discontinued programs")
    if not analysis.pricing_analogues and not analysis.pricing_unknowns:
        raise ValueError("Missing pricing analogues requires an explicit gap")
    for analogue in analysis.pricing_analogues:
        if any(getattr(analogue, key) is None for key in ("price_description", "geography", "as_of_date")) and not analogue.unknowns:
            raise ValueError("Incomplete pricing analogue requires explicit unknowns")
        if analogue.as_of_date is not None:
            date.fromisoformat(analogue.as_of_date)
    access = analysis.access
    if any((access.reimbursement, access.prescribing, access.other_access)) and not access.claim_ids:
        raise ValueError("Access statements require claim references")
    if not access.unknowns and not all((access.reimbursement, access.prescribing, access.other_access)):
        raise ValueError("Incomplete access assessment requires explicit unknowns")
    value = analysis.commercial_value
    if value.assessment != "insufficient_data" and not value.claim_ids:
        raise ValueError("Commercial value assessment requires claim references")
    if any((value.unmet_need, value.willingness_to_pay)) and not value.claim_ids:
        raise ValueError("Commercial value statements require claim references")
    if (value.assessment == "insufficient_data" or value.willingness_to_pay is None) and not value.unknowns:
        raise ValueError("Unknown commercial value requires explicit gaps")
    if not pack.evidence and value.assessment != "insufficient_data":
        raise ValueError("Empty evidence cannot establish commercial value")
    names = {c.name for c in analysis.competitors}
    if any(d.comparator not in names for d in analysis.differentiation):
        raise ValueError("Differentiation must reference a listed comparator")


async def analyze_market(case: CaseInput, pack: EvidencePack, ctx: RunContext,
                         *, scenarios: list[MarketScenario] | None = None,
                         clinical: RoleResult | None = None) -> RoleResult:
    """One model call; deterministic validation, calculations and assembly."""
    payload = prepare_market_inputs(case, pack, scenarios, clinical)
    if ctx.model is None or not callable(getattr(ctx.model, "generate_structured", None)):
        raise RuntimeError("R2 model adapter with generate_structured is required")
    raw = await ctx.model.generate_structured(PROMPT_ID, payload, MarketAnalysis, ctx)
    analysis = raw if isinstance(raw, MarketAnalysis) else MarketAnalysis.model_validate(raw)
    validate_market_result(analysis, case, pack)
    calculations = payload["calculated_scenarios"]
    claims = [Claim(**c.model_dump(), provenance="ai") for c in analysis.claims]
    risks = [Risk(**r.model_dump()) for r in analysis.risks]
    gaps = identify_market_gaps(analysis, calculations)
    if clinical is None:
        gaps.append("Clinical eligibility alignment with R4 is pending.")
    limitations = list(dict.fromkeys([*analysis.limitations, *pack.retrieval_warnings,
        "Semantic evidence support requires R3 audit."]))
    sections = [
        {"key": "competitive_landscape", "summary": analysis.summary,
         "claim_ids": [c.id for c in claims], "limitations": limitations,
         "structured_data": {"competitors": classify_competitors(analysis),
                             "differentiation": assess_differentiation(analysis),
                             "coverage": {k: v.model_dump() for k, v in analysis.competitive_coverage.items()},
                             "diligence_questions": [q.model_dump() for q in analysis.diligence_questions]}},
        {"key": "commercial_opportunity", "summary": analysis.commercial_summary,
         "claim_ids": [c.id for c in claims], "limitations": limitations,
         "structured_data": {"target_population": analysis.target_population.model_dump(),
                             "clinical_alignment": payload["clinical_alignment"],
                             "pricing_analogues": [a.model_dump() for a in analysis.pricing_analogues],
                             "pricing_unknowns": analysis.pricing_unknowns,
                             "access": analysis.access.model_dump(),
                             "commercial_value": analysis.commercial_value.model_dump(),
                             "scenarios": calculations,
                             "scenario_ranges": summarize_market_ranges(calculations),
                             "addressable_patients": [{"scenario": r["inputs"]["name"],
                                 "eligible_patients": r["eligible_patients"],
                                 "accessible_patients": r["addressable_patients"],
                                 "geography": r["inputs"]["geography"],
                                 "as_of_date": r["inputs"]["as_of_date"]} for r in calculations],
                             "diligence_questions": [q.model_dump() for q in analysis.diligence_questions],
                             "source_requests": gaps}},
    ]
    # Current R4 test contract has singular section_content. Preserve it rather
    # than editing R2 contracts; expose both canonical sections for integration.
    section = SectionContent(key="competitive_landscape", summary=analysis.summary,
                             claim_ids=[c.id for c in claims], limitations=limitations,
                             structured_data={"sections": sections, "prompt_version": PROMPT_VERSION,
                                              "synthetic": any(s.synthetic for s in pack.sources)})
    return RoleResult(role_id="market", summary=analysis.summary, position=analysis.position,
                      claims=claims, risks=risks, unknowns=gaps,
                      change_conditions=analysis.change_conditions, section_content=section)
