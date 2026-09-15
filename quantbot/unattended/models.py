from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import hashlib, json
from typing import Mapping

class Status(str, Enum):
    HEALTHY="HEALTHY"; WARN="WARN"; ALERT="ALERT"; BLOCKED="BLOCKED"

@dataclass(frozen=True)
class Issue:
    code: str; category: str; severity: Status; message: str
    timestamp: str; details: Mapping[str, object] = field(default_factory=dict)
    actionable: bool = False; auto_repair_allowed: bool = False
    @property
    def fingerprint(self) -> str:
        body={"code":self.code,"category":self.category,"severity":self.severity.value,
              "details":dict(self.details)}
        return hashlib.sha256(json.dumps(body,sort_keys=True,default=str,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    def as_dict(self) -> dict[str, object]:
        return {"code":self.code,"category":self.category,"severity":self.severity.value,
                "message":self.message,"timestamp":self.timestamp,"details":dict(self.details),
                "actionable":self.actionable,"auto_repair_allowed":self.auto_repair_allowed,
                "fingerprint":self.fingerprint}

def overall(issues: list[Issue]) -> Status:
    values={item.severity for item in issues}
    if Status.BLOCKED in values:return Status.BLOCKED
    if Status.ALERT in values:return Status.ALERT
    if Status.WARN in values:return Status.WARN
    return Status.HEALTHY
