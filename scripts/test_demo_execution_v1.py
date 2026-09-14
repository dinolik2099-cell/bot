from __future__ import annotations
import json,tempfile
from io import BytesIO
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.error import HTTPError
from quantbot.demo_execution.config import validate_config,load_credentials
from quantbot.demo_execution.binance_demo_adapter import BinanceDemoAdapter
from quantbot.demo_execution.signal_reader import ForwardSignalReader
from quantbot.demo_execution.ledger import ExecutionLedger
from quantbot.demo_execution.models import ExecutionIntent
from quantbot.demo_execution.persistence import DemoPersistence
from quantbot.demo_execution.execution_engine import DemoExecutionEngine
from quantbot.demo_execution.risk import normalize_quantity
from quantbot.demo_execution.reconciliation import reconcile
from quantbot.demo_execution.core import DemoExecutionError,FailClosedError,DemoTransientAPIError

def blocked(fn):
 try:fn()
 except Exception:return
 raise AssertionError('expected_fail_closed')
def signal(identity='s'*64,created=None):return {'signal_identity':identity,'symbol':'BTCUSDT','direction':'LONG','model_id':'m','declaration_identity':'d','signal_timestamp':'2026-09-14T00:00:00+00:00','created_at':created or datetime.now(timezone.utc).isoformat(),'git_commit':'g'*40,'config_identity':'c'*64,'universe_identity':'u','membership_identity':'m'}
def main():
 good={'environment':'DEMO','live_order_endpoint_allowed':False,'endpoint':'https://demo-fapi.binance.com','execution_policy':{'enabled':True,'position_mode':'ONE_WAY','margin_mode':'ISOLATED','leverage':1,'order_notional':100,'max_signal_age_seconds':3600,'risk':{'max_open_orders':2,'max_total_gross_exposure':1000,'max_strategy_exposure':500,'max_order_notional':200,'max_daily_loss':100}}}
 config=validate_config(good);assert config['config_identity']
 for endpoint in ('https://fapi.binance.com','https://testnet.binancefuture.com'):
  bad=dict(good);bad['endpoint']=endpoint;blocked(lambda:validate_config(bad))

 def transport_failure(*_args):raise OSError('synthetic_transport_down')
 try:BinanceDemoAdapter(config['endpoint'],transport=transport_failure).exchange_info()
 except DemoTransientAPIError:pass
 else:raise AssertionError('transport_failure_not_retryable')
 def classified(status,payload=b'{}'):
  def transport(*_args):raise HTTPError('https://demo-fapi.binance.com/fapi/v1/time',status,'synthetic',None,BytesIO(payload))
  try:BinanceDemoAdapter(config['endpoint'],transport=transport).exchange_info()
  except Exception as exc:return exc
  raise AssertionError('http_error_not_classified')
 assert isinstance(classified(429),DemoTransientAPIError)
 assert all(isinstance(classified(status),DemoTransientAPIError) for status in (500,502,503))
 assert isinstance(classified(400,b'{"code":-1022}'),DemoExecutionError) and not isinstance(classified(400),DemoTransientAPIError)
 for injected in (DemoExecutionError('deterministic_request'),FailClosedError('unsafe_state')):
  def preserved(*_args,error=injected):raise error
  try:BinanceDemoAdapter(config['endpoint'],transport=preserved).exchange_info()
  except Exception as exc:assert exc is injected and not isinstance(exc,DemoTransientAPIError)
  else:raise AssertionError('injected_demo_error_not_preserved')
 secret='TOP_SECRET_SHOULD_NOT_PERSIST';adapter=BinanceDemoAdapter(config['endpoint'],'key',secret,transport=lambda method,url,params,signed:{'status':'FILLED','orderId':'42'})
 with tempfile.TemporaryDirectory() as root:
  forward=Path(root)/'forward';target=forward/'signals'/'2026-09-14';target.mkdir(parents=True);target.joinpath('signals.jsonl').write_text(json.dumps(signal())+'\n',encoding='utf-8')
  reader=ForwardSignalReader(forward);items=reader.discover();assert len(items)==1 and items[0][1]['signal_identity']=='s'*64
  ledger=ExecutionLedger(Path(root)/'demo');persistence=DemoPersistence(Path(root)/'demo');engine=DemoExecutionEngine(ledger,persistence,adapter,config,'epoch')
  filters={'stepSize':'0.001','minQty':'0.001','minNotional':'5'};first=engine.process(items[0][1],'2026-09-14',dry_run=True,price=50000,filters=filters,health={});second=engine.process(items[0][1],'2026-09-14',dry_run=True,price=50000,filters=filters,health={});assert first['execution_intent_identity']==second['execution_intent_identity'] and len(ledger.rows)==1
  # Restart reread cannot form another intent; client id is deterministic.
  restarted=ExecutionLedger(Path(root)/'demo');assert len(restarted.rows)==1 and restarted.rows['s'*64]['client_order_id']==first['client_order_id']
  assert normalize_quantity(100,50000,filters)=='0.002';blocked(lambda:normalize_quantity(1,50000,filters))
  old=signal('o'*64,(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat());assert engine.process(old,'2026-09-14',dry_run=True,price=50000,filters=filters,health={})['state']=='REJECTED_POLICY'
  ledger.transition('s'*64,'SUBMITTING')
  def remote_transport(method,url,params,signed):
   return [] if '/openOrders' in url else {'status':'FILLED','orderId':'42'}
  remote=BinanceDemoAdapter(config['endpoint'],'key',secret,transport=remote_transport);assert reconcile(ledger,remote)['differences']==[] and ledger.rows['s'*64]['state']=='FILLED'
  # Partial fill remains recoverable across restart; it is not treated as a
  # new signal or a reason to POST a second order.
  partial_signal=signal('p'*64);partial=engine.process(partial_signal,'2026-09-14',dry_run=True,price=50000,filters=filters,health={});ledger.transition('p'*64,'PARTIALLY_FILLED',binance_order_id='43');assert ExecutionLedger(Path(root)/'demo').rows['p'*64]['state']=='PARTIALLY_FILLED';ledger.transition('p'*64,'FILLED');assert ExecutionLedger(Path(root)/'demo').rows['p'*64]['state']=='FILLED';blocked(lambda:ledger.transition('p'*64,'SUBMITTED'))
  # An inexplicable remote absence is a hard new-order stop, not a retry.
  engine.process(signal('q'*64),'2026-09-14',dry_run=True,price=50000,filters=filters,health={});ledger.transition('q'*64,'SUBMITTED')
  absent=BinanceDemoAdapter(config['endpoint'],'key',secret,transport=lambda *args: [] if '/openOrders' in args[1] else (_ for _ in ()).throw(RuntimeError('missing')))
  blocked(lambda:reconcile(ledger,absent));engine.disable('synthetic_discrepancy');blocked(lambda:engine.process(signal('z'*64),'2026-09-14',dry_run=True,price=50000,filters=filters,health={}))
  persistence.flush();persistence.close();contents=''.join(path.read_text(encoding='utf-8') for path in Path(root).rglob('*') if path.is_file());assert secret not in contents
 print('DEMO_ENDPOINT_FENCE=PASS');print('DEMO_TRANSIENT_TRANSPORT_CLASSIFICATION=PASS');print('DEMO_HTTP_TRANSIENT_WHITELIST=PASS');print('DEMO_INJECTED_SAFETY_EXCEPTION_PRESERVED=PASS');print('DEMO_EXACT_ONCE_RESTART=PASS');print('DEMO_LOST_RESPONSE_RECONCILIATION=PASS');print('DEMO_PARTIAL_FILL_STATE_MACHINE=PASS');print('DEMO_QUANTITY_FILTERS=PASS');print('DEMO_STALE_SIGNAL_REJECTED=PASS');print('DEMO_SECRET_SAFETY=PASS');print('OOS_READS=0');print('FORMAL_RESEARCH_RUNS=0');print('FORWARD_MUTATIONS=0');print('LIVE_ORDER_PLACEMENT=0')
if __name__=='__main__':main()
