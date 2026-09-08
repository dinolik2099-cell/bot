"""N9 immutable authorization manifest for a future non-OOS formal run.

This module is metadata-only.  It never imports a market-data reader.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib,json,os,platform,sys,subprocess
from pathlib import Path
from typing import Any, Mapping
from quantbot.backtest.costs import CostModel
from .formal_runner import N7Context
from .canonical_data_adapter import N8DataContext

SCHEMA='quantbot-formal-execution-manifest-n9-v1'
ADAPTER={'module':'quantbot.research.canonical_data_adapter','constructor':'make_n8_canonical_window_loader','reader':'quantbot.data.load.load_symbol_window','source_policy':'canonical_raw_windowed_no_fallback'}
TRUSTED_TREE_POLICY={'clean_required':True,'permitted_known_exception_path_utf8_hex':'646f63732f5175616e74426f745fe680bbe4bd93e5bc80e58f91e4b88ee7a094e7a9b6e5a4a7e7bab25f56322e312e6d64'}
# Git for Windows can expose the pre-existing outline filename through a legacy
# console rendering.  This is an exact, Windows-only compatibility alias, not a
# prefix or glob; every non-matching worktree item still makes preflight fail.
WINDOWS_LEGACY_OUTLINE_PATH_HEX='646f63732f5175616e74426f745fe996b9ee8483ee868ae7bc8de5acaaee87a3e988a7ee8484e5b4a3e98eb4e6bb85e791a2e996bbee86bde6a2bbe988b9e68e93e5be84e8a48fe7bc88e799ac56322e312e6d64'
# First-generation parallel formal execution remains explicitly bounded: 16 is
# large enough to use a half-host budget while preventing accidental 36/72-way
# fanout.  The manifest freezes the resolved value before launch.
TRUSTED_MAX_WORKERS=16
TRUSTED_OUTPUT_PREFIX='data/reports/formal_runs/'
class FormalAuthorizationError(RuntimeError): pass
def _canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'))
def _hash(v):return hashlib.sha256(_canon(v).encode()).hexdigest()
def _module_hash(module):return hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
def trusted_adapter():
 from . import canonical_data_adapter
 data=dict(ADAPTER);data['implementation_hash']=_module_hash(canonical_data_adapter);return data
def _authorized_output_path(repo_root,value):
 root=Path(repo_root).resolve();base=(root/'data'/'reports'/'formal_runs').resolve();candidate=Path(value)
 if candidate.is_absolute(): raise FormalAuthorizationError('output_destination_not_relative')
 resolved=(root/candidate).resolve()
 try: resolved.relative_to(base)
 except ValueError as exc: raise FormalAuthorizationError('output_destination_outside_authorized_namespace') from exc
 return resolved
def repository_state(repo_root):
 root=Path(repo_root)
 def git(*args):return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.STDOUT).decode().strip()
 try:
  commit=git('rev-parse','HEAD');raw=subprocess.check_output(['git','-C',str(root),'status','--porcelain','-z']);raw_items=[part[3:] for part in raw.split(b'\0') if part];items=[part.decode('utf-8','surrogateescape') for part in raw_items]
 except Exception as exc: raise FormalAuthorizationError('repository_state_unavailable') from exc
 permitted={bytes.fromhex(TRUSTED_TREE_POLICY['permitted_known_exception_path_utf8_hex'])}
 if os.name=='nt': permitted.add(bytes.fromhex(WINDOWS_LEGACY_OUTLINE_PATH_HEX))
 unexpected=[item for item in raw_items if item not in permitted]
 return {'commit':commit,'clean':not unexpected,'untracked':items}
def identity_payload(manifest):return {k:manifest[k] for k in ('schema_version','candidate_universe_hash','research_freeze_identity','research_plan_identity','dataset_id','boundary','boundary_identity_hash','train_window','validation_window','oos_status','oos_authorization','engine','cost_model','adapter','symbols','tasks','counts','ranking','top_k_train','viability','source_git_commit','source_tree_policy','worker_config','output')}

def build_manifest(n7:N7Context,n8:N8DataContext,*,source_git_commit:str,worker_config:Mapping[str,Any],output_destination:str,created_at:str)->dict:
 plan=n7.plan
 if n8.n7 is not n7: raise FormalAuthorizationError('n8_context_not_bound_to_n7')
 if not source_git_commit or not output_destination: raise FormalAuthorizationError('manifest_provenance_missing')
 workers=worker_config.get('workers')
 if type(workers) is not int or workers<1: raise FormalAuthorizationError('worker_config_invalid')
 data={'schema_version':SCHEMA,'candidate_universe_hash':plan['candidate_universe_hash'],'research_freeze_identity':plan['research_freeze_identity'],'research_plan_identity':plan['research_plan_identity'],'dataset_id':n8.dataset.dataset_id,'boundary':plan['boundary'],'boundary_identity_hash':plan['boundary_identity_hash'],'train_window':plan['boundary']['train_boundary'],'validation_window':plan['boundary']['validation_boundary'],'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED','engine':{'identity':n7.freeze['protocol_scope']['engine_identity'],'causal_policy':n7.freeze['protocol_scope']['causal_execution_policy']},'cost_model':{'identity':n7.freeze['protocol_scope']['cost_model_identity'],'config':asdict(CostModel())},'adapter':trusted_adapter(),'symbols':list(plan['symbols']),'tasks':list(plan['tasks']),'counts':dict(plan['counts']),'ranking':plan['ranking'],'top_k_train':plan['top_k_train'],'viability':plan['viability'],'source_git_commit':source_git_commit,'source_tree_policy':TRUSTED_TREE_POLICY,'worker_config':dict(worker_config),'output':{'destination':output_destination,'overwrite':False,'mode':'TRAIN_VALIDATION_ONLY'}}
 data['manifest_identity']=_hash(identity_payload(data));data['non_identity_metadata']={'created_at':created_at,'python':sys.version,'platform':platform.platform()};return data

def validate_manifest(manifest:Mapping[str,Any],n7:N7Context,n8:N8DataContext)->bool:
 if manifest.get('schema_version')!=SCHEMA: raise FormalAuthorizationError('manifest_schema_invalid')
 try: payload=identity_payload(manifest)
 except KeyError as exc: raise FormalAuthorizationError('manifest_identity_field_missing') from exc
 if manifest.get('manifest_identity')!=_hash(payload): raise FormalAuthorizationError('manifest_identity_mismatch')
 plan=n7.plan
 for key in ('candidate_universe_hash','research_freeze_identity','research_plan_identity','boundary_identity_hash'):
  if manifest.get(key)!=plan.get(key): raise FormalAuthorizationError('manifest_plan_chain_mismatch')
 if manifest.get('dataset_id')!=n8.dataset.dataset_id or manifest.get('boundary')!=plan['boundary'] or manifest.get('train_window')!=plan['boundary']['train_boundary'] or manifest.get('validation_window')!=plan['boundary']['validation_boundary']: raise FormalAuthorizationError('manifest_boundary_mismatch')
 if manifest.get('symbols')!=list(plan['symbols']) or manifest.get('tasks')!=list(plan['tasks']) or manifest.get('counts')!=dict(plan['counts']): raise FormalAuthorizationError('manifest_task_universe_mismatch')
 if manifest.get('ranking')!=plan['ranking'] or manifest.get('top_k_train')!=plan['top_k_train'] or manifest.get('viability')!=plan['viability']: raise FormalAuthorizationError('manifest_research_rule_mismatch')
 if manifest.get('oos_status')!='SEALED' or manifest.get('oos_authorization')!='NOT_AUTHORIZED': raise FormalAuthorizationError('manifest_oos_violation')
 engine=manifest.get('engine');cost=manifest.get('cost_model')
 if not isinstance(engine,Mapping) or not isinstance(cost,Mapping) or engine.get('identity')!=n7.freeze['protocol_scope']['engine_identity'] or engine.get('causal_policy')!=n7.freeze['protocol_scope']['causal_execution_policy'] or cost.get('identity')!=n7.freeze['protocol_scope']['cost_model_identity'] or cost.get('config')!=asdict(CostModel()) or manifest.get('adapter')!=trusted_adapter(): raise FormalAuthorizationError('manifest_runtime_provenance_mismatch')
 worker_policy=manifest.get('worker_config');output_policy=manifest.get('output')
 if manifest.get('source_tree_policy')!=TRUSTED_TREE_POLICY or not isinstance(worker_policy,Mapping) or not isinstance(output_policy,Mapping) or worker_policy.get('workers',0)>TRUSTED_MAX_WORKERS or not isinstance(output_policy.get('destination'),str) or output_policy.get('overwrite') is not False or output_policy.get('mode')!='TRAIN_VALIDATION_ONLY': raise FormalAuthorizationError('manifest_trusted_policy_mismatch')
 workers=manifest.get('worker_config',{}).get('workers')
 if type(workers) is not int or workers<1: raise FormalAuthorizationError('manifest_worker_config_invalid')
 return True

def preflight_authorize(manifest,n7,n8,*,repo_root,requested_windows,output_path,requested_workers:int):
 """Authorize future execution without touching any market-data loader."""
 validate_manifest(manifest,n7,n8)
 state=repository_state(repo_root)
 if state['commit']!=manifest['source_git_commit']: raise FormalAuthorizationError('source_git_commit_mismatch')
 if not state['clean']: raise FormalAuthorizationError('source_tree_not_clean')
 if not isinstance(requested_windows,Mapping) or set(requested_windows)!={'TRAIN','VALIDATION'} or requested_windows['TRAIN']!=manifest['train_window'] or requested_windows['VALIDATION']!=manifest['validation_window']: raise FormalAuthorizationError('execution_windows_not_authorized')
 if type(requested_workers) is not int or requested_workers<1 or requested_workers>manifest['worker_config']['workers']: raise FormalAuthorizationError('requested_workers_not_authorized')
 destination=_authorized_output_path(repo_root,manifest['output']['destination'])
 target=_authorized_output_path(repo_root,output_path)
 if target!=destination or target.exists(): raise FormalAuthorizationError('output_collision_or_destination_mismatch')
 return {'manifest_identity':manifest['manifest_identity'],'research_plan_identity':manifest['research_plan_identity'],'research_freeze_identity':manifest['research_freeze_identity'],'authorized_windows':requested_windows,'market_data_reads':0}
