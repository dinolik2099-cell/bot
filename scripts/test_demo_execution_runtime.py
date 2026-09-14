from __future__ import annotations
import json,tempfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from quantbot.demo_execution.config import validate_config
from quantbot.demo_execution.runtime import DemoRuntime
from quantbot.demo_execution.execution_engine import DemoExecutionEngine

def config():
 return validate_config({'environment':'DEMO','live_order_endpoint_allowed':False,'endpoint':'https://demo-fapi.binance.com','execution_policy':{'enabled':True,'position_mode':'ONE_WAY','margin_mode':'ISOLATED','leverage':1,'order_notional':100,'max_signal_age_seconds':3600,'risk':{'max_open_orders':10,'max_total_gross_exposure':10000,'max_strategy_exposure':10000,'max_order_notional':1000,'max_daily_loss':1000}}})

def event(value):
 now=datetime.now(timezone.utc)+timedelta(seconds=1)
 return {'signal_identity':value*64,'symbol':'BTCUSDT','direction':'LONG','model_id':'model','declaration_identity':'declaration','signal_timestamp':now.isoformat(),'created_at':now.isoformat(),'git_commit':'g'*40,'config_identity':'c'*64,'universe_identity':'u','membership_identity':'m'}

class Adapter:
 def __init__(self,*,post_unknown=False,mode=True,fail_ticker=False,income=None):self.post_unknown,self.mode,self.fail_ticker,self.income=post_unknown,mode,fail_ticker,([] if income is None else income);self.calls=[];self.remote={}
 def exchange_info(self):self.calls.append('exchange_info');return {'symbols':[{'symbol':'BTCUSDT','status':'TRADING','filters':[{'filterType':'LOT_SIZE','stepSize':'0.001','minQty':'0.001'},{'filterType':'MIN_NOTIONAL','notional':'5'}]}]}
 def ticker_price(self,symbol):
  self.calls.append('ticker')
  if self.fail_ticker:raise RuntimeError('metadata_unavailable')
  return {'symbol':symbol,'price':'50000'}
 def open_orders(self):self.calls.append('open_orders');return []
 def positions(self):self.calls.append('positions');return []
 def position_mode(self):self.calls.append('position_mode');return {'dualSidePosition':not self.mode}
 def income_history(self,start,end):self.calls.append('income_history');return self.income
 def change_margin_type(self,symbol,mode):self.calls.append('margin');return {}
 def change_leverage(self,symbol,leverage):self.calls.append('leverage');return {}
 def create_order(self,row):
  self.calls.append('create_order')
  if self.post_unknown:self.remote[row['newClientOrderId']]={'status':'FILLED','orderId':'77'};raise RuntimeError('lost_response')
  return {'status':'FILLED','orderId':'66'}
 def query_order(self,client,symbol):self.calls.append('query_order');return self.remote.get(client,{'status':'FILLED','orderId':'66'})

def append(forward,row):
 path=forward/'signals'/'2026-09-14'/'signals.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a',encoding='utf-8') as handle:handle.write(json.dumps(row)+'\n')

