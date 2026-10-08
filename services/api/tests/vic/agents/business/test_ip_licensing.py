"""Synthetic offline fixtures; no real patent assertions or provider calls."""
from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from vic.agents.business.ip_licensing import (
    CoverageArea, IPLicensingAnalysis, analyze_ip_licensing,
    prepare_ip_licensing_inputs, validate_ip_licensing_result,
)
from vic.contracts import CaseInput, Evidence, EvidencePack, RoleResult, RunContext, Source


def unknown(message="Not supplied"):
    return dict(value=None, basis="unknown", claim_ids=[], assumptions=[], unknowns=[message])


def documented(value):
    return dict(value=value, basis="documented", claim_ids=["ip_licensing.record"],
                assumptions=[], unknowns=[])


def fixture(full=False):
    case = CaseInput(indication="Synthetic disease", mechanism="Synthetic mechanism", scope="approach")
    pack = EvidencePack(snapshot_id="snapshot-ip", synthetic=True, sources=[Source(
        id="src-ip", title="Synthetic patent and license record", type="synthetic",
        synthetic=True, retrieved_at=datetime(2026, 10, 7, tzinfo=UTC),
        content_hash="sha256:" + "0" * 64)], evidence=[Evidence(
            id="ev-ip", source_id="src-ip", scope="approach", locator="synthetic record",
            excerpt="Synthetic application SYN-001. Applicant A, owner B. Pending in synthetic territory. "
                    "B licenses development to C; transfer requires consent. Production know-how is described.")])
    output = dict(summary="IP evidence incomplete; specialist review needed.", position="insufficient_data",
        claims=[], patents=[], rights_and_licenses=[], licensable_assets=[], licensing_options=[],
        freedom_to_operate=dict(status="unresolved", assessment=unknown("FTO search not done"),
            barriers=[], missing_checks=["Claim-level territorial FTO review"]),
        deal_data_gaps=[dict(topic="Commercial terms", missing_data="Terms unavailable",
            evidence_needed="Authorized agreement or term sheet", impact_on_deal="Cannot evaluate commitments")],
        specialist_questions=[dict(question="Who controls the rights?", why_it_matters="Licensing authority",
            evidence_needed="Chain of title", decision_if_positive="Consider negotiation",
            decision_if_negative="Resolve title before proceeding", claim_ids=[], patent_ids=[], license_ids=[])],
        implications=[], coverage={k:dict(status="insufficient_data",claim_ids=[],unknowns=[f"Missing {k}"])
            for k in CoverageArea.__args__}, risks=[], unknowns=["No complete rights review"],
        change_conditions=["Obtain current rights records"], limitations=["Synthetic illustration only"])
    if full:
        output['position'] = 'potential_barriers'
        output['claims'] = [dict(id="ip_licensing.record", text="Synthetic pending application and restricted license.",
            provenance="source", support_status="supported", evidence_ids=["ev-ip"], assumptions=[],
            scope="approach", importance="major")]
        output['patents'] = [dict(id="ip_patent_one",record_type="application",
            publication_number=documented("SYN-001"), title=unknown(), applicants=documented("A"),
            owners=documented("B"), legal_status=documented("Pending as reported"), status_as_of="2026-10-01",
            protected_subjects=[dict(category="manufacturing",description=documented("Synthetic process described"))],
            territories_and_term=[dict(territory="Synthetic territory",confirmed_expiry_date=None,
                status_as_of="2026-10-01",protection_status="pending",claim_ids=["ip_licensing.record"],
                unknowns=["Expiry not supplied"])], relevance=documented("Potential production relevance"), unknowns=[])]
        output['rights_and_licenses'] = [dict(id="ip_license_one",patent_ids=["ip_patent_one"],
            licensors=documented("B"), licensees=documented("C"), rights_granted=documented("Development"),
            exclusivity=unknown(),territory=unknown(),term=unknown(),field_of_use=unknown(),
            assignment_restrictions=documented("Consent required"),sublicensing_restrictions=unknown(),
            other_restrictions=unknown(),unknowns=["Full agreement unavailable"])]
        output['licensable_assets'] = [dict(id="ip_asset_one",asset_type="manufacturing_process",
            patent_ids=["ip_patent_one"],license_ids=["ip_license_one"],
            description=documented("Synthetic production know-how"),control_of_rights=unknown(),
            licensing_uncertainties=["Confirm authority"])]
        output['licensing_options'] = [dict(id="ip_option_one",format="nonexclusive",asset_ids=["ip_asset_one"],
            rationale=dict(value="Could consider a process license",basis="hypothesis",
                claim_ids=["ip_licensing.option"],assumptions=["If owner authorizes"],unknowns=[]),
            prerequisites=["Verify control"],unknown_terms=["Price unknown"])]
        output['claims'].append(dict(id="ip_licensing.option",text="Process license may be considered.",
            provenance="ai",support_status="unverified",evidence_ids=["ev-ip"],assumptions=["If authorized"],
            scope="approach",importance="minor"))
        output['freedom_to_operate'].update(status="potential_barriers",barriers=[dict(id="ip_barrier_one",
            patent_ids=["ip_patent_one"],license_ids=["ip_license_one"],concern=documented("Transfer consent"),
            affected_activity="transfer",consequence="May delay transaction",next_check="Review consent clause")])
        output['implications']=[dict(finding=documented("Transfer consent"),partnership_impact="Consent may be needed",
            investment_impact="Delay risk; amount unknown",next_check="Review agreement")]
        output['risks']=[dict(id="ip_licensing.transfer",description="Consent may delay a deal",priority="major",
            claim_ids=["ip_licensing.record"],impact="Possible delay",next_check="Review clause")]
        output['coverage']['patents']=dict(status="documented",claim_ids=["ip_licensing.record"],unknowns=[])
    return case, pack, output


