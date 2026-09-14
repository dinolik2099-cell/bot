from __future__ import annotations
from .models import ExecutionIntent,OrderState
from .risk import check_risk,normalize_quantity
from .core import FailClosedError,DemoRiskRejected

class DemoExecutionEngine:
 def __init__(self,ledger,persistence,adapter,config,epoch):self.ledger,self.persistence,self.adapter,self.config,self.epoch=ledger,persistence,adapter,config,epoch;self.fail_closed=False;self._configured_symbols=set()
 def disable(self,reason):self.fail_closed=True;return reason
 def reject_venue(self,signal,date,reason):
  intent=ExecutionIntent.from_signal(signal,self.config['execution_policy']['order_notional'],'OPEN');row,created=self.ledger.create(intent)
  if not created:
   # A pre-POST VALIDATED OPEN has no remote execution ambiguity and may be
   # conclusively rejected by the current Demo venue.  Later states are
   # evidence-bearing and must remain under reconciliation control.
   if row['state']=='VALIDATED':return self.ledger.transition(intent.signal_identity,OrderState.REJECTED_VENUE.value,reason=reason)
   return row
  self.persistence.append('venue_rejections',date,{'signal_identity':intent.signal_identity,'reason':reason,'demo_epoch':self.epoch});return self.ledger.transition(intent.signal_identity,OrderState.REJECTED_VENUE.value,reason=reason)
 def reject_policy(self,signal,date,reason='stale_signal',dry_run=True):
  """Create a durable terminal policy outcome without venue/API access."""
  policy=self.config.get('execution_policy')
  if policy is None:raise FailClosedError('demo_execution_policy_missing')
  intent=ExecutionIntent.from_signal(signal,policy['order_notional'],'OPEN');row,created=self.ledger.create(intent)
  if not created:return row
  self.persistence.append('signals',date,{'signal':signal,'demo_epoch':self.epoch,'execution_intent_identity':intent.intent_identity})
  self.persistence.append('policy_rejections',date,{'signal_identity':intent.signal_identity,'execution_intent_identity':intent.intent_identity,'reason':reason,'demo_epoch':self.epoch})
  return self.ledger.transition(intent.signal_identity,OrderState.REJECTED_POLICY.value,reason=reason,dry_run=bool(dry_run))
 def _configure_symbol(self,symbol,dry_run):
  if dry_run or symbol in self._configured_symbols:return
  policy=self.config['execution_policy']
  try:self.adapter.change_margin_type(symbol,policy['margin_mode'])
  except Exception as exc:
   # Binance returns a deterministic already-configured error.  It is safe to
   # treat only that explicit condition as success; every other failure fences
   # the following order POST.
   if 'no need to change margin type' not in str(exc).lower() and 'already' not in str(exc).lower():raise FailClosedError('demo_margin_mode_setup_failed') from exc
  try:self.adapter.change_leverage(symbol,policy['leverage'])
  except Exception as exc:raise FailClosedError('demo_leverage_setup_failed') from exc
  self.persistence.append('account_configuration',__import__('datetime').datetime.now(__import__('datetime').timezone.utc).date().isoformat(),{'symbol':symbol,'margin_mode':policy['margin_mode'],'leverage':policy['leverage'],'demo_epoch':self.epoch})
  self._configured_symbols.add(symbol)
 def process(self,signal,date,*,dry_run=True,price=None,filters=None,health=None,action='OPEN',close_quantity=None,close_side=None):
  if self.fail_closed:raise FailClosedError('demo_new_orders_disabled')
  policy=self.config.get('execution_policy')
  if policy is None:raise FailClosedError('demo_execution_policy_missing')
  intent=ExecutionIntent.from_signal(signal,policy['order_notional'],action);row,created=self.ledger.create(intent)
  if not created:
   if row['state'] in {item.value for item in __import__('quantbot.demo_execution.models',fromlist=['TERMINAL']).TERMINAL}:return row
   if row['state']!='VALIDATED':return row
   if dry_run:return row
   if intent.action=='CLOSE':
    expected_side='SHORT' if intent.side=='LONG' else 'LONG'
    if not close_quantity or close_side!=expected_side:raise FailClosedError('demo_validated_close_position_changed')
    quantity=str(close_quantity);order_side='BUY' if close_side=='SHORT' else 'SELL'
   else:
    # A crash can occur after VALIDATED but before configuration.  Recovering
    # OPENs must re-establish the same account policy gate before POST.
    self._configure_symbol(intent.symbol,dry_run);quantity=row['quantity'];order_side='BUY' if intent.side=='LONG' else 'SELL'
   self.ledger.transition(intent.signal_identity,OrderState.SUBMITTING.value);order={'symbol':intent.symbol,'side':order_side,'type':'MARKET','quantity':quantity,'newClientOrderId':intent.client_order_id}
   if intent.action=='CLOSE':order['reduceOnly']='true'
   try:response=self.adapter.create_order(order)
   except Exception:return self.ledger.transition(intent.signal_identity,OrderState.RECONCILING.value,submit_response_unknown=True)
   return self.ledger.transition(intent.signal_identity,{'FILLED':'FILLED','NEW':'ACKNOWLEDGED','PARTIALLY_FILLED':'PARTIALLY_FILLED'}.get(response.get('status'),'FAILED_SAFE'),binance_order_id=str(response.get('orderId','')),remote_status=response.get('status'))
  self.persistence.append('signals',date,{'signal':signal,'demo_epoch':self.epoch,'execution_intent_identity':intent.intent_identity})
  if action=='OPEN':
   try:check_risk(policy,signal,open_orders=(health or {}).get('open_orders',0),gross_exposure=(health or {}).get('gross_exposure',0),strategy_exposure=(health or {}).get('strategy_exposure',0),daily_pnl=(health or {}).get('daily_pnl',0))
   except DemoRiskRejected as exc:
    self.persistence.append('policy_rejections',date,{'signal_identity':intent.signal_identity,'execution_intent_identity':intent.intent_identity,'reason':exc.reason,'demo_epoch':self.epoch});return self.ledger.transition(intent.signal_identity,OrderState.REJECTED_POLICY.value,reason=exc.reason,dry_run=bool(dry_run))
  if action=='SKIP_SAME_DIRECTION':return self.ledger.transition(intent.signal_identity,OrderState.SKIPPED.value,dry_run=dry_run,reason='same_direction_position')
  if action=='OPEN' and (price is None or filters is None):raise FailClosedError('demo_market_metadata_missing')
  quantity=normalize_quantity(intent.notional,price,filters) if action=='OPEN' else str(close_quantity or '')
  if not quantity:raise FailClosedError('demo_close_quantity_missing')
  self.ledger.transition(intent.signal_identity,OrderState.VALIDATED.value,quantity=quantity,position_side='LONG' if intent.side=='LONG' else 'SHORT',dry_run=bool(dry_run))
  if dry_run:return self.ledger.transition(intent.signal_identity,OrderState.INTENT_CREATED.value,dry_run=True)
  # CLOSE is risk-reducing and relies on the already verified remote position;
  # it must survive a process restart without replaying account configuration.
  if action=='OPEN':self._configure_symbol(intent.symbol,dry_run)
  self.ledger.transition(intent.signal_identity,OrderState.SUBMITTING.value)
  side=close_side if action=='CLOSE' else intent.side
  order_side=('SELL' if side=='LONG' else 'BUY') if action=='CLOSE' else ('BUY' if side=='LONG' else 'SELL')
  order={'symbol':intent.symbol,'side':order_side,'type':'MARKET','quantity':quantity,'newClientOrderId':intent.client_order_id}
  if action=='CLOSE':order['reduceOnly']='true'
  try:response=self.adapter.create_order(order)
  except Exception:
   # Ambiguous POST is reconciled by deterministic clientOrderId; never retry POST here.
   return self.ledger.transition(intent.signal_identity,OrderState.RECONCILING.value,submit_response_unknown=True)
  status=response.get('status','NEW');mapping={'NEW':'ACKNOWLEDGED','PARTIALLY_FILLED':'PARTIALLY_FILLED','FILLED':'FILLED','REJECTED':'REJECTED'}
  return self.ledger.transition(intent.signal_identity,mapping.get(status,'FAILED_SAFE'),binance_order_id=str(response.get('orderId','')),remote_status=status)
