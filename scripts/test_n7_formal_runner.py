from pathlib import Path
import json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.formal_runner import (N7ExecutionError,authorize_n7_window,load_n7_context,make_n7_window_loader,make_n7_canonical_evaluator,run_n7_plan,build_n7_result,validate_n7_result,write_n7_result)
from quantbot.research.plan_executor import PlanExecutionError
from quantbot.research.authorization_gate import FreezeAuthorizationError

PLAN=ROOT/'docs/handoff/FROZEN_RESEARCH_PLAN_N5.json';FREEZE=ROOT/'docs/handoff/CANDIDATE_UNIVERSE_FREEZE_N3.json';LOCK=json.loads((ROOT/'data/reports/research_boundary_lock.json').read_text())
def clone(value):return json.loads(json.dumps(value))
def rejected(action):
 try:action()
 except (N7ExecutionError,PlanExecutionError,FreezeAuthorizationError,ValueError,FileExistsError):return
 raise AssertionError('unexpectedly accepted')
def evaluator(window,entry,task,params):
 value=float(sum(float(x) for x in params.values()))
 return {'total_return':value,'max_drawdown':.1,'profit_factor':1.0,'trades':1}
def main():
 context=load_n7_context(PLAN,FREEZE,LOCK);calls=[]
 guarded=make_n7_window_loader(context,lambda **kwargs:calls.append(kwargs) or 'synthetic-frame')
 task=context.plan['tasks'][0]
 rejected(lambda:guarded(window='OOS',symbol=task['symbol'],task=task));assert not calls
 assert guarded(window='TRAIN',symbol=task['symbol'],task=task)=='synthetic-frame' and len(calls)==1
 entry=context.entries[0];blocked_loader_calls=[];blocked_loader=lambda **kwargs:blocked_loader_calls.append(kwargs)
 rejected(lambda:make_n7_canonical_evaluator(context,blocked_loader,lambda _:None,lambda:object())('TRAIN',entry,task,{}))
 from quantbot.backtest.engine_v2 import BacktestEngine
 rejected(lambda:make_n7_canonical_evaluator(context,blocked_loader,lambda _:None,lambda:BacktestEngine(1000,cost_model=object()))('TRAIN',entry,task,{}))
 assert not blocked_loader_calls
 # Tampered N3/N5 chains fail before a data interface can be constructed or called.
 with tempfile.TemporaryDirectory() as td:
  root=Path(td);bad_plan=clone(context.plan);bad_plan['research_plan_identity']='x'*64;(root/'plan.json').write_text(json.dumps(bad_plan));rejected(lambda:load_n7_context(root/'plan.json',FREEZE,LOCK))
  bad_freeze=clone(context.freeze);bad_freeze['research_freeze_identity']='x'*64;(root/'freeze.json').write_text(json.dumps(bad_freeze));rejected(lambda:load_n7_context(PLAN,root/'freeze.json',LOCK))
 # N6 plan validation happens before evaluator access for identity/model/grid/task attacks.
 def pre_evaluator_reject(mutator):
  fresh=load_n7_context(PLAN,FREEZE,LOCK);plan=fresh.plan;mutator(plan);before=len(calls);rejected(lambda:run_n7_plan(fresh,evaluator));assert len(calls)==before
 pre_evaluator_reject(lambda p:p['tasks'].pop())
 pre_evaluator_reject(lambda p:p['tasks'].append(clone(p['tasks'][0])))
 pre_evaluator_reject(lambda p:p['tasks'][0].__setitem__('task_identity','z'*64))
 pre_evaluator_reject(lambda p:p['models'][0].__setitem__('implementation_module_hash','z'*64))
 pre_evaluator_reject(lambda p:p['models'][0].__setitem__('parameter_grid_hash','z'*64))
 fresh=load_n7_context(PLAN,FREEZE,LOCK);rejected(lambda:run_n7_plan(fresh,evaluator,engine_identity='wrong'));rejected(lambda:run_n7_plan(fresh,evaluator,cost_model_identity='wrong'))
 # A normal synthetic 216-task execution is deterministic and fully provenance-bound.
 context=load_n7_context(PLAN,FREEZE,LOCK);one=run_n7_plan(context,evaluator);two=run_n7_plan(context,evaluator)
 assert len(one)==216 and one==two
 result=build_n7_result(context,one);assert result['run_status']=='COMPLETE' and validate_n7_result(context,result)
 tampered=clone(result);tampered['outputs'][0]['strategy_function_hash']='x'*64;rejected(lambda:validate_n7_result(context,tampered))
 tampered=clone(result);tampered['outputs'][0]['train'][0]['window']='OOS';rejected(lambda:validate_n7_result(context,tampered))
 tampered=clone(result);tampered['outputs'][0]['validation'][0]['oos_authorized']=True;rejected(lambda:validate_n7_result(context,tampered))
 # A crashed/failed cell remains visible and can only yield PARTIAL, never PASS/COMPLETE.
 def broken(*args):raise RuntimeError('synthetic crash')
 partial=build_n7_result(context,run_n7_plan(context,broken));assert partial['run_status']=='PARTIAL' and validate_n7_result(context,partial)
 partial['run_status']='COMPLETE';rejected(lambda:validate_n7_result(context,partial))
 with tempfile.TemporaryDirectory() as td:
  path=write_n7_result(td,result);assert path.exists();rejected(lambda:write_n7_result(td,result))
 print('N7_FORMAL_RUNNER_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
