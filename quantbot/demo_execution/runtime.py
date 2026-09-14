from __future__ import annotations
from pathlib import Path
import time
from .core import identity,utc_now,FailClosedError
from .signal_reader import ForwardSignalReader
from .ledger import ExecutionLedger
from .persistence import DemoPersistence
from .reconciliation import reconcile

def _filters(exchange,symbol):
 rows=[row for row in exchange.get('symbols',[]) if row.get('symbol')==symbol]
 if len(rows)!=1:raise FailClosedError('demo_symbol_exchange_info_missing')
 values={row.get('filterType'):row for row in rows[0].get('filters',[])};lot=values.get('LOT_SIZE',{});notional=values.get('MIN_NOTIONAL',values.get('NOTIONAL',{}))
 if not lot.get('stepSize') or not lot.get('minQty') or not (notional.get('notional') or notional.get('minNotional')):raise FailClosedError('demo_symbol_filters_invalid')
 return {'stepSize':lot['stepSize'],'minQty':lot['minQty'],'minNotional':notional.get('notional',notional.get('minNotional'))}

class DemoRuntime:
 def __init__(self,config,root,forward_root,adapter,git_commit):
  self.config,self.root,self.forward_root,self.adapter,self.git_commit=config,Path(root),Path(forward_root),adapter,git_commit;self.persistence=DemoPersistence(root);self.ledger=ExecutionLedger(root);self.fail_closed=False;self.epoch_start=(self.persistence.read_checkpoint() or {}).get('demo_epoch_start',utc_now())
 def checkpoint(self,cursor=None,reconciliation_state=None):
  row={'schema_version':'quantbot-demo-checkpoint-v1','git_commit':self.git_commit,'demo_epoch':self.root.name,'demo_epoch_start':self.epoch_start,'config_identity':self.config['config_identity'],'source_forward_identity':identity({'root':str(self.forward_root)}),'last_signal_cursor':cursor,'orders_seen':len(self.ledger.rows),'fills_seen':sum(row['state']=='FILLED' for row in self.ledger.rows.values()),'reconciliation':reconciliation_state or {},'fail_closed':self.fail_closed,'runtime_health':{'live_order_endpoint_allowed':False}};row['checkpoint_identity']=identity(row);return self.persistence.write_checkpoint(row)
 def reconcile(self):
  try:return reconcile(self.ledger,self.adapter)
  except Exception as exc:self.fail_closed=True;self.persistence.append('reconciliation',utc_now()[:10],{'reason':str(exc),'fail_closed':True});raise
 def startup_reconcile(self):
  state=self.reconcile();self.checkpoint((self.persistence.read_checkpoint() or {}).get('last_signal_cursor'),state);return state
 def _health(self):
  orders=self.adapter.open_orders();positions=self.adapter.positions();gross=sum(abs(float(row.get('positionAmt',0))*float(row.get('markPrice',0))) for row in positions)
  return {'open_orders':len(orders),'gross_exposure':gross,'strategy_exposure':0.0,'daily_pnl':0.0}
 def _mode_check(self):
  policy=self.config.get('execution_policy')
  if policy is None:return
  remote=self.adapter.position_mode();actual='HEDGE' if remote.get('dualSidePosition') is True else 'ONE_WAY'
  if actual!=policy['position_mode']:raise FailClosedError('demo_position_mode_mismatch')
 def _trip(self,engine,reason,signal_identity=None):
  self.fail_closed=True;engine.disable(reason);self.persistence.append('runtime',utc_now()[:10],{'signal_identity':signal_identity,'reason':reason,'fail_closed':True})
 def consume_once(self,engine,dry_run=True):
  checkpoint=self.persistence.read_checkpoint() or {};cursor=checkpoint.get('last_signal_cursor');processed=0
  try:exchange=self.adapter.exchange_info();self._mode_check()
  except Exception as exc:
   self._trip(engine,type(exc).__name__);self.checkpoint(cursor);self.persistence.flush();return {'processed':0,'cursor':cursor,'fail_closed':True}
  for marker,signal in ForwardSignalReader(self.forward_root).discover(cursor,self.epoch_start):
   try:
    price=float(self.adapter.ticker_price(signal['symbol'])['price']);result=engine.process(signal,signal['created_at'][:10],dry_run=dry_run,price=price,filters=_filters(exchange,signal['symbol']),health=self._health())
    self.persistence.append('orders',signal['created_at'][:10],{'signal_identity':signal['signal_identity'],'state':result['state'],'client_order_id':result['client_order_id'],'dry_run':dry_run});processed+=1
    if result['state']=='RECONCILING':self.reconcile()
   except Exception as exc:
    self._trip(engine,type(exc).__name__,signal.get('signal_identity'))
   cursor=marker;self.checkpoint(cursor)
  self.persistence.flush();return {'processed':processed,'cursor':cursor,'fail_closed':self.fail_closed}
 def serve(self,engine,*,dry_run,poll_seconds=15,reconcile_seconds=60,stop=None,sleep=time.sleep,monotonic=time.monotonic):
  """Run the durable consumer until its supervisor requests shutdown.

  A reconciliation failure deliberately does not end this loop: the engine is
  already fail-closed for new orders, while the consumer must continue to
  observe remote state until an operator resolves the discrepancy.
  """
  if poll_seconds <= 0 or reconcile_seconds <= 0:raise ValueError('demo_poll_intervals_must_be_positive')
  stop=stop or (lambda:False);last_reconcile=monotonic();cycles=0
  try:
   while not stop():
    self.consume_once(engine,dry_run=dry_run);cycles+=1
    if monotonic()-last_reconcile>=reconcile_seconds:
     try:self.reconcile()
     except Exception:pass
     last_reconcile=monotonic()
    if not stop():sleep(poll_seconds)
  finally:
   # A graceful supervisor stop never abandons a buffered evidence record.
   self.checkpoint((self.persistence.read_checkpoint() or {}).get('last_signal_cursor'))
   self.persistence.flush();self.persistence.close()
  return {'cycles':cycles,'fail_closed':self.fail_closed}
 def diagnostics(self):
  credentials=bool(self.adapter.api_key and self.adapter.api_secret);out={'environment':self.config['environment'],'endpoint':self.config['endpoint'],'live_allowed':False,'credentials_loaded':credentials,'ledger_state':len(self.ledger.rows),'checkpoint_state':self.persistence.read_checkpoint(),'fail_closed':self.fail_closed}
  if credentials:
   try:out.update({'account_reachable':True,'balance':self.adapter.balance(),'position_mode':self.adapter.position_mode(),'open_orders_count':len(self.adapter.open_orders()),'positions_count':len(self.adapter.positions())})
   except Exception as exc:out.update({'account_reachable':False,'error_type':type(exc).__name__})
  return out
