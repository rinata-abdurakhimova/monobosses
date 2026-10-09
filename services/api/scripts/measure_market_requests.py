"""Reconstruct main baseline and measure labelled synthetic requests, offline only."""
import argparse
import json
import subprocess
import sys
import types
from pathlib import Path
root=Path(__file__).resolve().parents[3]
parser = argparse.ArgumentParser(description="Offline synthetic Market request sizes; no provider calls")
parser.add_argument("--baseline", default="68ece19479130862cc4ceeb957af3c5326c880f8")
args = parser.parse_args()
sys.path.insert(0,str(root/'services/api/tests/vic/agents/business'))
from test_market import fixture, run_context, scenario
from vic.agents.business import market
from vic.contracts import Claim, RoleResult, SectionContent, Evidence, AuditFinding
from vic.config import Settings
from vic.llm import StructuredLlm, structured_request, request_sizes
# Reconstruct unchanged main's implementation for a synthetic offline baseline.
old=types.ModuleType('vic.agents.business._market_baseline')
old.__package__='vic.agents.business'
old.__file__=str(root/'services/api/src/vic/agents/business/market.py')
sys.modules[old.__name__]=old
exec(compile(subprocess.check_output(['git','show',f'{args.baseline}:services/api/src/vic/agents/business/market.py'],cwd=root,text=True),old.__file__,'exec'),old.__dict__)
settings=Settings(_env_file=None, llm_model='gpt-5-mini', llm_api_key='', llm_provider='placeholder', market_request_max_bytes=18000, llm_max_output_tokens=4096)
# Provider is never invoked; this object supplies identical serialization/config.
adapter=StructuredLlm(None,settings)
rows=[]
for large in (False,True):
    case,pack,_=fixture()
    clinical=None
    if large:
        for n in range(30):
            pack.evidence.append(Evidence(id=f'extra_{n}',source_id='s1',scope='approach',locator=f'page {n}',excerpt='Synthetic background detail. '*35,limitations=['Synthetic; population uncertain']))
        pack.evidence.append(Evidence(id='last_contradiction',source_id='s1',scope='approach',locator='final safety finding',excerpt='Synthetic decisive safety contradiction: comparator not approved.'))
        clinical=RoleResult(role_id='clinical',summary='Synthetic clinical context',position='insufficient_data',
            claims=[Claim(id='clinical.target_population',text='Synthetic adults only',provenance='ai',support_status='supported',evidence_ids=['e1'],scope='approach',importance='major')],
            unknowns=['Clinical eligibility needs review'],
            section_content=[SectionContent(key='clinical_development_plan',summary='Synthetic only',claim_ids=['clinical.target_population'],limitations=['Synthetic'],structured_data={'target_population':'Synthetic adults only','study_sequence':['Synthetic trial planning detail. '*80]})])
    ctx=run_context(adapter)
    previous=old.prepare_market_inputs(case,pack,[scenario()],clinical)
    _,system,messages=structured_request('market',previous,old.MarketAnalysis,ctx)
    before=request_sizes(system,messages,model=settings.llm_model,max_tokens=settings.llm_max_output_tokens)
    payload=market.prepare_market_inputs(case,pack,[scenario()],clinical)
    streams={}
    for task in market.PASS_MODELS:
        child=market._pass_context(ctx,task)
        batches=market.plan_market_batches(payload,clinical,task,child)
        sizes=[adapter.structured_request_size(task,b,market.PASS_MODELS[task],child) for b in batches]
        parts={key:len(json.dumps(batches[0][key],ensure_ascii=False,default=str,separators=(',',':')).encode()) for key in ('clinical_input','evidence','sources','calculated_scenarios')}
        streams[task]={'batches':len(batches),'max_request_bytes':max(s['request_bytes'] for s in sizes),'prompt_bytes':sizes[0]['prompt_bytes'],'schema_bytes':sizes[0]['schema_bytes'],'first_payload_bytes':sizes[0]['payload_bytes'],'first_parts_bytes':parts}
    rows.append({'fixture':'large_32_evidence_plus_clinical' if large else 'small_1_evidence','baseline':before,'split':streams})
result={'baseline_ref':subprocess.check_output(['git','rev-parse',args.baseline],cwd=root,text=True).strip(),'unit':'UTF-8 bytes, NOT tokens','model_for_serialization':'gpt-5-mini (no calls)','configured_budget_bytes':settings.market_request_max_bytes,'initial_budget_bytes':int(settings.market_request_max_bytes*market.INITIAL_BUDGET_FRACTION),'live_verified':False,'fixtures':rows}
print(json.dumps(result,indent=2))
