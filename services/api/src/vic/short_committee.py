"""Concise synthesis of the seven specialists through Investment, without audit calls."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from vic.contracts import CommitteeDecision, DiligenceQuestion, RoleResult, SectionContent
from vic.failures import MalformedModelOutput


class ShortConclusion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    recommendation: Literal['Invest', 'Conditional', 'Do Not Invest']
    rationale: str = Field(min_length=1, max_length=700)
    claim_ids: list[str] = Field(default_factory=list)


async def synthesize_short_committee(case, pack, results, ctx):
    allowed = {'science', 'translation', 'clinical', 'market', 'ip_licensing', 'partnerships', 'investment'}
    results = [r for r in results if r.role_id.value in allowed]
    claims = {c.id: c for r in results for c in r.claims}
    limitation = 'Preliminary assessment without semantic audit, investment threshold or failure-miner review.'
    payload = {'case': case.model_dump(mode='json'),
        'specialists': [r.model_dump(mode='json') for r in results],
        'evidence': [e.model_dump(mode='json') for e in pack.evidence],
        'limitation': limitation}
    if ctx.model is None:
        output = ShortConclusion(recommendation='Conditional',
            rationale='Consider further diligence before committing capital. The available specialist findings remain a preliminary assessment with unresolved evidence gaps.')
    else:
        output = await ctx.model.generate_structured('chair_short', payload, ShortConclusion, ctx)
        output = ShortConclusion.model_validate(output.model_dump() if isinstance(output, BaseModel) else output)
    if not set(output.claim_ids) <= claims.keys():
        raise MalformedModelOutput('Short Chair referenced claims not supplied by the seven specialists')
    unresolved = [c.id for c in claims.values() if c.importance.value == 'critical'
        and c.support_status.value in {'unknown', 'unverified', 'contradicted'}]
    unavailable = [r.role_id.value for r in results if r.position == 'analysis_unavailable']
    if output.recommendation == 'Invest' and (unresolved or unavailable):
        output = output.model_copy(update={'recommendation': 'Conditional',
            'rationale': 'Proceed only after resolving critical evidence gaps or unavailable specialist analyses. '
                'The seven specialist outputs do not yet support a positive investment decision.'})
    gaps = list(dict.fromkeys(gap for r in results for gap in r.unknowns))
    checks = (gaps + [
        'Confirm clinical efficacy and safety applicability.', 'Verify commercial and comparator assumptions.',
        'Check asset rights and licensing restrictions.', 'Validate funding to the next milestone.',
        'Obtain independent evidence review before committing capital.'])[:5]
    questions = [DiligenceQuestion(question='Verify: ' + gap,
        why_it_matters='This may change the preliminary investment decision.',
        evidence_needed='Relevant source documents and subject-matter verification.',
        decision_if_positive='Reassess the conditions for progressing.',
        decision_if_negative='Revise or stop the proposed investment path.') for gap in checks]
    decision = CommitteeDecision(recommendation=output.recommendation, rationale=output.rationale,
        conditions=[limitation, 'Resolve material evidence gaps before committing capital.'], questions=questions)
    chair = RoleResult(role_id='chair', position=output.recommendation, summary=output.rationale,
        unknowns=[limitation], change_conditions=decision.conditions,
        section_content=[SectionContent(key='recommendation', summary=output.rationale,
            claim_ids=output.claim_ids, limitations=[limitation],
            structured_data={'short_committee': True, 'recommendation': output.recommendation})])
    return decision, chair
