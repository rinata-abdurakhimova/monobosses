"""Clinical subtasks with full scoped inputs and diagnostic request sizes."""
import json

from vic.contracts import RunStage
from vic.llm import request_sizes, structured_request
from vic.prompts import load_prompt


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

    payload = {**base, 'scoped_records': records}
    _, rendered, messages = structured_request(task, payload, model, ctx,
        system_override=system, compact=True)
    sizes = request_sizes(rendered, messages, model=adapter._s.llm_model,
        max_tokens=adapter._s.llm_max_output_tokens,
        reasoning_effort=adapter._reasoning_effort(task))
    ctx.trace.log(RunStage.ANALYZE, f'{task} initial request sizes {sizes}; application_budget=disabled')
    result = await adapter._generate_direct(task, payload, model, ctx,
        compact=True, system_override=system)
    return result.model_dump()
