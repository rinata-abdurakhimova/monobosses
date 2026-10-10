"""Clinical subtasks with measured input segmentation and bounded AI reviews."""
import json

from pydantic import BaseModel, ConfigDict, Field

from vic.contracts import RunStage
from vic.failures import ProviderError, RunFailure
from vic.llm import request_sizes, structured_request
from vic.prompts import load_prompt


class ContextReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    observations: str = Field(min_length=1, max_length=600)
    gaps_and_conflicts: str = Field(min_length=1, max_length=400)


class CombinedContextReview(ContextReview):
    observations: str = Field(min_length=1, max_length=1000)
    gaps_and_conflicts: str = Field(min_length=1, max_length=1000)


TASKS = {
    'clinical_population': ({'target_population', 'comparator', 'standard_of_care', 'unmet_need'},
        {'clinical.target_population', 'clinical.comparator_choice', 'clinical.standard_of_care', 'clinical.unmet_need'},
        {'translation.patient_benefit'}),
    'clinical_endpoints': ({'clinically_meaningful_outcome', 'primary_endpoint', 'secondary_endpoints', 'biomarker_strategy', 'trial_size'},
        {'clinical.primary_endpoint', 'clinical.secondary_endpoints', 'clinical.biomarker_strategy', 'clinical.trial_size_basis'},
        {'translation.molecular_effect', 'translation.target_engagement', 'translation.biological_response'}),
    'clinical_safety': (set(), {'clinical.safety_requirements'},
        {'translation.human_exposure', 'translation.safe_exposure', 'translation.therapeutic_window',
         'translation.pk_pd_adequacy', 'translation.tissue_penetration'}),
    'clinical_planning': ({'thesis', 'position', 'study_sequence', 'regulatory_context', 'historical_analogues', 'next_milestone'},
        {'clinical.study_sequence', 'clinical.regulatory_precedent', 'clinical.next_milestone'}, set()),
}


def scoped_records(case, pack, science, translation, task):
    """Exact source excerpts; scoped prior claims; critical risks/gaps shared."""
    wanted = TASKS[task][2]
    records = []
    sources = {s.id: s for s in pack.sources}
    for evidence in pack.evidence:
        source = sources.get(evidence.source_id)
        records.append({'kind': 'evidence', 'id': evidence.id, 'source_id': evidence.source_id,
            'scope': evidence.scope.value, 'locator': evidence.locator,
            'source_type': source.type if source else None,
            'published_at': str(source.published_at) if source and source.published_at else None,
            'synthetic': bool(source and source.synthetic),
            'text': evidence.excerpt, 'limitations': evidence.limitations})
    if case.program_data:
        records.append({'kind': 'program_data', 'text': case.program_data})
    for role in (science, translation):
        records.append({'kind': 'upstream_summary', 'role': role.role_id.value,
                        'position': role.position, 'text': role.summary})
        for claim in role.claims:
            if claim.importance.value == 'critical' or claim.id in wanted or (
                    role is science and task == 'clinical_endpoints') or task == 'clinical_planning':
                records.append({'kind': 'upstream_claim', 'id': claim.id,
                    'status': claim.support_status.value, 'importance': claim.importance.value,
                    'scope': claim.scope.value, 'evidence_ids': claim.evidence_ids,
                    'text': claim.text, 'provenance': claim.provenance.value, 'assumptions': claim.assumptions})
        for risk in role.risks:
            # Safety and contradictions cannot be excluded by a lexical filter.
            records.append({'kind': 'upstream_risk', 'id': risk.id, 'priority': risk.priority.value,
                            'claim_ids': risk.claim_ids, 'text': risk.description, 'impact': risk.impact, 'next_check': risk.next_check})
        for field in ('unknowns', 'change_conditions'):
            for text in getattr(role, field):
                records.append({'kind': field, 'role': role.role_id.value, 'text': text})
        for section in role.section_content:
            for text in section.limitations:
                records.append({'kind': 'limitation', 'role': role.role_id.value, 'text': text})
    return records


async def generate_clinical(adapter, case, pack, science, translation, ctx):
    from vic.agents.science.clinical import ClinicalPlanAnalysis, _merge_parts
    parts = []
    for task in TASKS:
        parts.append(await _generate_task(adapter, case, pack, science, translation, ctx, task, parts))
    return ClinicalPlanAnalysis.model_validate(_merge_parts(parts))


