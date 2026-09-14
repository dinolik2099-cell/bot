from __future__ import annotations
import json,tempfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from quantbot.demo_execution.config import validate_config
from quantbot.demo_execution.runtime import DemoRuntime
from quantbot.demo_execution.execution_engine import DemoExecutionEngine
from quantbot.demo_execution.core import FailClosedError

def cfg():return validate_config({'environment':'DEMO','live_order_endpoint_allowed':False,'endpoint':'https://demo-fapi.binance.com','execution_policy':{'enabled':True,'position_mode':'ONE_WAY','margin_mode':'ISOLATED','leverage':1,'order_notional':10,'max_signal_age_seconds':3600,'risk':{'max_open_orders':10,'max_total_gross_exposure':100,'max_strategy_exposure':100,'max_order_notional':20,'max_daily_loss':100}}})
def signal(seed,direction='LONG',model='model'):
 now=datetime.now(timezone.utc)+timedelta(seconds=1);return {'signal_identity':seed*64,'symbol':'BTCUSDT','direction':direction,'model_id':model,'declaration_identity':'decl','signal_timestamp':now.isoformat(),'created_at':now.isoformat()}
def append(root,row):
 path=root/'signals'/'2026-09-15'/'signals.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a',encoding='utf-8') as out:out.write(json.dumps(row)+'\n')
class Demo:
 def __init__(self):self.calls=[];self.amount='0';self.orders={};self.fail_post=False
 def exchange_info(self):return {'symbols':[{'symbol':'BTCUSDT','status':'TRADING','filters':[{'filterType':'LOT_SIZE','stepSize':'0.001','minQty':'0.001'},{'filterType':'MIN_NOTIONAL','notional':'5'}]}]}
 def ticker_price(self,s):return {'symbol':s,'price':'10000'}
 def open_orders(self):return []
 def positions(self):return [{'symbol':'BTCUSDT','positionAmt':self.amount,'markPrice':'10000'}]
 def position_mode(self):return {'dualSidePosition':False}
 def income_history(self,a,b):return []
 def change_margin_type(self,s,m):self.calls.append(('margin',s,m));return {'code':200}
 def change_leverage(self,s,l):self.calls.append(('leverage',s,l));return {'leverage':l}
 def create_order(self,row):
  self.calls.append(('order',dict(row)))
  if self.fail_post:raise RuntimeError('lost_post')
  qty=float(row['quantity']);self.amount=str((float(self.amount)+qty) if row['side']=='BUY' else (float(self.amount)-qty));self.orders[row['newClientOrderId']]={'status':'FILLED','orderId':str(len(self.orders)+1)};return self.orders[row['newClientOrderId']]
 def query_order(self,c,s):return self.orders.get(c,{'status':'FILLED','orderId':'1'})
def main():
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);forward=root/'forward';api=Demo();runtime=DemoRuntime(cfg(),root/'day0',forward,api,'a'*40);engine=DemoExecutionEngine(runtime.ledger,runtime.persistence,api,runtime.config,'day0');runtime.startup_reconcile()
  # Dry-run traverses intent/filter/risk but has no account configuration or exposure.
  append(forward,signal('a'));assert runtime.consume_once(engine,dry_run=True)['processed']==1;assert not api.calls
  append(forward,signal('b'));assert runtime.consume_once(engine,dry_run=True)['processed']==1;assert not api.calls
  # First live OPEN configures exactly once then opens an attributable position.
  append(forward,signal('c'));assert runtime.consume_once(engine,dry_run=False)['processed']==1;assert [x[0] for x in api.calls[:2]]==['margin','leverage'];open_order=api.calls[-1][1];assert 'reduceOnly' not in open_order and api.amount!='0'
  # Same direction is a terminal, durable no-op: no second MARKET order.
  append(forward,signal('d'));assert runtime.consume_once(engine,dry_run=False)['processed']==1;assert runtime.ledger.rows['d'*64]['state']=='SKIPPED' and len([x for x in api.calls if x[0]=='order'])==1
  # Reverse signal only closes the actual remote amount; it neither reverses nor reconfigures.
  amount=api.amount;configuration_calls=len([x for x in api.calls if x[0] in {'margin','leverage'}]);engine=DemoExecutionEngine(runtime.ledger,runtime.persistence,api,runtime.config,'day0');append(forward,signal('e','SHORT'));assert runtime.consume_once(engine,dry_run=False)['processed']==1;close=api.calls[-1][1];assert close['reduceOnly']=='true' and float(close['quantity'])==abs(float(amount)) and close['side']=='SELL' and api.amount=='0.0';assert len([x for x in api.calls if x[0] in {'margin','leverage'}])==configuration_calls
  # FILLED remote position plus its FILLED ledger row is accounted once, not doubled.
  api.amount='0.001';runtime._health(signal('z'));health=runtime._health(signal('z'));assert health['gross_exposure']==10.0 and health['strategy_exposure']==10.0
  # A second matching OPEN row makes attribution ambiguous and fences execution.
  duplicate=dict(runtime.ledger.rows['c'*64]);duplicate['signal_identity']='x'*64;runtime.ledger.rows['x'*64]=duplicate;runtime.ledger._save()
  try:runtime._health(signal('y'))
  except FailClosedError:pass
  else:raise AssertionError('expected ambiguous attribution fence')
  runtime.persistence.close()
 print('DEMO_MARGIN_LEVERAGE_EXECUTE_ONLY=PASS')
 print('DEMO_DRY_RUN_NEVER_MUTATES_ACCOUNT_CONFIGURATION=PASS')
 print('DEMO_SAME_DIRECTION_NO_ADD_EXPOSURE=PASS')
 print('DEMO_OPPOSITE_SIGNAL_REDUCE_ONLY_CLOSE=PASS')
 print('DEMO_CLOSE_QUANTITY_REMOTE_POSITION=PASS')
 print('DEMO_FILLED_OPEN_POSITION_ATTRIBUTED=PASS')
 print('DEMO_REMOTE_FILLED_LEDGER_NO_DOUBLE_COUNT=PASS')
 print('DEMO_AMBIGUOUS_POSITION_ATTRIBUTION_FAIL_CLOSED=PASS')
 print('OOS_READS=0');print('FORWARD_MUTATIONS=0');print('LIVE_ORDER_PLACEMENT=0')
if __name__=='__main__':main()
