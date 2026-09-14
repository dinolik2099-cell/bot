from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone

class DemoExecutionError(RuntimeError):pass
class FailClosedError(DemoExecutionError):pass
def canon(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def identity(value):return hashlib.sha256(canon(value).encode()).hexdigest()
def utc_now():return datetime.now(timezone.utc).isoformat()
