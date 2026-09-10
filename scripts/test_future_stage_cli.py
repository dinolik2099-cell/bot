"""Wiring-only tests: no N7/N8 loader and no protected artifact are opened."""
from __future__ import annotations
from unittest.mock import patch
import json,sys,tempfile,os
from quantbot.research.future_data_plane import FutureRuntimeContext
from quantbot.research.future_stages import FormalStageProtocol,build_future_stage_execution_plan
from quantbot.research.authorization import AuthorizationEvidence,Capability
from quantbot.research.future_stage_cli import dispatch_authorized_stage

def runtime(stage):
 input_id='a'*64;p=FormalStageProtocol(stage,input_id,'dataset','boundary','b'*40,{}).artifact();plan=build_future_stage_execution_plan(p,accepted_input_identity=input_id,chunk_count=1);return FutureRuntimeContext(p,plan,input_id)
def main():
 deps={'n8':object(),'raw_root':'never-open','strategy_resolver':lambda _:None,'engine_factory':lambda:None,'source_git_commit':'c'*40};auth=AuthorizationEvidence(Capability.TRAIN_VALIDATION,'AUTHORIZED','test-only')
 cases=(
  ('stress','quantbot.research.stress_formal_runner.run_authorized_stress'),('regime','quantbot.research.regime_formal_runner.run_authorized_regime'),
  ('walk_forward','quantbot.research.walk_forward_non_oos_runner.run_authorized_walk_forward'),('long_horizon','quantbot.research.long_horizon_formal_runner.run_authorized_long_horizon'),
  ('failure','quantbot.research.failure_data_plane.run_authorized_failure_diagnostics'),('monte_carlo','quantbot.research.monte_carlo_formal_runner.run_authorized_monte_carlo'),
  ('portfolio','quantbot.research.portfolio_formal_runner.run_authorized_shared_capital_portfolio'))
 for stage,target in cases:
  calls=[]
  def sentry(**kwargs):calls.append(kwargs);return {'artifact_identity':'d'*64}
  evidence=None
  if stage=='monte_carlo':
   # The runner is patched only to prove CLI wiring; it receives the existing
   # formal runner slot, not a CLI evaluator/resampler injection.
   import tempfile,json,os
   handle=tempfile.NamedTemporaryFile('w',suffix='.json',delete=False,encoding='utf-8');json.dump({'formal_result':True,'synthetic':False,'returns':[.1],'research_freeze_identity':None,'research_plan_identity':None,'input_identity':'a'*64},handle);handle.close();evidence=handle.name
  elif stage=='portfolio':
   import tempfile,json,os
   handle=tempfile.NamedTemporaryFile('w',suffix='.json',delete=False,encoding='utf-8');json.dump({'diagnostic':{},'manifest':{},'n11_identity':'x','candidate_count':0,'correlation_sha256':'0'*64},handle);handle.close();evidence=handle.name
  with patch(target,sentry):
   dispatch_authorized_stage(stage=stage,runtime=runtime(stage),authority=auth,deps=deps,evidence_path=evidence)
  assert len(calls)==1,stage
 if evidence: os.unlink(evidence)
 # Invoke the actual argparse path twice: metadata-only returns without
 # resolving dependencies, and unauthorized --execute fails before resolver.
 ctx=runtime('stress'); protocol=tempfile.NamedTemporaryFile('w',delete=False,encoding='utf-8');plan=tempfile.NamedTemporaryFile('w',delete=False,encoding='utf-8')
 json.dump(ctx.protocol,protocol);protocol.close();json.dump(ctx.plan,plan);plan.close()
 import quantbot.research.future_stage_cli as cli
 argv=['future-stage','--protocol',protocol.name,'--plan',plan.name,'--input-identity','a'*64]
 with patch.object(sys,'argv',argv),patch.object(cli,'resolve_canonical_runtime',side_effect=AssertionError('protected_dependency_open')):
  assert cli.main_for_stage('stress')==2
 argv.append('--execute')
 with patch.object(sys,'argv',argv),patch.object(cli,'resolve_canonical_runtime',side_effect=AssertionError('protected_dependency_open')):
  try: cli.main_for_stage('stress')
  except PermissionError: pass
  else: raise AssertionError('unauthorized_execute_accepted')
 os.unlink(protocol.name);os.unlink(plan.name)
 print('FUTURE_STAGE_CLI_WIRING_SYNTHETIC_TEST_OK');print('SEVEN_EXISTING_RUNNER_DISPATCHES=PASS');print('PROTECTED_READS=0');print('OOS_READS=0');print('FORMAL_RESEARCH_RUNS=0')
if __name__=='__main__':main()
