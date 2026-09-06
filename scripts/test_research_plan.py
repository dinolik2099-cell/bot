from pathlib import Path
import sys,json,tempfile,subprocess
from dataclasses import replace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.candidate_universe import CURRENT_PROTOCOL_SCOPE,build_candidate_universe
from quantbot.research.research_plan import build_plan,validate_plan
from quantbot.research.model_registry import register_existing_models
from quantbot.strategies.model_pool import register_model_pool
def main():
 register_existing_models();register_model_pool();e=build_candidate_universe();lock=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text());p=build_plan(e,CURRENT_PROTOCOL_SCOPE,lock,'4e1a66757a152af47dc7ba045ce64e97d1005711c5274c451827b68d07c5d9f1')
 assert p['counts']['models']==36 and p['counts']['symbols']==6 and p['counts']['model_symbol_cells']==216 and p['oos_authorization']=='NOT_AUTHORIZED';assert len({x['task_identity'] for x in p['tasks']})==216;assert build_plan(e,CURRENT_PROTOCOL_SCOPE,lock,p['research_freeze_identity'])['research_plan_identity']==p['research_plan_identity'];assert validate_plan(p)
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
 assert build_plan(e,replace(CURRENT_PROTOCOL_SCOPE,timeframe='4h'),lock,p['research_freeze_identity'])['research_plan_identity']!=p['research_plan_identity'];print('RESEARCH_PLAN_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
