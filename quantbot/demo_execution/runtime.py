from __future__ import annotations
from pathlib import Path
import time
from datetime import datetime,timezone
from decimal import Decimal
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
  self.config,self.root,self.forward_root,self.adapter,self.git_commit=config,Path(root),Path(forward_root),adapter,git_commit;self.persistence=DemoPersistence(root);self.ledger=ExecutionLedger(root);checkpoint=self.persistence.read_checkpoint() or {};self.fail_closed=bool(checkpoint.get('fail_closed'));self.epoch_start=checkpoint.get('demo_epoch_start',utc_now())
 def checkpoint(self,cursor=None,reconciliation_state=None):
  row={'schema_version':'quantbot-demo-checkpoint-v1','git_commit':self.git_commit,'demo_epoch':self.root.name,'demo_epoch_start':self.epoch_start,'config_identity':self.config['config_identity'],'source_forward_identity':identity({'root':str(self.forward_root)}),'last_signal_cursor':cursor,'orders_seen':len(self.ledger.rows),'fills_seen':sum(row['state']=='FILLED' for row in self.ledger.rows.values()),'reconciliation':reconciliation_state or {},'fail_closed':self.fail_closed,'runtime_health':{'live_order_endpoint_allowed':False}};row['checkpoint_identity']=identity(row);return self.persistence.write_checkpoint(row)
 def reconcile(self):
  try:
   state=reconcile(self.ledger,self.adapter);positions=self.adapter.positions();attributed=self._position_attributions(positions)
   # A terminal close is only trusted once the matching remote position is
   # absent.  This catches partial/late close evidence without re-posting.
   for row in self.ledger.rows.values():
    if row['state']=='FILLED' and row['intent'].get('action')=='CLOSE' and row['intent']['symbol'] in attributed:raise FailClosedError('demo_close_position_not_flat')
   state['attributed_positions']=len(attributed);return state
  except Exception as exc:self.fail_closed=True;self.persistence.append('reconciliation',utc_now()[:10],{'reason':str(exc),'fail_closed':True});raise
 def startup_reconcile(self):
  state=self.reconcile();self.checkpoint((self.persistence.read_checkpoint() or {}).get('last_signal_cursor'),state);return state
 def _position_attributions(self,positions):
  attributed={}
  for position in positions:
   amount=Decimal(str(position.get('positionAmt',0)))
   if not amount:continue
   side='LONG' if amount>0 else 'SHORT';matches=[]
   for row in self.ledger.rows.values():
    intent=row['intent']
    if row['state']=='FILLED' and not row.get('dry_run') and intent.get('action')=='OPEN' and intent['symbol']==position.get('symbol') and intent.get('side')==side and Decimal(str(row.get('quantity','0')))==abs(amount):matches.append(row)
   if len(matches)!=1:raise FailClosedError('demo_position_attribution_ambiguous')
   attributed[position['symbol']]={'row':matches[0],'quantity':abs(amount),'side':side,'notional':abs(amount)*Decimal(str(position.get('markPrice',0)))}
  return attributed
 def _lifecycle(self,signal):
  positions=self.adapter.positions();attributed=self._position_attributions(positions);current=attributed.get(signal['symbol'])
  if current is None:return 'OPEN',None,None
  requested=str(signal['direction']).upper()
  if current['side']==requested:return 'SKIP_SAME_DIRECTION',None,None
  return 'CLOSE',format(current['quantity'],'f'),current['side']
 def _health(self,signal):
  """Build risk inputs from durable ledger and Demo-account evidence only."""
  orders=self.adapter.open_orders();positions=self.adapter.positions()
  attributed=self._position_attributions(positions);unresolved=self.ledger.live_exposure();gross_remote=sum(float(value['notional']) for value in attributed.values())
  gross_ledger=sum(float(row['intent']['notional']) for row in unresolved)
  strategy_ledger=sum(float(value['notional']) for value in attributed.values() if value['row']['intent'].get('model_id')==signal.get('model_id'))+sum(float(row['intent']['notional']) for row in unresolved if row['intent'].get('model_id')==signal.get('model_id'))
  now=datetime.now(timezone.utc);start=now.replace(hour=0,minute=0,second=0,microsecond=0)
  income=self.adapter.income_history(int(start.timestamp()*1000),int(now.timestamp()*1000))
  if not isinstance(income,list) or any('income' not in row for row in income):raise FailClosedError('demo_daily_pnl_evidence_invalid')
  return {'open_orders':max(len(orders),len(unresolved)),'gross_exposure':gross_remote+gross_ledger,'strategy_exposure':strategy_ledger,'daily_pnl':sum(float(row['income']) for row in income)}
 def _mode_check(self):
  policy=self.config.get('execution_policy')
  if policy is None:return
  remote=self.adapter.position_mode();actual='HEDGE' if remote.get('dualSidePosition') is True else 'ONE_WAY'
  if actual!=policy['position_mode']:raise FailClosedError('demo_position_mode_mismatch')
 def _trip(self,engine,reason,signal_identity=None):
  self.fail_closed=True;engine.disable(reason);self.persistence.append('runtime',utc_now()[:10],{'signal_identity':signal_identity,'reason':reason,'fail_closed':True})
 def consume_once(self,engine,dry_run=True):
  checkpoint=self.persistence.read_checkpoint() or {};cursor=checkpoint.get('last_signal_cursor');processed=0
  if self.fail_closed:
   engine.disable('persisted_fail_closed');return {'processed':0,'cursor':cursor,'fail_closed':True}
  try:exchange=self.adapter.exchange_info();self._mode_check()
  except Exception as exc:
   self._trip(engine,type(exc).__name__);self.checkpoint(cursor);self.persistence.flush();return {'processed':0,'cursor':cursor,'fail_closed':True}
  for marker,signal in ForwardSignalReader(self.forward_root).discover(cursor,self.epoch_start):
   durable_reconciling=False
   try:
    action,close_quantity,close_side=self._lifecycle(signal);price=float(self.adapter.ticker_price(signal['symbol'])['price']);result=engine.process(signal,signal['created_at'][:10],dry_run=dry_run,price=price,filters=_filters(exchange,signal['symbol']),health=self._health(signal),action=action,close_quantity=close_quantity,close_side=close_side)
    self.persistence.append('orders',signal['created_at'][:10],{'signal_identity':signal['signal_identity'],'state':result['state'],'client_order_id':result['client_order_id'],'dry_run':dry_run});processed+=1
    durable_reconciling=result['state']=='RECONCILING'
    if durable_reconciling:self.reconcile()
   except Exception as exc:
    self._trip(engine,type(exc).__name__,signal.get('signal_identity'))
    # A deterministic intent already durably recorded as RECONCILING is safe
    # to resume through reconciliation.  Any earlier failure leaves this
    # marker uncommitted so it cannot be silently skipped.
    if not durable_reconciling:
     self.checkpoint(cursor);self.persistence.flush();break
   cursor=marker;self.checkpoint(cursor)
   if self.fail_closed:break
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
