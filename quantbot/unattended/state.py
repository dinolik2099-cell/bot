from __future__ import annotations
import json, os
from pathlib import Path
from .models import Issue

class StateStore:
    """Atomic local supervisor state.  This path is runtime evidence, never Git input."""
    def __init__(self,path):self.path=Path(path)
    def load(self):
        if not self.path.exists():return {"schema_version":"quantbot-unattended-state-v1","issues":{},"repairs":[],"notifications":{}}
        value=json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema_version")!="quantbot-unattended-state-v1":raise ValueError("unattended_state_schema_invalid")
        return value
    def write(self,value):
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix(self.path.suffix+".tmp")
        tmp.write_text(json.dumps(value,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(tmp,self.path)
    def observe(self,issues:list[Issue],timestamp:str):
        state=self.load();previous=state.setdefault("issues",{});current={}
        for issue in issues:
            row=previous.get(issue.fingerprint,{"count":0})
            current[issue.fingerprint]={"count":int(row.get("count",0))+1,"last":issue.as_dict(),"last_seen":timestamp}
        state["issues"]=current;state["last_observation"]={"timestamp":timestamp,"issues":[item.as_dict() for item in issues]};self.write(state);return state
    def notify_once(self,fingerprint,timestamp):
        state=self.load();sent=state.setdefault("notifications",{})
        if fingerprint in sent:return False
        sent[fingerprint]=timestamp;self.write(state);return True
