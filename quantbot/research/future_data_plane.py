"""Shared future-runner data-plane primitives; no protected access before authority."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping
from .authorization import AuthorizationEvidence, Capability
from .future_stages import validate_stage_protocol, validate_future_stage_execution_plan
from .artifact_store import seal, validate_seal

class FutureDataPlaneError(RuntimeError): pass
@dataclass(frozen=True)
class FutureRuntimeContext:
 protocol: Mapping[str,Any]; plan: Mapping[str,Any]; input_identity: str
 def authorize(self,evidence:AuthorizationEvidence,capability:Capability)->None:
  validate_stage_protocol(self.protocol,accepted_input_identity=self.input_identity)
  validate_future_stage_execution_plan(self.plan,protocol=self.protocol,accepted_input_identity=self.input_identity)
  if evidence.capability!=capability: raise FutureDataPlaneError('future_capability_mismatch')
  evidence.require()
 def result(self,rows,source_git_commit):
  expected=[r['chunk_identity'] for r in self.plan['chunks']]
  actual=[r.get('chunk_identity') for r in rows]
  if set(actual)!=set(expected) or len(actual)!=len(expected) or any(r.get('status')!='COMPLETED' for r in rows): raise FutureDataPlaneError('future_result_chunks_invalid')
  return seal({'schema_version':'quantbot-future-data-plane-result-v1','protocol_identity':self.protocol['artifact_identity'],'execution_plan_identity':self.plan['artifact_identity'],'input_identity':self.input_identity,'source_git_commit':source_git_commit,'rows':list(rows),'oos_status':'SEALED','oos_authorization':'NOT_AUTHORIZED'})