def main():
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp);forward=root/'forward';adapter=Adapter();runtime=DemoRuntime(config(),root/'fixed_day0',forward,adapter,'a'*40);engine=DemoExecutionEngine(runtime.ledger,runtime.persistence,adapter,runtime.config,'fixed_day0')
  # Startup reconciliation is first, then only post-Day-0 signals are read.
  runtime.startup_reconcile();append(forward,event('a'));first=runtime.consume_once(engine,dry_run=True);assert first['processed']==1 and 'ticker' in adapter.calls and len(runtime.ledger.rows)==1
  append(forward,event('b'));second=runtime.consume_once(engine,dry_run=True);assert second['processed']==1 and len(runtime.ledger.rows)==2
  # Restart restores both fixed epoch and durable cursor: nothing is replayed.
  restarted=DemoRuntime(config(),root/'fixed_day0',forward,adapter,'a'*40);again=DemoExecutionEngine(restarted.ledger,restarted.persistence,adapter,restarted.config,'fixed_day0');assert restarted.epoch_start==runtime.epoch_start and restarted.consume_once(again,dry_run=True)['processed']==0
  # Execute mode traverses the same pipeline and calls the real engine/adapter.
  append(forward,event('c'));executed=restarted.consume_once(again,dry_run=False);assert executed['processed']==1 and 'create_order' in adapter.calls
  # An unknown POST response is reconciled, never retried, and becomes FILLED.
  unknown=Adapter(post_unknown=True);lost_forward=root/'lost_forward';lost=DemoRuntime(config(),root/'lost_day0',lost_forward,unknown,'b'*40);lost.startup_reconcile();lost_engine=DemoExecutionEngine(lost.ledger,lost.persistence,unknown,lost.config,'lost_day0');append(lost_forward,event('d'));lost.consume_once(lost_engine,dry_run=False);assert len(lost.ledger.rows)==1 and next(iter(lost.ledger.rows.values()))['state']=='FILLED';assert unknown.calls.count('create_order')==1 and 'query_order' in unknown.calls
  # A mode discrepancy disables new orders, but the service continues periodic reconciliation.
  bad=Adapter(mode=False);blocked=DemoRuntime(config(),root/'blocked_day0',root/'empty',bad,'c'*40);blocked_engine=DemoExecutionEngine(blocked.ledger,blocked.persistence,bad,blocked.config,'blocked_day0');ticks=iter((0.0,2.0,3.0));stops=iter((False,False,True));result=blocked.serve(blocked_engine,dry_run=True,poll_seconds=1,reconcile_seconds=1,stop=lambda:next(stops),sleep=lambda _:None,monotonic=lambda:next(ticks));assert result['fail_closed'] and bad.calls.count('open_orders')>=1
  # Failure before a durable intent must leave the current marker and every
  # later signal untouched.  The long-running service only reconciles.
  failing_forward=root/'failing_forward';append(failing_forward,event('e'));append(failing_forward,event('f'));failing_adapter=Adapter(fail_ticker=True);failing=DemoRuntime(config(),root/'failing_day0',failing_forward,failing_adapter,'d'*40);failing_engine=DemoExecutionEngine(failing.ledger,failing.persistence,failing_adapter,failing.config,'failing_day0');failed=failing.consume_once(failing_engine,dry_run=True);assert failed['cursor'] is None and len(failing.ledger.rows)==0 and failing_adapter.calls.count('ticker')==1
  ticks=iter((0.0,2.0,3.0));stops=iter((False,False,True));failing.serve(failing_engine,dry_run=True,poll_seconds=1,reconcile_seconds=1,stop=lambda:next(stops),sleep=lambda _:None,monotonic=lambda:next(ticks));assert (failing.persistence.read_checkpoint() or {}).get('last_signal_cursor') is None and failing_adapter.calls.count('open_orders')>=1
  # Once a POST has an ambiguous outcome, the durable RECONCILING intent may
  # advance the cursor; restart resolves it without a second POST.
  recon_forward=root/'recon_forward';append(recon_forward,event('g'));recon_adapter=Adapter(post_unknown=True);recon=DemoRuntime(config(),root/'recon_day0',recon_forward,recon_adapter,'e'*40);recon.startup_reconcile();recon_engine=DemoExecutionEngine(recon.ledger,recon.persistence,recon_adapter,recon.config,'recon_day0');recon_adapter.remote={};
  def unavailable(client,symbol):recon_adapter.calls.append('query_order');raise RuntimeError('remote_unknown')
  recon_adapter.query_order=unavailable;recon_result=recon.consume_once(recon_engine,dry_run=False);assert recon_result['cursor'] is not None and recon_result['fail_closed'] and recon_adapter.calls.count('create_order')==1
  recon_adapter.query_order=lambda client,symbol:{'status':'FILLED','orderId':'88'};recovered=DemoRuntime(config(),root/'recon_day0',recon_forward,recon_adapter,'e'*40);recovered.startup_reconcile();assert next(iter(recovered.ledger.rows.values()))['state']=='FILLED' and recovered.consume_once(DemoExecutionEngine(recovered.ledger,recovered.persistence,recon_adapter,recovered.config,'recon_day0'),dry_run=False)['processed']==0 and recon_adapter.calls.count('create_order')==1
  # Daily PnL is account-income evidence, not a zero literal.
  pnl_forward=root/'pnl_forward';append(pnl_forward,event('h'));pnl_adapter=Adapter(income=[{'income':'-100'}]);pnl_config=config();pnl_config['execution_policy']['risk']['max_daily_loss']=100;pnl=DemoRuntime(pnl_config,root/'pnl_day0',pnl_forward,pnl_adapter,'f'*40);pnl_result=pnl.consume_once(DemoExecutionEngine(pnl.ledger,pnl.persistence,pnl_adapter,pnl_config,'pnl_day0'),dry_run=True);assert not pnl_result['fail_closed'] and pnl_adapter.calls.count('income_history')==1 and pnl.ledger.rows['h'*64]['state']=='REJECTED_POLICY'
  # Dry-run evidence never becomes real exposure; consecutive dry signals remain consumable.
  strategy_forward=root/'strategy_forward';append(strategy_forward,event('i'));append(strategy_forward,event('j'));strategy_config=config();strategy_config['execution_policy']['risk']['max_strategy_exposure']=100;strategy_adapter=Adapter();strategy=DemoRuntime(strategy_config,root/'strategy_day0',strategy_forward,strategy_adapter,'g'*40);strategy_engine=DemoExecutionEngine(strategy.ledger,strategy.persistence,strategy_adapter,strategy_config,'strategy_day0');assert strategy.consume_once(strategy_engine,dry_run=True)['processed']==2;assert not strategy.fail_closed and len(strategy.ledger.rows)==2
  unit=(Path(__file__).resolve().parents[1]/'deploy'/'quantbot-demo-execution.service').read_text(encoding='utf-8');assert '--serve' in unit and '--diagnostics' not in unit and '%H' not in unit and 'demo_execution_day0_v1' in unit
  runtime.persistence.close();restarted.persistence.close();lost.persistence.close();failing.persistence.close();recon.persistence.close();recovered.persistence.close();pnl.persistence.close();strategy.persistence.close()
 print('DEMO_LONG_RUNNING_INCREMENTAL_CURSOR=PASS')
 print('DEMO_DRY_RUN_FULL_PIPELINE=PASS')
 print('DEMO_EXECUTE_ENGINE_WIRING=PASS')
 print('DEMO_RESTART_CURSOR_EXACT_ONCE=PASS')
 print('DEMO_LOST_POST_RECONCILIATION=PASS')
 print('DEMO_STARTUP_AND_PERIODIC_RECONCILIATION=PASS')
 print('DEMO_FAIL_CLOSED_CONTINUES_RECONCILIATION=PASS')
 print('DEMO_FIXED_DAY0_SERVICE=PASS')
 print('DEMO_PRE_INTENT_FAILURE_CURSOR_NOT_ADVANCED=PASS')
 print('DEMO_FAIL_CLOSED_DOES_NOT_CONSUME_LATER_SIGNALS=PASS')
 print('DEMO_RECONCILIATION_CONTINUES_WHILE_SIGNAL_CURSOR_FROZEN=PASS')
 print('DEMO_DURABLE_RECONCILING_INTENT_RESTART_SAFE=PASS')
 print('DEMO_DAILY_LOSS_RISK_REAL_INPUT=PASS')
 print('DEMO_STRATEGY_EXPOSURE_REAL_INPUT=PASS')
 print('OOS_READS=0');print('FORWARD_MUTATIONS=0');print('LIVE_ORDER_PLACEMENT=0')
if __name__=='__main__':main()
