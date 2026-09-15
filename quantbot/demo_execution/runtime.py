from __future__ import annotations
from pathlib import Path
import time
from datetime import datetime,timezone
from decimal import Decimal
from .core import identity,utc_now,FailClosedError,DemoExecutionError,DemoTransientAPIError
from .signal_reader import ForwardSignalReader
from .ledger import ExecutionLedger
from .persistence import DemoPersistence
from .reconciliation import reconcile
from .risk import is_stale

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
   # A terminal CLOSE normally requires its symbol to be flat.  The sole
   # exception is a remote position uniquely attributable to a different,
   # later, durably FILLED OPEN.  Current symbol membership alone is never
   # sufficient: that would either accept a partial CLOSE or retroactively
   # invalidate a valid later re-entry.
   for row in self.ledger.rows.values():
    current=attributed.get(row['intent'].get('symbol'))
    if row['state']=='FILLED' and row['intent'].get('action')=='CLOSE' and current is not None and not self._later_filled_open(row,current['row']):raise FailClosedError('demo_close_position_not_flat')
   state['attributed_positions']=len(attributed);return state
  except Exception as exc:self.fail_closed=True;self.persistence.append('reconciliation',utc_now()[:10],{'reason':str(exc),'fail_closed':True});raise
 def _filled_at(self,row):
  events=row.get('events')
  if not isinstance(events,list):raise FailClosedError('demo_close_chronology_invalid')
  matches=[event for event in events if isinstance(event,dict) and event.get('state')=='FILLED']
  if len(matches)!=1 or not isinstance(matches[0].get('at'),str):raise FailClosedError('demo_close_chronology_invalid')
  try:
   timestamp=datetime.fromisoformat(matches[0]['at'].replace('Z','+00:00'))
   if timestamp.tzinfo is None:raise ValueError('timezone_required')
   return timestamp.astimezone(timezone.utc)
  except Exception as exc:raise FailClosedError('demo_close_chronology_invalid') from exc
 def _later_filled_open(self,close_row,open_row):
  """Prove that an attributed position was recreated after this CLOSE."""
  if not isinstance(open_row,dict) or open_row.get('state')!='FILLED' or open_row.get('intent',{}).get('action')!='OPEN':return False
  close_identity=close_row.get('execution_intent_identity');open_identity=open_row.get('execution_intent_identity')
  if not isinstance(close_identity,str) or not isinstance(open_identity,str) or open_identity==close_identity:return False
  if open_row.get('signal_identity')==close_row.get('signal_identity') or open_row.get('client_order_id')==close_row.get('client_order_id'):return False
  return self._filled_at(open_row)>self._filled_at(close_row)
 def startup_reconcile(self):
  state=self.reconcile();self.checkpoint((self.persistence.read_checkpoint() or {}).get('last_signal_cursor'),state);return state
 def startup_fail_closed(self,engine,exc):
  """Persist a startup reconciliation failure before serving any signal."""
  cursor=(self.persistence.read_checkpoint() or {}).get('last_signal_cursor')
  self._trip(engine,'startup_reconciliation_failed',error=f'{type(exc).__name__}:{exc}')
  self.checkpoint(cursor);self.persistence.flush()
 def _inherited_position_attribution(self,symbol,side,quantity):
  # A predecessor attribution is only a bridge into this recovery epoch.
  # Once this epoch durably FILLS a CLOSE for the symbol, the bridge is
  # permanently retired; any later exposure must be proven by this epoch.
  for ledger_row in self.ledger.rows.values():
   intent=ledger_row.get('intent',{})
   if ledger_row.get('state')=='FILLED' and not ledger_row.get('dry_run') and intent.get('action')=='CLOSE' and intent.get('symbol')==symbol:return None
  checkpoint=self.persistence.read_checkpoint() or {};recovery=checkpoint.get('recovery')
  if not isinstance(recovery,dict) or recovery.get('predecessor_executed_fills') is not True or recovery.get('old_intents_not_replayed') is not True:return None
  if not isinstance(recovery.get('filled_recovery_authorization_identity'),str) or not isinstance(recovery.get('filled_recovery_authorization_claim_identity'),str):raise FailClosedError('demo_inherited_position_evidence_invalid')
  remote=recovery.get('remote_reconciliation')
  if not isinstance(remote,dict) or remote.get('open_orders')!=0 or not isinstance(remote.get('attributed_positions'),list):raise FailClosedError('demo_inherited_position_evidence_invalid')
  matches=[row for row in remote['attributed_positions'] if isinstance(row,dict) and row.get('symbol')==symbol and row.get('side')==side and Decimal(str(row.get('quantity','0')))==quantity]
  if len(matches)!=1:return None
  row=matches[0]
  if not isinstance(row.get('execution_intent_identity'),str) or not isinstance(row.get('client_order_id'),str):raise FailClosedError('demo_inherited_position_evidence_invalid')
  return {'state':'FILLED','execution_intent_identity':row['execution_intent_identity'],'client_order_id':row['client_order_id'],'signal_identity':None,'quantity':format(quantity,'f'),'inherited_recovery_position':True,'intent':{'action':'OPEN','symbol':symbol,'side':side}}

 def _position_attributions(self,positions):
  attributed={}
  for position in positions:
   amount=Decimal(str(position.get('positionAmt',0)))
   if not amount:continue
   side='LONG' if amount>0 else 'SHORT';quantity=abs(amount);matches=[]
   for row in self.ledger.rows.values():
    intent=row['intent']
    if row['state']=='FILLED' and not row.get('dry_run') and intent.get('action')=='OPEN' and intent['symbol']==position.get('symbol') and intent.get('side')==side and Decimal(str(row.get('quantity','0')))==quantity:matches.append(row)
   if len(matches)>1:raise FailClosedError('demo_position_attribution_ambiguous')
   if len(matches)==1:matched=matches[0]
   else:
    matched=self._inherited_position_attribution(position.get('symbol'),side,quantity)
    if matched is None:raise FailClosedError('demo_position_attribution_ambiguous')
   attributed[position['symbol']]={'row':matched,'quantity':quantity,'side':side,'notional':quantity*Decimal(str(position.get('markPrice',0)))}
  return attributed
 def _lifecycle(self,signal):
  try:positions=self.adapter.positions()
  except DemoTransientAPIError as exc:raise DemoTransientAPIError(str(exc),'lifecycle_positions') from exc
  attributed=self._position_attributions(positions);current=attributed.get(signal['symbol'])
  if current is None:return 'OPEN',None,None
  requested=str(signal['direction']).upper()
  if current['side']==requested:return 'SKIP_SAME_DIRECTION',None,None
  return 'CLOSE',format(current['quantity'],'f'),current['side']
 def _health(self,signal):
  """Build risk inputs from durable ledger and Demo-account evidence only."""
  try:orders=self.adapter.open_orders()
  except DemoTransientAPIError as exc:raise DemoTransientAPIError(str(exc),'health_open_orders') from exc
  try:positions=self.adapter.positions()
  except DemoTransientAPIError as exc:raise DemoTransientAPIError(str(exc),'health_positions') from exc
  attributed=self._position_attributions(positions);unresolved=self.ledger.live_exposure();gross_remote=sum(float(value['notional']) for value in attributed.values())
  gross_ledger=sum(float(row['intent']['notional']) for row in unresolved)
  strategy_ledger=sum(float(value['notional']) for value in attributed.values() if value['row']['intent'].get('model_id')==signal.get('model_id'))+sum(float(row['intent']['notional']) for row in unresolved if row['intent'].get('model_id')==signal.get('model_id'))
  now=datetime.now(timezone.utc);start=now.replace(hour=0,minute=0,second=0,microsecond=0)
  try:income=self.adapter.income_history(int(start.timestamp()*1000),int(now.timestamp()*1000))
  except DemoTransientAPIError as exc:raise DemoTransientAPIError(str(exc),'health_income_history') from exc
  if not isinstance(income,list) or any('income' not in row for row in income):raise FailClosedError('demo_daily_pnl_evidence_invalid')
  return {'open_orders':max(len(orders),len(unresolved)),'gross_exposure':gross_remote+gross_ledger,'strategy_exposure':strategy_ledger,'daily_pnl':sum(float(row['income']) for row in income)}
 def _mode_check(self):
  policy=self.config.get('execution_policy')
  if policy is None:return
  try:remote=self.adapter.position_mode()
  except DemoTransientAPIError as exc:raise DemoTransientAPIError(str(exc),'position_mode') from exc
  actual='HEDGE' if remote.get('dualSidePosition') is True else 'ONE_WAY'
  if actual!=policy['position_mode']:raise FailClosedError('demo_position_mode_mismatch')
 def _trip(self,engine,reason,signal_identity=None,error=None):
  self.fail_closed=True;engine.disable(reason);self.persistence.append('runtime',utc_now()[:10],{'signal_identity':signal_identity,'reason':reason,'error':error,'fail_closed':True})
 def _record_transient(self,cursor,signal_identity,operation,exc):
  self.persistence.append('transient_failures',utc_now()[:10],{'signal_identity':signal_identity,'operation':operation,'error_type':type(exc).__name__,'error':str(exc)})
  self.checkpoint(cursor);self.persistence.flush()
 def consume_once(self,engine,dry_run=True):
  checkpoint=self.persistence.read_checkpoint() or {};cursor=checkpoint.get('last_signal_cursor');processed=0
  if self.fail_closed:
   engine.disable('persisted_fail_closed');return {'processed':0,'cursor':cursor,'fail_closed':True}
  try:discovered=ForwardSignalReader(self.forward_root).discover(cursor,self.epoch_start)
  except Exception as exc:
   self._trip(engine,'forward_signal_integrity',error=str(exc));self.checkpoint(cursor);self.persistence.flush();return {'processed':0,'cursor':cursor,'fail_closed':True}
  active=[]
  for marker,signal in discovered:
   if is_stale(self.config['execution_policy'],signal):
    try:
     existing=engine.ledger.rows.get(signal['signal_identity'])
     result=engine.reject_policy(signal,signal['created_at'][:10],'stale_signal',dry_run=dry_run)
     if result['state']!='REJECTED_POLICY':raise FailClosedError('demo_stale_policy_outcome_not_terminal')
     if existing is None:self.persistence.append('orders',signal['created_at'][:10],{'signal_identity':signal['signal_identity'],'state':result['state'],'client_order_id':result['client_order_id'],'dry_run':dry_run})
     processed+=1;cursor=marker;self.checkpoint(cursor)
    except (FailClosedError,DemoExecutionError) as exc:
     self._trip(engine,type(exc).__name__,signal.get('signal_identity'),str(exc));self.checkpoint(cursor);self.persistence.flush();break
   else:active.append((marker,signal))
  # An entirely stale discovered batch is complete without any venue call.
  # With no signals at all, retain the existing cycle-level safety checks.
  if self.fail_closed or (discovered and not active) or (not discovered and cursor is not None):
   self.persistence.flush();return {'processed':processed,'cursor':cursor,'fail_closed':self.fail_closed}
  try:exchange=self.adapter.exchange_info()
  except DemoTransientAPIError as exc:
   self._record_transient(cursor,None,'exchange_info',exc);return {'processed':processed,'cursor':cursor,'fail_closed':False}
  except Exception as exc:
   self._trip(engine,type(exc).__name__,error=str(exc));self.checkpoint(cursor);self.persistence.flush();return {'processed':processed,'cursor':cursor,'fail_closed':True}
  try:self._mode_check()
  except DemoTransientAPIError as exc:
   self._record_transient(cursor,None,'position_mode',exc);return {'processed':processed,'cursor':cursor,'fail_closed':False}
  except Exception as exc:
   self._trip(engine,type(exc).__name__,error=str(exc));self.checkpoint(cursor);self.persistence.flush();return {'processed':processed,'cursor':cursor,'fail_closed':True}
  for marker,signal in active:
   durable_reconciling=False
   operation='lifecycle_positions'
   try:
    action,close_quantity,close_side=self._lifecycle(signal)
    if action=='OPEN':
     rows=[row for row in exchange.get('symbols',[]) if row.get('symbol')==signal['symbol']]
     if len(rows)!=1 or rows[0].get('status')!='TRADING':result=engine.reject_venue(signal,signal['created_at'][:10],'demo_symbol_not_trading')
     else:
      operation='ticker_price'
      try:ticker=self.adapter.ticker_price(signal['symbol'])
      except DemoTransientAPIError as exc:raise DemoTransientAPIError(str(exc),'ticker_price') from exc
      if not ticker.get('price'):result=engine.reject_venue(signal,signal['created_at'][:10],'demo_market_price_unavailable')
      else:operation='health';result=engine.process(signal,signal['created_at'][:10],dry_run=dry_run,price=float(ticker['price']),filters=_filters(exchange,signal['symbol']),health=self._health(signal),action=action,close_quantity=close_quantity,close_side=close_side)
    else:operation='health';result=engine.process(signal,signal['created_at'][:10],dry_run=dry_run,health=self._health(signal),action=action,close_quantity=close_quantity,close_side=close_side)
    self.persistence.append('orders',signal['created_at'][:10],{'signal_identity':signal['signal_identity'],'state':result['state'],'client_order_id':result['client_order_id'],'dry_run':dry_run});processed+=1
    durable_reconciling=result['state']=='RECONCILING'
    if result['state'] in {'SUBMITTING','RECONCILING','ACKNOWLEDGED','PARTIALLY_FILLED'}:self.reconcile()
   except FailClosedError as exc:
    self._trip(engine,type(exc).__name__,signal.get('signal_identity'),str(exc))
    # A deterministic intent already durably recorded as RECONCILING is safe
    # to resume through reconciliation.  Any earlier failure leaves this
    # marker uncommitted so it cannot be silently skipped.
    if not durable_reconciling:
     self.checkpoint(cursor);self.persistence.flush();break
   except DemoTransientAPIError as exc:
    # A pre-intent adapter failure has no durable execution outcome.  Keep the
    # marker for retry and record the exact failed operation without freezing
    # the entire consumer.
    self._record_transient(cursor,signal.get('signal_identity'),exc.operation or operation,exc);break
   except DemoExecutionError as exc:
    self._trip(engine,type(exc).__name__,signal.get('signal_identity'),str(exc));self.checkpoint(cursor);self.persistence.flush();break
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
