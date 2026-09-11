"""Date-partitioned append-only record router for forward evidence."""
from __future__ import annotations
from .core import AppendOnlyStore,utc_now
class ForwardPersistence:
 def __init__(self,root,git_commit,config_identity,universe_identity):self.store=AppendOnlyStore(root);self.meta={'schema_version':'quantbot-forward-record-v1','source':'binance_public','git_commit':git_commit,'config_identity':config_identity,'universe_identity':universe_identity}
 def append(self,kind,date,row):
  payload={**self.meta,'created_at':utc_now(),**dict(row)};return self.store.append(f'{kind}/{date}/{kind}.jsonl',payload)
