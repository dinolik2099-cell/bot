from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.plan_executor import authorize_window,rank_train,PlanExecutionError,execute_synthetic_cell
from quantbot.research.model_registry import ModelSpec,RegisteredModel
def main():
 try:authorize_window({},'OOS')
 except PlanExecutionError:pass
 else:raise AssertionError('OOS must fail')
 rows=[{'total_return':.1,'max_drawdown':.1,'profit_factor':1,'trades':2,'params':{'a':2}},{'total_return':.1,'max_drawdown':.1,'profit_factor':1,'trades':2,'params':{'a':1}}]
 assert rank_train(rows)[0]['params']['a']==1
 class E: parameter_grid={'x':(1,2,3)}
 def ev(window,entry,task,params): return {'total_return':float(params['x']),'max_drawdown':.1,'profit_factor':1.0,'trades':1}
 out=execute_synthetic_cell(E(),{'task_identity':'t','model_id':'m','symbol':'S'},ev,top_k=2)
 assert len(out['train'])==3 and len(out['validation'])==2 and all(not x['oos_authorized'] for x in out['validation'])
 print('PLAN_EXECUTOR_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
