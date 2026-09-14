from __future__ import annotations
from .models import ExecutionIntent,OrderState
from .risk import check_risk,normalize_quantity
from .core import FailClosedError

class DemoExecutionEngine:
 def __init__(self,ledger,persistence,adapter,config,epoch):self.ledger,self.persistence,self.adapter,self.config,self.epoch=ledger,persistence,adapter,config,epoch;self.fail_closed=False
 def disable(self,reason):self.fail_closed=True;return reason
 def process(self,signal,date,*,dry_run=True,price=None,filters=None,health=None):
  if self.fail_closed:raise FailClosedError('demo_new_orders_disabled')
  policy=self.config.get('execution_policy')
  if policy is None:raise FailClosedError('demo_execution_policy_missing')
  check_risk(policy,signal,open_orders=(health or {}).get('open_orders',0),gross_exposure=(health or {}).get('gross_exposure',0),strategy_exposure=(health or {}).get('strategy_exposure',0),daily_pnl=(health or {}).get('daily_pnl',0))
  intent=ExecutionIntent.from_signal(signal,policy['order_notional']);row,created=self.ledger.create(intent)
  if not created:return row
  self.persistence.append('signals',date,{'signal':signal,'demo_epoch':self.epoch,'execution_intent_identity':intent.intent_identity})
  if price is None or filters is None:raise FailClosedError('demo_market_metadata_missing')
  quantity=normalize_quantity(intent.notional,price,filters);self.ledger.transition(intent.signal_identity,OrderState.VALIDATED.value,quantity=quantity)
  if dry_run:return self.ledger.transition(intent.signal_identity,OrderState.INTENT_CREATED.value,dry_run=True)
  self.ledger.transition(intent.signal_identity,OrderState.SUBMITTING.value)
  try:response=self.adapter.create_order({'symbol':intent.symbol,'side':'BUY' if intent.side=='LONG' else 'SELL','type':'MARKET','quantity':quantity,'newClientOrderId':intent.client_order_id})
  except Exception:
   # Ambiguous POST is reconciled by deterministic clientOrderId; never retry POST here.
   return self.ledger.transition(intent.signal_identity,OrderState.RECONCILING.value,submit_response_unknown=True)
  status=response.get('status','NEW');mapping={'NEW':'ACKNOWLEDGED','PARTIALLY_FILLED':'PARTIALLY_FILLED','FILLED':'FILLED','REJECTED':'REJECTED'}
  return self.ledger.transition(intent.signal_identity,mapping.get(status,'FAILED_SAFE'),binance_order_id=str(response.get('orderId','')),remote_status=status)
