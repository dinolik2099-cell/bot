from pathlib import Path
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
from quantbot.research.formal_execution_manifest import build_manifest,validate_manifest,preflight_authorize,FormalAuthorizationError
LOCK=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text());PLAN=ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json';FREEZE=ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json'
def clone(v):return json.loads(json.dumps(v))
def main():
 n7=load_n7_context(PLAN,FREEZE,LOCK);n8=load_n8_data_context(n7,ROOT/'data/reports/research_boundary_lock.json')
 with tempfile.TemporaryDirectory() as td:
  out=str(Path(td)/'N9_FORMAL_RESULT.json');args=dict(source_git_commit='143ebbab0b657646a8c59d55aad7099b9ea0eaf1',worker_config={'workers':2},output_destination=out)
  one=build_manifest(n7,n8,created_at='2026-09-07T00:00:00+00:00',**args);two=build_manifest(n7,n8,created_at='2026-09-07T01:00:00+00:00',**args);assert one['manifest_identity']==two['manifest_identity'] and validate_manifest(one,n7,n8)
  clean={'clean':True,'untracked':['docs/QuantBot_总体开发与研究大纲_V2.1.md']};assert preflight_authorize(one,n7,n8,current_git_commit=args['source_git_commit'],source_tree=clean,requested_windows=('TRAIN','VALIDATION'),output_path=out,requested_workers=1)['market_data_reads']==0
  def reject(fn):
   try:fn()
   except FormalAuthorizationError:return
   raise AssertionError('unexpectedly accepted')
  for key in ('candidate_universe_hash','research_freeze_identity','research_plan_identity','dataset_id','boundary_identity_hash','symbols','tasks','counts','ranking','top_k_train','viability','engine','cost_model','adapter'):
   bad=clone(one);bad[key]='bad';reject(lambda b=bad:validate_manifest(b,n7,n8))
  bad=clone(one);bad['manifest_identity']='x'*64;reject(lambda:validate_manifest(bad,n7,n8))
  bad=clone(one);bad['schema_version']='unknown';reject(lambda:validate_manifest(bad,n7,n8))
  reject(lambda:preflight_authorize(one,n7,n8,current_git_commit='wrong',source_tree=clean,requested_windows=('TRAIN','VALIDATION'),output_path=out,requested_workers=1))
  reject(lambda:preflight_authorize(one,n7,n8,current_git_commit=args['source_git_commit'],source_tree=clean,requested_windows=('OOS',),output_path=out,requested_workers=1))
  reject(lambda:preflight_authorize(one,n7,n8,current_git_commit=args['source_git_commit'],source_tree=clean,requested_windows=('TRAIN','VALIDATION'),output_path=out,requested_workers=3))
  Path(out).touch();reject(lambda:preflight_authorize(one,n7,n8,current_git_commit=args['source_git_commit'],source_tree=clean,requested_windows=('TRAIN','VALIDATION'),output_path=out,requested_workers=1))
 print('N9_FORMAL_EXECUTION_MANIFEST_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
