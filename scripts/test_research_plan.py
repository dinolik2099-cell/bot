from pathlib import Path
import sys,json,tempfile,subprocess
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.candidate_universe import CURRENT_PROTOCOL_SCOPE,build_candidate_universe
from quantbot.research.research_plan import build_plan,validate_plan,identity_payload,_hash,task_id
from quantbot.research.freeze_manifest import build_freeze_manifest
from quantbot.research.model_registry import register_existing_models
from quantbot.strategies.model_pool import register_model_pool
def main():
 register_existing_models();register_model_pool();e=build_candidate_universe();lock=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text());freeze=build_freeze_manifest(e,CURRENT_PROTOCOL_SCOPE,lock,'base');p=build_plan(e,CURRENT_PROTOCOL_SCOPE,lock,freeze['research_freeze_identity'])
 assert p['counts']['models']==36 and p['counts']['symbols']==6 and p['counts']['model_symbol_cells']==216 and p['oos_authorization']=='NOT_AUTHORIZED';assert len({x['task_identity'] for x in p['tasks']})==216;assert build_plan(e,CURRENT_PROTOCOL_SCOPE,lock,p['research_freeze_identity'])['research_plan_identity']==p['research_plan_identity'];assert validate_plan(p,e,freeze)
 for key in ('schema_version','research_freeze_identity','candidate_universe_hash','research_plan_identity'):
  bad=dict(p);bad[key]='bad'
  if key=='schema_version':
   try:validate_plan(bad)
   except ValueError:pass
   else:raise AssertionError(key)
 bad=json.loads(json.dumps(p));bad['counts']['train_evaluations']+=1
 try:validate_plan(bad)
 except ValueError as x:assert str(x)=='train_evaluations_mismatch'
 else:raise AssertionError('train count')
 bad=json.loads(json.dumps(p));bad['tasks'].append(bad['tasks'][0])
 try:validate_plan(bad)
 except ValueError as x:assert str(x)=='task_count_mismatch'
 else:raise AssertionError('task duplicate')
 bad=json.loads(json.dumps(p));bad['oos_authorization']='AUTHORIZED'
 try:validate_plan(bad)
 except ValueError as x:assert str(x)=='oos_not_authorized'
 else:raise AssertionError('oos')
 def consistent(x): x['research_plan_identity']=_hash(identity_payload(x));return x
 for key,value in (('candidate_universe_hash','x'*64),('research_freeze_identity','y'*64),('protocol_scope',{'x':'y'}),('boundary',{'x':'y'})):
  bad=json.loads(json.dumps(p));bad[key]=value
  if key=='protocol_scope':bad['protocol_scope_hash']=_hash(value)
  if key=='boundary':bad['boundary_identity_hash']=_hash(value)
  try:validate_plan(consistent(bad),e,freeze)
  except ValueError as x:assert str(x).startswith('accepted_')
  else:raise AssertionError(key)
 bad=json.loads(json.dumps(p));bad['tasks'][0]['task_identity']='x'*64
 try:validate_plan(consistent(bad),e)
 except ValueError as x:assert str(x)=='task_identity_mismatch'
 else:raise AssertionError('task identity')
 bad=json.loads(json.dumps(p));bad['tasks'][0]['symbol']='UNKNOWN';bad['tasks'][0]['task_identity']=task_id(p['research_freeze_identity'],bad['tasks'][0]['model_id'],'UNKNOWN',p['models'][0]['parameter_grid_hash'],p['protocol_scope_hash'])
 try:validate_plan(consistent(bad),e)
 except ValueError as x:assert str(x)=='task_cartesian_product_mismatch'
 else:raise AssertionError('unknown symbol')
 for field,value in (('parameter_grid_hash','x'*64),('implementation_module_hash','y'*64),('warmup_bars',999),('family','bad'),('secondary_traits',['bad'])):
  bad=json.loads(json.dumps(p));bad['models'][0][field]=value
  try:validate_plan(consistent(bad),e)
  except ValueError as x:assert str(x) in {'frozen_model_metadata_mismatch','task_identity_mismatch'}
  else:raise AssertionError(field)
 assert build_plan(e,replace(CURRENT_PROTOCOL_SCOPE,timeframe='4h'),lock,p['research_freeze_identity'])['research_plan_identity']!=p['research_plan_identity'];print('RESEARCH_PLAN_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
