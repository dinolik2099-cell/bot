from __future__ import annotations
from pathlib import Path
from .core import identity,utc_now,FailClosedError
from .signal_reader import ForwardSignalReader
from .ledger import ExecutionLedger
from .persistence import DemoPersistence
from .reconciliation import reconcile

class DemoRuntime:
 def __init__(self,config,root,forward_root,adapter,git_commit):
  self.config,self.root,self.forward_root,self.adapter,self.git_commit=config,Path(root),Path(forward_root),adapter,git_commit;self.persistence=DemoPersistence(root);self.ledger=ExecutionLedger(root);self.fail_closed=False;self.epoch_start=(self.persistence.read_checkpoint() or {}).get('demo_epoch_start',utc_now())
 def checkpoint(self,cursor=None,reconciliation_state=None):
  row={'schema_version':'quantbot-demo-checkpoint-v1','git_commit':self.git_commit,'demo_epoch':self.root.name,'demo_epoch_start':self.epoch_start,'config_identity':self.config['config_identity'],'source_forward_identity':identity({'root':str(self.forward_root)}),'last_signal_cursor':cursor,'orders_seen':len(self.ledger.rows),'fills_seen':sum(row['state']=='FILLED' for row in self.ledger.rows.values()),'reconciliation':reconciliation_state or {},'fail_closed':self.fail_closed,'runtime_health':{'live_order_endpoint_allowed':False}};row['checkpoint_identity']=identity(row);return self.persistence.write_checkpoint(row)
 def reconcile(self):
  try:return reconcile(self.ledger,self.adapter)
  except Exception as exc:self.fail_closed=True;self.persistence.append('reconciliation',utc_now()[:10],{'reason':str(exc),'fail_closed':True});raise
 def diagnostics(self):
  credentials=bool(self.adapter.api_key and self.adapter.api_secret);out={'environment':self.config['environment'],'endpoint':self.config['endpoint'],'live_allowed':False,'credentials_loaded':credentials,'ledger_state':len(self.ledger.rows),'checkpoint_state':self.persistence.read_checkpoint(),'fail_closed':self.fail_closed}
  if credentials:
   try:out.update({'account_reachable':True,'balance':self.adapter.balance(),'position_mode':self.adapter.position_mode(),'open_orders_count':len(self.adapter.open_orders()),'positions_count':len(self.adapter.positions())})
   except Exception as exc:out.update({'account_reachable':False,'error_type':type(exc).__name__})
  return out