def ctx(model=None, **changes):
    values=dict(case_id="case-ip",run_id="run-ip",snapshot_id="snapshot-ip",as_of_date=None,
                mode="evidence_only",model=model)
    return RunContext(**(values|changes))


def adapter(output):
    return type("Adapter", (), {"generate_structured": AsyncMock(return_value=output)})()


@pytest.mark.asyncio
@pytest.mark.parametrize('full', [False, True])
async def test_complete_output_and_single_call(full):
    case,pack,output=fixture(full)
    model=adapter(output)
    result=await analyze_ip_licensing(case,pack,ctx(model))
    model.generate_structured.assert_awaited_once()
    args=model.generate_structured.call_args.args
    assert args[0]=='ip_licensing' and args[2] is IPLicensingAnalysis
    assert RoleResult.model_validate(result.model_dump()).role_id=='ip_licensing'
    data=result.section_content[0].structured_data['ip_licensing']
    for key in ('patents','rights_and_licenses','licensable_assets','licensing_options',
                'freedom_to_operate','deal_data_gaps','specialist_questions','implications','coverage'):
        assert key in data
    assert data['legal_review_required'] and data['synthetic']
    assert data['snapshot_id']=='snapshot-ip'
    assert data['prompt_version']=='1.0.0'
    assert data['evidence_source_links']=={'ev-ip':'src-ip'}
    assert result.unknowns and result.change_conditions
    if full:
        assert data['patents'][0]['territories_and_term'][0]['confirmed_expiry_date'] is None
        assert data['licensing_options'][0]['rationale']['basis']=='hypothesis'
        assert result.risks and len(result.claims)==2
        assert 'Price unknown' in result.unknowns


@pytest.mark.asyncio
async def test_empty_evidence_returns_gaps():
    case,pack,output=fixture()
    pack=pack.model_copy(update={'sources':[],'evidence':[]})
    result=await analyze_ip_licensing(case,pack,ctx(adapter(output)))
    data=result.section_content[0].structured_data['ip_licensing']
    assert result.position=='insufficient_data'
    assert not data['patents'] and not data['licensing_options']
    assert data['freedom_to_operate']['status']=='unresolved'


