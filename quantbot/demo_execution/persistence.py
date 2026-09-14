from __future__ import annotations
import os,threading,json
from pathlib import Path
from .core import canon,utc_now,DemoExecutionError

class DemoPersistence:
 def __init__(self,root):self.root=Path(root);self._lock=threading.RLock();self._handles={};self._pending={}
 def _path(self,kind,date):return self.root/kind/date/f'{kind}.jsonl'
 def append(self,kind,date,row):
  with self._lock:
   path=self._path(kind,date);path.parent.mkdir(parents=True,exist_ok=True);key=str(path);handle=self._handles.get(key)
   if handle is None:handle=path.open('a',encoding='utf-8',newline='\n');self._handles[key]=handle;self._pending[key]=0
   handle.write(canon({'created_at':utc_now(),**dict(row)})+'\n');self._pending[key]+=1
   if self._pending[key]>=64:self._sync(key)
   return path
 def _sync(self,key):
  handle=self._handles[key];handle.flush();os.fsync(handle.fileno());self._pending[key]=0
 def flush(self):
  with self._lock:
   for key in tuple(self._handles):self._sync(key)
 def close(self):
  with self._lock:
   self.flush()
   for handle in self._handles.values():handle.close()
   self._handles.clear()
 def write_checkpoint(self,row):
  path=self.root/'checkpoints'/'runtime.json';path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.tmp');temporary.write_text(canon(row)+'\n',encoding='utf-8');os.replace(temporary,path);return path
 def read_checkpoint(self):
  path=self.root/'checkpoints'/'runtime.json'
  return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