async def _generate_task(adapter, case, pack, science, translation, ctx, task, prior_parts):
    from vic.agents.science.clinical import _pass_model
    fields, keys, _ = TASKS[task]
    limit = adapter._s.clinical_request_target_bytes
    reserve = 512
    model = _pass_model(task, fields, keys)
    system = load_prompt(task).text
    records = scoped_records(case, pack, science, translation, task)
    if task == 'clinical_planning':
        records.extend({'kind': 'clinical_subtask_result', 'text': json.dumps(part, ensure_ascii=False)} for part in prior_parts)
    base = {'indication': case.indication, 'mechanism': case.mechanism,
            'modality': case.modality, 'development_stage': case.development_stage,
            'scope': case.scope.value, 'claim_keys': sorted(keys),
            'retrieval_warnings': pack.retrieval_warnings,
            'source_evidence_ids': [e.id for e in pack.evidence]}

    def size(payload, schema=model, instructions=system):
        _, rendered, messages = structured_request(task, payload, schema, ctx,
            system_override=instructions, compact=True)
        return request_sizes(rendered, messages, model=adapter._s.llm_model,
            max_tokens=adapter._s.llm_max_output_tokens,
            reasoning_effort=adapter._reasoning_effort(task))['request_bytes']

    async def call(payload, schema=model, instructions=system):
        measured = size(payload, schema, instructions)
        if measured > limit - reserve:
            raise RunFailure(f'{task}: instructions/schema/metadata exceed Clinical budget with repair reserve',
                             code='clinical_request_budget')
        ctx.trace.log(RunStage.ANALYZE, f'{task} initial request_bytes={measured}; target_bytes={limit}; repair_reserve_bytes={reserve}')
        result = await adapter._generate_direct(task, payload, schema, ctx,
            compact=True, system_override=instructions)
        return result

    payload = {**base, 'scoped_records': records}
    reviewed = False
    if size(payload) <= limit - reserve:
        try:
            result = await call(payload)
        except ProviderError as exc:
            if exc.code != 'provider_context_limit':
                raise
            limit = max(2000, limit // 2)
            reviewed = True
        else:
            return result.model_dump()
    else:
        reviewed = True
    if reviewed:
        instructions = (system + '\nReview the supplied exact input segment ONLY. Do not perform the full task yet. '
            'Preserve numeric qualifiers, evidence/claim IDs, statuses, safety concerns, contradictions and missing data. '
            'Segments may end inside a record; do not infer missing content. This is an AI synopsis, not new evidence. '
            'Return observations <=600 characters and gaps_and_conflicts <=400 characters.')
        text = json.dumps(records, ensure_ascii=False, separators=(',', ':'))
        reviews = []
        offset = 0
        while offset < len(text):
            def segment(end, start=offset, base=base, text=text):
                return {**base, 'segment_start': start, 'segment_end': end,
                        'exact_input_segment': text[start:end]}
            low, high = offset, len(text)
            while low < high:
                mid = (low + high + 1) // 2
                if size(segment(mid), ContextReview, instructions) <= limit - reserve:
                    low = mid
                else:
                    high = mid - 1
            if low == offset:
                raise RunFailure(f'{task}: indivisible case/audit metadata exceeds Clinical budget', code='clinical_request_budget')
            try:
                review = await call(segment(low), ContextReview, instructions)
            except ProviderError as exc:
                if exc.code != 'provider_context_limit' or limit <= 2000:
                    raise
                limit = max(2000, limit // 2)
                continue
            reviews.append({'start': offset, 'end': low, **review.model_dump()})
            offset = low
        # Stable metadata survive AI review verbatim; full canonical inputs remain in RoleResults.
        catalogue = [{k: v for k, v in record.items() if k not in {'text', 'limitations'}}
                     for record in records if 'id' in record]
        payload = {**base, 'record_catalogue': catalogue, 'ai_context_reviews': reviews,
                   'reviewed_characters': offset, 'partial_upstream_projection': True}
        merge_prompt = instructions.replace(
            'observations <=600 characters and gaps_and_conflicts <=400 characters',
            'observations <=1000 characters and gaps_and_conflicts <=1000 characters'
        ) + '\nMerge ALL provided adjacent reviews; preserve their opposing findings and uncertainty.'
        while size(payload) > limit - reserve and len(reviews) > 1:
            merged = []
            for index in range(0, len(reviews), 2):
                group = reviews[index:index + 2]
                if len(group) == 1:
                    merged.extend(group)
                    continue
                note = await call({**base, 'adjacent_reviews': group}, CombinedContextReview, merge_prompt)
                merged.append({'start': group[0]['start'], 'end': group[-1]['end'], **note.model_dump()})
            reviews = merged
            payload['ai_context_reviews'] = reviews
        result = await call(payload)
        result.limitations.append('Clinical used task-scoped AI reviews of all selected input segments; reviews may omit detail. Full upstream results remain available; summaries are not independent evidence.')
        return result.model_dump()
