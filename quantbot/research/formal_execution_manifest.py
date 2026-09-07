"""N9 immutable authorization manifest for a future non-OOS formal run.

This module is metadata-only.  It never imports a market-data reader.
"""
from __future__ import annotations
from dataclasses import asdict
import hashlib,json,platform,sys
from pathlib import Path
from typing import Any, Mapping
from quantbot.backtest.costs import CostModel
from .formal_runner import N7Context
from .canonical_data_adapter import N8DataContext

SCHEMA='quantbot-formal-execution-manifest-n9-v1'
ADAPTER={'module':'quantbot.research.canonical_data_adapter','constructor':'make_n8_canonical_window_loader','reader':'quantbot.data.load.load_symbol_window','source_policy':'canonical_raw_windowed_no_fallback'}
class FormalAuthorizationError(RuntimeError): pass
def _canon(v):return json.dumps(v,sort_keys=True,separators=(',',':'))
def _hash(v):return hashlib.sha256(_canon(v).encode()).hexdigest()
def identity_payload(manifest):return {k:manifest[k] for k in ('schema_version','candidate_universe_hash','research_freeze_identity','research_plan_identity','dataset_id','boundary','boundary_identity_hash','train_window','validation_window','oos_status','oos_authorization','engine','cost_model','adapter','symbols','tasks','counts','ranking','top_k_train','viability','source_git_commit','source_tree_policy','worker_config','output')}

def build_manifest(n7:N7Context,n8:N8DataContext,*,source_git_commit:str,worker_config:Mapping[str,Any],output_destination:str,created_at:str)->dict:
 plan=n7.plan
 if n8.n7 is not n7: raise FormalAuthorizationError('n8_context_not_bound_to_n7')
 if not source_git_commit or not output_destination: raise FormalAuthorizationError('manifest_provenance_missing')
 workers=worker_config.get('workers')
 if type(workers) is not int or workers<1: raise FormalAuthorizationError('worker_config_invalid')
 data={'schema_version':SCHEMA,'candidate_universe_hash':plan['candidate_universe_hash'],'research_freeze_identity':plan['research_freeze_identity'],'research_plan_identity':plan['research_plan_identity'],'dataset_id':n8.dataset.dataset_id,'boundary':plan['boundary'],'boundary_identity_hash':plan['boundary_identity_hash'],'train_window':plan['boundary']['train_boundary'],'validation_window':plan['boundary']['validation_boundary'],'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED','engine':{'identity':n7.freeze['protocol_scope']['engine_identity'],'causal_policy':n7.freeze['protocol_scope']['causal_execution_policy']},'cost_model':{'identity':n7.freeze['protocol_scope']['cost_model_identity'],'config':asdict(CostModel())},'adapter':ADAPTER,'symbols':list(plan['symbols']),'tasks':list(plan['tasks']),'counts':dict(plan['counts']),'ranking':plan['ranking'],'top_k_train':plan['top_k_train'],'viability':plan['viability'],'source_git_commit':source_git_commit,'source_tree_policy':{'clean_required':True,'permitted_known_exceptions':['docs/QuantBot_总体开发与研究大纲_V2.1.md']},'worker_config':dict(worker_config),'output':{'destination':output_destination,'overwrite':False,'mode':'TRAIN_VALIDATION_ONLY'}}
 data['manifest_identity']=_hash(identity_payload(data));data['non_identity_metadata']={'created_at':created_at,'python':sys.version,'platform':platform.platform()};return data

def validate_manifest(manifest:Mapping[str,Any],n7:N7Context,n8:N8DataContext)->bool:
 if manifest.get('schema_version')!=SCHEMA: raise FormalAuthorizationError('manifest_schema_invalid')
 try: payload=identity_payload(manifest)
 except KeyError as exc: raise FormalAuthorizationError('manifest_identity_field_missing') from exc
 if manifest.get('manifest_identity')!=_hash(payload): raise FormalAuthorizationError('manifest_identity_mismatch')
 plan=n7.plan
 for key in ('candidate_universe_hash','research_freeze_identity','research_plan_identity','boundary_identity_hash'):
  if manifest.get(key)!=plan.get(key): raise FormalAuthorizationError('manifest_plan_chain_mismatch')
 if manifest.get('dataset_id')!=n8.dataset.dataset_id or manifest.get('boundary')!=plan['boundary']: raise FormalAuthorizationError('manifest_boundary_mismatch')
 if manifest.get('symbols')!=list(plan['symbols']) or manifest.get('tasks')!=list(plan['tasks']) or manifest.get('counts')!=dict(plan['counts']): raise FormalAuthorizationError('manifest_task_universe_mismatch')
 if manifest.get('ranking')!=plan['ranking'] or manifest.get('top_k_train')!=plan['top_k_train'] or manifest.get('viability')!=plan['viability']: raise FormalAuthorizationError('manifest_research_rule_mismatch')
 if manifest.get('oos_status')!='SEALED' or manifest.get('oos_authorization')!='NOT_AUTHORIZED': raise FormalAuthorizationError('manifest_oos_violation')
 if manifest.get('engine',{}).get('identity')!=n7.freeze['protocol_scope']['engine_identity'] or manifest.get('cost_model',{}).get('identity')!=n7.freeze['protocol_scope']['cost_model_identity'] or manifest.get('cost_model',{}).get('config')!=asdict(CostModel()) or manifest.get('adapter')!=ADAPTER: raise FormalAuthorizationError('manifest_runtime_provenance_mismatch')
 workers=manifest.get('worker_config',{}).get('workers')
 if type(workers) is not int or workers<1: raise FormalAuthorizationError('manifest_worker_config_invalid')
 return True

def preflight_authorize(manifest,n7,n8,*,current_git_commit:str,source_tree:Mapping[str,Any],requested_windows,output_path,requested_workers:int):
 """Authorize future execution without touching any market-data loader."""
 validate_manifest(manifest,n7,n8)
 if current_git_commit!=manifest['source_git_commit']: raise FormalAuthorizationError('source_git_commit_mismatch')
 if not source_tree.get('clean') or set(source_tree.get('untracked',()))-set(manifest['source_tree_policy']['permitted_known_exceptions']): raise FormalAuthorizationError('source_tree_not_clean')
 if requested_windows!=('TRAIN','VALIDATION'): raise FormalAuthorizationError('execution_windows_not_authorized')
 if type(requested_workers) is not int or requested_workers<1 or requested_workers>manifest['worker_config']['workers']: raise FormalAuthorizationError('requested_workers_not_authorized')
 target=Path(output_path)
 if str(target)!=manifest['output']['destination'] or target.exists(): raise FormalAuthorizationError('output_collision_or_destination_mismatch')
 return {'manifest_identity':manifest['manifest_identity'],'research_plan_identity':manifest['research_plan_identity'],'research_freeze_identity':manifest['research_freeze_identity'],'authorized_windows':requested_windows,'market_data_reads':0}
