from __future__ import annotations
import hashlib, json, os
from datetime import datetime
from pathlib import Path
from .models import Issue

REPAIR_RECORD_LIMIT=64

class StateStore:
    """Atomic local state with bounded repair history and at-least-once outbox delivery."""
    def __init__(self,path):self.path=Path(path)
    def load(self):
        if not self.path.exists():return {"schema_version":"quantbot-unattended-state-v1","issues":{},"repairs":[],"recoveries":[],"notifications":{},"repair_window_untrusted":False}
        value=json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema_version")!="quantbot-unattended-state-v1":raise ValueError("unattended_state_schema_invalid")
        for key,default in (("issues",{}),("repairs",[]),("recoveries",[]),("notifications",{}),("repair_window_untrusted",False)):value.setdefault(key,default)
        return value
    def write(self,value):
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix(self.path.suffix+".tmp")
        tmp.write_text(json.dumps(value,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8");os.replace(tmp,self.path)
    @staticmethod
    def _lifecycle_id(fingerprint,timestamp):return hashlib.sha256(f"{fingerprint}:{timestamp}".encode()).hexdigest()
    def _repair_window(self,state,timestamp,window_seconds):
        if state.get("repair_window_untrusted"):return
        try:
            current=timestamp_value(timestamp);last=state.get("repair_clock")
            if last is not None and current<timestamp_value(last):raise ValueError("rollback")
            repairs=[]
            for row in state["repairs"]:
                age=current-timestamp_value(row.get("timestamp"))
                if age<0:raise ValueError("future")
                if age<window_seconds:repairs.append(row)
            state["repairs"]=repairs[-REPAIR_RECORD_LIMIT:];state["repair_clock"]=timestamp
        except Exception:
            state["repair_window_untrusted"]=True;state["repairs"]=state["repairs"][-REPAIR_RECORD_LIMIT:]
    def observe(self,issues:list[Issue],timestamp:str,window_seconds=3600):
        state=self.load();self._repair_window(state,timestamp,window_seconds);previous=state["issues"];current={}
        for item in issues:
            row=previous.get(item.fingerprint)
            if row:current[item.fingerprint]={**row,"count":int(row.get("count",0))+1,"last":item.as_dict(),"last_seen":timestamp}
            else:current[item.fingerprint]={"count":1,"lifecycle_id":self._lifecycle_id(item.fingerprint,timestamp),"started_at":timestamp,"last":item.as_dict(),"last_seen":timestamp}
        known={(row["fingerprint"],row["lifecycle_id"]) for row in state["recoveries"]}
        for fingerprint,row in previous.items():
            key=(fingerprint,row["lifecycle_id"])
            if fingerprint not in current and key not in known:state["recoveries"].append({"fingerprint":fingerprint,"lifecycle_id":row["lifecycle_id"],"recovered_at":timestamp})
        state["issues"]=current;state["last_observation"]={"timestamp":timestamp,"issues":[item.as_dict() for item in issues]};self.write(state);return state
    def record_repair(self,*,fingerprint,lifecycle_id,timestamp,status,error_type=None,window_seconds=3600):
        state=self.load();self._repair_window(state,timestamp,window_seconds)
        row={"fingerprint":fingerprint,"lifecycle_id":lifecycle_id,"timestamp":timestamp,"status":status}
        if error_type:row["error_type"]=error_type
        state["repairs"]=(state["repairs"]+[row])[-REPAIR_RECORD_LIMIT:];self.write(state);return state
    def queue_notification(self,identity,kind,message,timestamp):
        state=self.load()
        if identity not in state["notifications"]:state["notifications"][identity]={"kind":kind,"message":message,"state":"PENDING","created_at":timestamp,"attempts":0};self.write(state)
    def pending_notifications(self):return [(key,row) for key,row in self.load()["notifications"].items() if row.get("state")=="PENDING"]
    def delivery_attempt(self,identity,timestamp):
        state=self.load();row=state["notifications"][identity];row["attempts"]=int(row.get("attempts",0))+1;row["last_attempt_at"]=timestamp;self.write(state)
    def mark_sent(self,identity,timestamp):
        state=self.load();row=state["notifications"][identity]
        if row.get("state")!="SENT":row["state"]="SENT";row["sent_at"]=timestamp;self.write(state)

def timestamp_value(value):return datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()
