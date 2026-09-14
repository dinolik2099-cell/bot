from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone

class DemoExecutionError(RuntimeError):pass
class FailClosedError(DemoExecutionError):pass
class DemoRiskRejected(DemoExecutionError):
 def __init__(self,reason):super().__init__(reason);self.reason=reason
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def identity(value):return hashlib.sha256(canon(value).encode()).hexdigest()
def utc_now():return datetime.now(timezone.utc).isoformat()
