"""Date-partitioned append-only record router for forward evidence."""
from __future__ import annotations
from .core import AppendOnlyStore,utc_now
import json
import threading
class ForwardPersistence:
 def __init__(self,root,git_commit,config_identity,universe_identity):self.store=AppendOnlyStore(root);self._lock=threading.RLock();self.meta={'schema_version':'quantbot-forward-record-v1','source':'binance_public','git_commit':git_commit,'config_identity':config_identity,'universe_identity':universe_identity}
 def bind_snapshot(self,snapshot):
  """Update only provenance for newly appended evidence, never store state."""
  with self._lock:self.meta['universe_identity']=snapshot['universe_identity'];self.meta['membership_identity']=snapshot['membership_identity']
 def append(self,kind,date,row):
  with self._lock:
   payload={**self.meta,'created_at':utc_now(),**dict(row)};return self.store.append(f'{kind}/{date}/{kind}.jsonl',payload,deduplicate=False)
 def flush(self):
  with self._lock:self.store.flush()
 def daily_counts(self,date):
  """Read-only evidence counters for operator diagnostics."""
  with self._lock:
   out={}
   for kind in ('universe','intrabar','candles','bootstrap','signals','paths','exits','opportunities','portfolio','diagnostics','snapshots'):
    path=self.store.root/kind/date/f'{kind}.jsonl'
    out[kind]=sum(1 for line in path.open(encoding='utf-8')) if path.exists() else 0
   return out
