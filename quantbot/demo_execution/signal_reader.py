"""Read-only Forward signal cursor; no Forward imports or writes."""
from __future__ import annotations
import json
from pathlib import Path
from .core import DemoExecutionError

REQUIRED={'signal_identity','symbol','direction','signal_timestamp','model_id','declaration_identity'}
class ForwardSignalReader:
 def __init__(self,root):self.root=Path(root)
 def discover(self,cursor=None,not_before=None):
  result=[];seen=set();started=cursor is None
  for path in sorted((self.root/'signals').glob('*/*.jsonl')):
   for offset,line in enumerate(path.read_text(encoding='utf-8').splitlines()):
    marker=f'{path.relative_to(self.root).as_posix()}:{offset}'
    if not started:
     if marker==cursor:started=True
     continue
    row=json.loads(line)
    if not isinstance(row,dict) or not REQUIRED.issubset(row):raise DemoExecutionError('demo_forward_signal_schema_invalid')
    sid=row['signal_identity']
    if not_before is not None and str(row.get('created_at',''))<not_before:continue
    if sid in seen:raise DemoExecutionError('demo_forward_signal_duplicate_ambiguity')
    seen.add(sid);result.append((marker,row))
  return result
