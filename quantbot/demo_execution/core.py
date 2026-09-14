from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone

class DemoExecutionError(RuntimeError):pass
class FailClosedError(DemoExecutionError):pass
class DemoTransientAPIError(DemoExecutionError):
 """A confirmed transport/API failure before a durable execution outcome.

 The runtime may retry this condition without advancing its Forward cursor.
 It deliberately remains distinct from ordinary DemoExecutionError, which is
 an integrity/configuration failure and therefore fail-closed.
 """
 def __init__(self,reason,operation=None):super().__init__(reason);self.operation=operation
class DemoRiskRejected(DemoExecutionError):
 def __init__(self,reason):super().__init__(reason);self.reason=reason
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def identity(value):return hashlib.sha256(canon(value).encode()).hexdigest()
def utc_now():return datetime.now(timezone.utc).isoformat()
