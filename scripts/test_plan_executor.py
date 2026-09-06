from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from quantbot.research.plan_executor import authorize_window,rank_train,PlanExecutionError
def main():
 try:authorize_window({},'OOS')
 except PlanExecutionError:pass
 else:raise AssertionError('OOS must fail')
 rows=[{'total_return':.1,'max_drawdown':.1,'profit_factor':1,'trades':2,'params':{'a':2}},{'total_return':.1,'max_drawdown':.1,'profit_factor':1,'trades':2,'params':{'a':1}}]
 assert rank_train(rows)[0]['params']['a']==1;print('PLAN_EXECUTOR_SYNTHETIC_TEST_OK')
if __name__=='__main__':main()
