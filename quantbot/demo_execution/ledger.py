from __future__ import annotations
import json
from pathlib import Path
from .core import DemoExecutionError,identity,utc_now
from .models import OrderState,TERMINAL

class ExecutionLedger:
 def __init__(self,root):self.path=Path(root)/'runtime'/'ledger.json';self.path.parent.mkdir(parents=True,exist_ok=True);self.rows=json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
 def _save(self):
  temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.rows,sort_keys=True),encoding='utf-8');temp.replace(self.path)
 def create(self,intent):
  existing=self.rows.get(intent.signal_identity)
  if existing:
   if existing['execution_intent_identity']!=intent.intent_identity:raise DemoExecutionError('demo_intent_identity_ambiguity')
   return dict(existing),False
  row={'signal_identity':intent.signal_identity,'execution_intent_identity':intent.intent_identity,'client_order_id':intent.client_order_id,'state':OrderState.INTENT_CREATED.value,'intent':intent.row(),'events':[{'state':OrderState.INTENT_CREATED.value,'at':utc_now()}]};self.rows[intent.signal_identity]=row;self._save();return dict(row),True
 def transition(self,signal_identity,state,**fields):
  row=self.rows.get(signal_identity)
  if not row:raise DemoExecutionError('demo_ledger_signal_missing')
  if state not in {item.value for item in OrderState}:raise DemoExecutionError('demo_order_state_invalid')
  if row['state'] in {item.value for item in TERMINAL} and state!=row['state']:raise DemoExecutionError('demo_terminal_state_immutable')
  row.update(fields);row['state']=state;row['events'].append({'state':state,'at':utc_now(),**fields});self._save();return dict(row)
 def unresolved(self):return [dict(row) for row in self.rows.values() if row['state'] not in {item.value for item in TERMINAL}]
 def live_exposure(self):return [dict(row) for row in self.rows.values() if not row.get('dry_run') and row['intent'].get('action')=='OPEN' and row['state'] not in {item.value for item in TERMINAL}]
