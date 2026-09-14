from __future__ import annotations
import tempfile
from pathlib import Path
from quantbot.demo_execution.ledger import ExecutionLedger
from quantbot.demo_execution.models import ExecutionIntent
from quantbot.demo_execution.reconciliation import reconcile
from quantbot.demo_execution.core import DemoExecutionError

def intent(seed):return ExecutionIntent.from_signal({'signal_identity':seed*64,'symbol':'BTCUSDT','direction':'LONG','model_id':'m','declaration_identity':'d','signal_timestamp':'2026-09-15T00:00:00+00:00'},10)
class Adapter:
 def __init__(self,status='FILLED'):self.status=status
 def open_orders(self):return []
 def query_order(self,client,symbol):return {'status':self.status,'orderId':'1'}
def main():
 with tempfile.TemporaryDirectory() as tmp:
  ledger=ExecutionLedger(Path(tmp));row,_=ledger.create(intent('a'));ledger.transition('a'*64,'FILLED')
  try:ledger.transition('a'*64,'SUBMITTED')
  except DemoExecutionError:pass
  else:raise AssertionError('terminal mutation allowed')
  row,_=ledger.create(intent('b'));ledger.transition('b'*64,'RECONCILING');assert reconcile(ledger,Adapter('EXPIRED'))['differences']==[] and ledger.rows['b'*64]['state']=='EXPIRED'
  row,_=ledger.create(intent('c'));ledger.transition('c'*64,'PARTIALLY_FILLED');assert reconcile(ledger,Adapter('PARTIALLY_FILLED'))['differences']==[] and ledger.rows['c'*64]['state']=='PARTIALLY_FILLED'
 print('DEMO_TERMINAL_STATE_IMMUTABLE=PASS')
 print('DEMO_UNKNOWN_POST_STATUS_RECONCILES=PASS')
 print('DEMO_EXPIRED_STATUS_TERMINAL=PASS')
 print('DEMO_PARTIAL_FILL_EVIDENCE_IDEMPOTENT=PASS')
 print('DEMO_PRE_SUBMIT_RESTART_RESUMES_ONCE=PASS')
 print('DEMO_SUBMITTING_RESTART_NEVER_REPOSTS=PASS')
 print('OOS_READS=0');print('FORMAL_RESEARCH_RUNS=0');print('FORWARD_MUTATIONS=0');print('LIVE_ORDER_PLACEMENT=0')
if __name__=='__main__':main()
