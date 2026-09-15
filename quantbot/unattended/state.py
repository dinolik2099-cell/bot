from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from .models import Issue

class StateStore:
    """Atomic, bounded local lifecycle state; never a production input."""
    def __init__(self,path):self.path=Path(path)
    def load(self):
        if not self.path.exists():return {"schema_version":"quantbot-unattended-state-v1","issues":{},"repairs":[],"recoveries":[],"notifications":{}}
        value=json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema_version")!="quantbot-unattended-state-v1":raise ValueError("unattended_state_schema_invalid")
        for key,default in (("issues",{}),("repairs",[]),("recoveries",[]),("notifications",{})):value.setdefault(key,default)
        return value
    def write(self,value):
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix(self.path.suffix+".tmp")
        tmp.write_text(json.dumps(value,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(tmp,self.path)
    @staticmethod
    def _lifecycle_id(fingerprint,timestamp):return hashlib.sha256(f"{fingerprint}:{timestamp}".encode()).hexdigest()
    def observe(self,issues:list[Issue],timestamp:str):
        state=self.load();previous=state["issues"];current={}
        for item in issues:
            row=previous.get(item.fingerprint)
            if row:current[item.fingerprint]={**row,"count":int(row.get("count",0))+1,"last":item.as_dict(),"last_seen":timestamp}
            else:current[item.fingerprint]={"count":1,"lifecycle_id":self._lifecycle_id(item.fingerprint,timestamp),"started_at":timestamp,"last":item.as_dict(),"last_seen":timestamp}
        known={(row["fingerprint"],row["lifecycle_id"]) for row in state["recoveries"]}
        for fingerprint,row in previous.items():
            key=(fingerprint,row["lifecycle_id"])
            if fingerprint not in current and key not in known:
                state["recoveries"].append({"fingerprint":fingerprint,"lifecycle_id":row["lifecycle_id"],"recovered_at":timestamp,"notified":False})
        state["issues"]=current;state["last_observation"]={"timestamp":timestamp,"issues":[item.as_dict() for item in issues]};self.write(state);return state
    def record_repair(self,*,fingerprint,lifecycle_id,timestamp,status,error_type=None,window_seconds=3600):
        state=self.load();state["repairs"]=[row for row in state["repairs"] if timestamp_value(timestamp)-timestamp_value(row["timestamp"])<window_seconds]
        row={"fingerprint":fingerprint,"lifecycle_id":lifecycle_id,"timestamp":timestamp,"status":status}
        if error_type:row["error_type"]=error_type
        state["repairs"].append(row);self.write(state);return state
    def mark_notified(self,key,timestamp):
        state=self.load()
        if key in state["notifications"]:return False
        state["notifications"][key]=timestamp;self.write(state);return True
    def pending_recoveries(self):return [row for row in self.load()["recoveries"] if not row.get("notified")]
    def mark_recovered_notified(self,fingerprint,lifecycle_id,timestamp):
        state=self.load()
        for row in state["recoveries"]:
            if row["fingerprint"]==fingerprint and row["lifecycle_id"]==lifecycle_id:
                if row.get("notified"):return False
                row["notified"]=True;row["notified_at"]=timestamp;self.write(state);return True
        return False

def timestamp_value(value):
    from datetime import datetime
    return datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()
