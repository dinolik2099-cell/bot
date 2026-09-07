from pathlib import Path
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
from quantbot.research.formal_execution_manifest import build_manifest,validate_manifest,FormalAuthorizationError,identity_payload,_hash
LOCK=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text());PLAN=ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json';FREEZE=ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json'
def clone(v):return json.loads(json.dumps(v))
def main():
 n7=load_n7_context(PLAN,FREEZE,LOCK);n8=load_n8_data_context(n7,ROOT/'data/reports/research_boundary_lock.json')
 with tempfile.TemporaryDirectory() as td:
  out='data/reports/formal_runs/N9_FORMAL_RESULT.json';args=dict(source_git_commit='143ebbab0b657646a8c59d55aad7099b9ea0eaf1',worker_config={'workers':2},output_destination=out)
  one=build_manifest(n7,n8,created_at='2026-09-07T00:00:00+00:00',**args);two=build_manifest(n7,n8,created_at='2026-09-07T01:00:00+00:00',**args);assert one['manifest_identity']==two['manifest_identity'] and validate_manifest(one,n7,n8)
  def reject(fn):
   try:fn()
   except FormalAuthorizationError:return
   raise AssertionError('unexpectedly accepted')
  def semantic_bad(key,value):
   bad=clone(one);bad[key]=value;bad['manifest_identity']=_hash(identity_payload(bad));return bad
  for key in ('candidate_universe_hash','research_freeze_identity','research_plan_identity','dataset_id','boundary_identity_hash','symbols','tasks','counts','ranking','top_k_train','viability','engine','cost_model','adapter','train_window','validation_window','source_tree_policy','worker_config','output','oos_status'):
   reject(lambda b=semantic_bad(key,'bad'):validate_manifest(b,n7,n8))
  bad=clone(one);bad['manifest_identity']='x'*64;reject(lambda:validate_manifest(bad,n7,n8))
  bad=clone(one);bad['schema_version']='unknown';reject(lambda:validate_manifest(bad,n7,n8))
 print('N9_FORMAL_EXECUTION_MANIFEST_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
