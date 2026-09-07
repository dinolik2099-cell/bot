from pathlib import Path
import json,sys,tempfile,subprocess
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import load_n7_context
from quantbot.research.canonical_data_adapter import load_n8_data_context
from quantbot.research.formal_execution_manifest import build_manifest,validate_manifest,preflight_authorize,FormalAuthorizationError,identity_payload,_hash
LOCK=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text());PLAN=ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json';FREEZE=ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json'
def clone(v):return json.loads(json.dumps(v))
def make_clean_repo(path):
 subprocess.check_call(['git','init','-q',str(path)])
 subprocess.check_call(['git','-C',str(path),'config','user.email','n9-test@example.invalid'])
 subprocess.check_call(['git','-C',str(path),'config','user.name','N9 Test'])
 (path/'README').write_text('metadata-only test\n')
 subprocess.check_call(['git','-C',str(path),'add','README'])
 subprocess.check_call(['git','-C',str(path),'commit','-q','-m','test'])
 return subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
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
  repo=Path(td)/'repo';repo.mkdir();commit=make_clean_repo(repo)
  authorized=build_manifest(n7,n8,source_git_commit=commit,worker_config={'workers':2},output_destination=out,created_at='test')
  assert preflight_authorize(authorized,n7,n8,repo_root=repo,requested_windows={'TRAIN':authorized['train_window'],'VALIDATION':authorized['validation_window']},output_path=out,requested_workers=1)['market_data_reads']==0
  wrong_windows={'TRAIN':dict(authorized['train_window'],start='1900-01-01T00:00:00+00:00'),'VALIDATION':authorized['validation_window']}
  reject(lambda:preflight_authorize(authorized,n7,n8,repo_root=repo,requested_windows=wrong_windows,output_path=out,requested_workers=1))
  source_tamper=semantic_bad('source_git_commit','0'*40)
  with patch('quantbot.data.load.load_symbol') as full_reader,patch('quantbot.data.load.load_symbol_window') as window_reader,patch('pandas.read_csv') as csv_reader:
   reject(lambda:preflight_authorize(source_tamper,n7,n8,repo_root=repo,requested_windows={'TRAIN':source_tamper['train_window'],'VALIDATION':source_tamper['validation_window']},output_path=out,requested_workers=1))
   assert not full_reader.called and not window_reader.called and not csv_reader.called
 print('N9_FORMAL_EXECUTION_MANIFEST_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