@pytest.mark.parametrize('defect', [
    'evidence','claim_link','duplicate_claim','scope','program_evidence','silent_unknown',
    'documented_unverified','hypothesis_supported','patent_identifier','silent_patent',
    'territory_link','territory_silent','invalid_date','license_rights','patent_link','asset_link',
    'duplicate_record','coverage_missing','coverage_silent','coverage_false','fto_clear',
    'barrier_status','barrier_missing','deal_gap','questions_missing','risk_owner','extra_price',
])
def test_invalid_results_rejected(defect):
    case,pack,out=fixture(True)
    if defect=='evidence': out['claims'][0]['evidence_ids']=['absent']
    if defect=='claim_link': out['patents'][0]['owners']['claim_ids']=['ip_licensing.absent']
    if defect=='duplicate_claim': out['claims'].append(deepcopy(out['claims'][0]))
    if defect=='scope': out['claims'][0]['scope']='program'
    if defect=='program_evidence':
        case=case.model_copy(update={'scope':'program','program_data':'Synthetic candidate data ' * 4})
        out['claims'][0]['scope']='program'
    if defect=='silent_unknown': out['patents'][0]['title']['unknowns']=[]
    if defect=='documented_unverified': out['claims'][0].update(support_status='unverified',assumptions=['Unconfirmed'])
    if defect=='hypothesis_supported': out['licensing_options'][0]['rationale']['claim_ids']=['ip_licensing.record']
    if defect=='patent_identifier': out['patents'][0]['publication_number']=unknown()
    if defect=='silent_patent': out['patents'][0]['status_as_of']=None
    if defect=='territory_link': out['patents'][0]['territories_and_term'][0]['claim_ids']=[]
    if defect=='territory_silent': out['patents'][0]['territories_and_term'][0]['unknowns']=[]
    if defect=='invalid_date': out['patents'][0]['status_as_of']='2026-99-01'
    if defect=='license_rights': out['rights_and_licenses'][0]['rights_granted']=unknown()
    if defect=='patent_link': out['rights_and_licenses'][0]['patent_ids']=['absent']
    if defect=='asset_link': out['licensing_options'][0]['asset_ids']=['absent']
    if defect=='duplicate_record': out['patents'].append(deepcopy(out['patents'][0]))
    if defect=='coverage_missing': del out['coverage']['patents']
    if defect=='coverage_silent': out['coverage']['deal_data']['unknowns']=[]
    if defect=='coverage_false': out['coverage']['territories_and_term'].update(status='documented',claim_ids=[])
    if defect=='fto_clear': out['freedom_to_operate']['status']='clear'
    if defect=='barrier_status': out['freedom_to_operate']['status']='unresolved'
    if defect=='barrier_missing': out['freedom_to_operate']['barriers']=[]
    if defect=='deal_gap': out['deal_data_gaps']=[]
    if defect=='questions_missing': out['specialist_questions']=[]
    if defect=='risk_owner': out['risks'][0]['id']='market.transfer'
    if defect=='extra_price': out['licensing_options'][0]['upfront_price']=1000000
    with pytest.raises(ValueError):
        validate_ip_licensing_result(IPLicensingAnalysis.model_validate(out),case,pack)


@pytest.mark.parametrize('defect',['source','duplicate','snapshot','upstream_role','upstream_evidence','date'])
def test_input_validation(defect):
    case,pack,_=fixture()
    context=ctx()
    upstream=None
    if defect=='source': pack.evidence[0].source_id='absent'
    if defect=='duplicate': pack.evidence.append(pack.evidence[0])
    if defect=='snapshot': context.snapshot_id='other'
    if defect in ('upstream_role','upstream_evidence'):
        upstream=RoleResult(role_id='market',summary='Synthetic context',position='insufficient_data')
        if defect=='upstream_role': upstream.role_id='clinical'
        else:
            _,_,out=fixture(True)
            from vic.contracts import Claim
            upstream.claims=[Claim.model_validate(out['claims'][0]|{'evidence_ids':['absent']})]
    if defect=='date':
        from datetime import date
        case.as_of_date=date(2026,10,1); context.as_of_date=date(2026,10,2)
    with pytest.raises(ValueError):
        prepare_ip_licensing_inputs(case,pack,context,market=upstream)


