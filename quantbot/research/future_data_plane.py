"""Shared future-runner data-plane primitives; no protected access before authority."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from .authorization import AuthorizationEvidence, Capability
from .future_stages import validate_stage_protocol, validate_future_stage_execution_plan
from .artifact_store import seal, validate_seal, write_new_json

class FutureDataPlaneError(RuntimeError): pass
@dataclass(frozen=True)
class FutureRuntimeContext:
 protocol: Mapping[str,Any]; plan: Mapping[str,Any]; input_identity: str
 def validate(self)->None:
  if not isinstance(self.input_identity,str) or len(self.input_identity)!=64: raise FutureDataPlaneError('future_input_identity_invalid')
  validate_stage_protocol(self.protocol,accepted_input_identity=self.input_identity)
  validate_future_stage_execution_plan(self.plan,protocol=self.protocol,accepted_input_identity=self.input_identity)
 def authorize(self,evidence:AuthorizationEvidence,capability:Capability)->None:
  self.validate()
  if evidence.capability!=capability: raise FutureDataPlaneError('future_capability_mismatch')
  evidence.require()
 def result(self,rows:Sequence[Mapping[str,Any]],source_git_commit:str):
  self.validate()
  if not isinstance(source_git_commit,str) or len(source_git_commit)!=40: raise FutureDataPlaneError('future_source_git_commit_invalid')
  expected=[r['chunk_identity'] for r in self.plan['chunks']]
  actual=[r.get('chunk_identity') for r in rows]
  if set(actual)!=set(expected) or len(actual)!=len(expected) or len(set(actual))!=len(actual): raise FutureDataPlaneError('future_result_chunks_invalid')
  normalized=[]
  for row in rows:
   if not isinstance(row,Mapping) or row.get('status')!='COMPLETED' or row.get('window')!='TRAIN_VALIDATION': raise FutureDataPlaneError('future_result_row_status_invalid')
   if row.get('protocol_identity')!=self.protocol['artifact_identity'] or row.get('execution_plan_identity')!=self.plan['artifact_identity'] or row.get('input_identity')!=self.input_identity: raise FutureDataPlaneError('future_result_row_provenance_invalid')
   if not isinstance(row.get('result_identity'),str) or len(row['result_identity'])!=64: raise FutureDataPlaneError('future_result_row_identity_invalid')
   if row.get('oos_status','SEALED')!='SEALED' or row.get('oos_authorization','NOT_AUTHORIZED')!='NOT_AUTHORIZED': raise FutureDataPlaneError('future_result_row_oos_invalid')
   normalized.append(dict(row))
  return seal({'schema_version':'quantbot-future-data-plane-result-v2','protocol_identity':self.protocol['artifact_identity'],'execution_plan_identity':self.plan['artifact_identity'],'input_identity':self.input_identity,'source_git_commit':source_git_commit,'rows':sorted(normalized,key=lambda row:row['chunk_identity']),'counts':{'chunks':len(expected)},'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})

 def validate_result(self,result:Mapping[str,Any])->bool:
  self.validate(); validate_seal(result)
  if result.get('schema_version')!='quantbot-future-data-plane-result-v2': raise FutureDataPlaneError('future_result_schema_invalid')
  if result.get('protocol_identity')!=self.protocol['artifact_identity'] or result.get('execution_plan_identity')!=self.plan['artifact_identity'] or result.get('input_identity')!=self.input_identity: raise FutureDataPlaneError('future_result_binding_invalid')
  if result.get('oos_status')!='SEALED' or result.get('oos_authorization')!='NOT_AUTHORIZED': raise FutureDataPlaneError('future_result_oos_invalid')
  rows=result.get('rows')
  if not isinstance(rows,list) or result.get('counts',{}).get('chunks')!=len(self.plan['chunks']): raise FutureDataPlaneError('future_result_count_invalid')
  rebuilt=self.result(rows,result.get('source_git_commit'))
  if rebuilt.get('artifact_identity')!=result.get('artifact_identity'): raise FutureDataPlaneError('future_result_identity_mismatch')
  return True

 def write_result(self,root:str,result:Mapping[str,Any]):
  self.validate_result(result)
  return write_new_json(root,'FUTURE_DATA_PLANE_RESULT',result)


def make_future_canonical_evaluator(*, runtime: FutureRuntimeContext, evidence: AuthorizationEvidence,
                                    n8_context, raw_root, strategy_resolver, engine_factory):
 """Construct a future-stage evaluator only through the accepted N7/N8 path.

 This constructor has no raw frame-loader or raw evaluator parameter.  It
 first validates the stage protocol/plan and explicit non-OOS authority, then
 binds the stage to N8's physically window-bounded canonical reader and N7's
 BacktestEngine/CostModel checked evaluator.  No loader is called here.
 """
 runtime.authorize(evidence,Capability.TRAIN_VALIDATION)
 from .canonical_data_adapter import make_n8_canonical_window_loader
 from .formal_runner import make_n7_canonical_evaluator
 if runtime.protocol.get('dataset_id')!=n8_context.dataset.dataset_id:
  raise FutureDataPlaneError('future_dataset_identity_mismatch')
 if runtime.protocol.get('boundary_identity_hash')!=n8_context.n7.plan.get('boundary_identity_hash'):
  raise FutureDataPlaneError('future_boundary_identity_mismatch')
 return make_n7_canonical_evaluator(n8_context.n7,make_n8_canonical_window_loader(n8_context,raw_root),strategy_resolver,engine_factory)


def make_future_canonical_window_loader(*, runtime: FutureRuntimeContext, evidence: AuthorizationEvidence,
                                        n8_context, raw_root):
 """Authorize and bind a future metadata stage to N8's exact raw reader."""
 runtime.authorize(evidence,Capability.TRAIN_VALIDATION)
 from .canonical_data_adapter import make_n8_canonical_window_loader
 if runtime.protocol.get('dataset_id')!=n8_context.dataset.dataset_id: raise FutureDataPlaneError('future_dataset_identity_mismatch')
 if runtime.protocol.get('boundary_identity_hash')!=n8_context.n7.plan.get('boundary_identity_hash'): raise FutureDataPlaneError('future_boundary_identity_mismatch')
 return make_n8_canonical_window_loader(n8_context,raw_root)