@pytest.mark.asyncio
async def test_missing_adapter_and_provider_failure():
    case,pack,out=fixture()
    with pytest.raises(RuntimeError,match='adapter'):
        await analyze_ip_licensing(case,pack,ctx())
    model=adapter(out); model.generate_structured.side_effect=TimeoutError('Synthetic timeout')
    with pytest.raises(TimeoutError):
        await analyze_ip_licensing(case,pack,ctx(model))
    model.generate_structured.assert_awaited_once()


def test_upstream_and_provenance_preserved():
    case,pack,_=fixture()
    pack.retrieval_warnings=['Patent search incomplete']
    context=RoleResult(role_id='market',summary='Synthetic region context',position='insufficient_data',
                       unknowns=['Region unknown'])
    payload=prepare_ip_licensing_inputs(case,pack,ctx(),market=context)
    assert payload['upstream_context']['market']['unknowns']==['Region unknown']
    assert payload['evidence'][0]['excerpt']==pack.evidence[0].excerpt
    assert payload['sources'][0]['content_hash']==pack.sources[0].content_hash
    assert payload['context_availability']=={'science':False,'clinical':False,'market':True}
    assert payload['retrieval_warnings']==['Patent search incomplete']


@pytest.mark.asyncio
async def test_model_instance_and_json_serialization():
    import json
    case,pack,out=fixture(True)
    result=await analyze_ip_licensing(case,pack,ctx(adapter(IPLicensingAnalysis.model_validate(out))))
    serialized=json.loads(result.model_dump_json())
    assert serialized['section_content'][0]['structured_data']['ip_licensing']['patents'][0]['status_as_of']=='2026-10-01'


@pytest.mark.parametrize('status', ['contradicted','mixed','unknown','unverified'])
def test_uncertain_claim_cannot_be_presented_as_documented(status):
    case,pack,out=fixture(True)
    out['claims'][0].update(support_status=status,assumptions=['Requires review'])
    with pytest.raises(ValueError,match='Documented finding'):
        validate_ip_licensing_result(IPLicensingAnalysis.model_validate(out),case,pack)


@pytest.mark.asyncio
async def test_invalid_output_does_not_become_result():
    case,pack,out=fixture(True)
    out['patents'][0]['owners']['claim_ids']=['ip_licensing.missing']
    model=adapter(out)
    with pytest.raises(ValueError,match='Unknown claim'):
        await analyze_ip_licensing(case,pack,ctx(model))
    model.generate_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_uncertainty_warnings_and_claim_status_retained():
    case,pack,out=fixture(True)
    pack.retrieval_warnings=['Incomplete synthetic patent search']
    result=await analyze_ip_licensing(case,pack,ctx(adapter(out)))
    assert 'Incomplete synthetic patent search' in result.section_content[0].limitations
    assert result.claims[1].support_status=='unverified'
    assert result.claims[1].assumptions==['If authorized']
    assert 'Confirm authority' in result.unknowns
    assert 'Expiry not supplied' in result.unknowns


def test_patent_without_known_owner_is_preserved_with_gap():
    case,pack,out=fixture(True)
    out['patents'][0]['owners']=unknown('Current owner needs chain-of-title evidence')
    analysis=IPLicensingAnalysis.model_validate(out)
    validate_ip_licensing_result(analysis,case,pack)
    assert analysis.patents[0].applicants.value=='A'
    assert analysis.patents[0].owners.value is None


@pytest.mark.asyncio
async def test_empty_evidence_rejects_asserted_records():
    case,pack,out=fixture(True)
    pack=pack.model_copy(update={'sources':[],'evidence':[]})
    with pytest.raises(ValueError):
        await analyze_ip_licensing(case,pack,ctx(adapter(out)))
