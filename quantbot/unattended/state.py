from __future__ import annotations
import hashlib, json, os, uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from .models import Issue

REPAIR_RECORD_LIMIT=64
OPERATOR_EVENT_LIMIT=64

class StateStore:
    """Cross-process atomic state; external notification delivery remains recoverable at-least-once."""
    def __init__(self,path,retention=None):self.path=Path(path);self.retention={"sent_notifications":256,"recoveries":256,"delivery_lease_seconds":60,**(retention or {})}
    @property
    def lock_path(self):return self.path.with_suffix(self.path.suffix+".lock")
    @contextmanager
    def _lock(self):
        self.lock_path.parent.mkdir(parents=True,exist_ok=True)
        with self.lock_path.open("a+b") as handle:
            handle.seek(0);handle.write(b"0");handle.flush()
            if os.name=="nt":
                import msvcrt;handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_LOCK,1)
                try:yield
                finally:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl;fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
                try:yield
                finally:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
    def _empty(self):return {"schema_version":"quantbot-unattended-state-v1","issues":{},"repairs":[],"recoveries":[],"notifications":{},"operator_events":[],"repair_window_untrusted":False}
    def _load(self):
        if not self.path.exists():return self._empty()
        value=json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema_version")!="quantbot-unattended-state-v1":raise ValueError("unattended_state_schema_invalid")
        for key,default in self._empty().items():value.setdefault(key,default)
        return value
    def load(self):return self._load()
    def _sync_dir(self):
        if os.name=="nt":return
        descriptor=os.open(str(self.path.parent),os.O_RDONLY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    def _write(self,value):
        self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix(self.path.suffix+f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with tmp.open("w",encoding="utf-8") as handle:
                handle.write(json.dumps(value,sort_keys=True,ensure_ascii=False)+"\n");handle.flush();os.fsync(handle.fileno())
            os.replace(tmp,self.path);self._sync_dir()
        finally:
            if tmp.exists():tmp.unlink()
    def _mutate(self,fn):
        with self._lock():
            state=self._load();result=fn(state);self._write(state);return result
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
        except Exception:state["repair_window_untrusted"]=True;state["repairs"]=state["repairs"][-REPAIR_RECORD_LIMIT:]
    def _prune_retention(self,state):
        try:
            complete=[]
            for row in state["recoveries"]:
                key=f"recovered:{row['fingerprint']}:{row['lifecycle_id']}";notification=state["notifications"].get(key)
                if notification and notification.get("state")=="SENT":complete.append(row)
            if any(not isinstance(row.get("recovered_at"),str) for row in complete):raise ValueError("malformed_recovery")
            expired=sorted(complete,key=lambda row:timestamp_value(row["recovered_at"]))[:max(0,len(complete)-int(self.retention["recoveries"]))]
            expired_keys={f"recovered:{row['fingerprint']}:{row['lifecycle_id']}" for row in expired};state["recoveries"]=[row for row in state["recoveries"] if f"recovered:{row['fingerprint']}:{row['lifecycle_id']}" not in expired_keys]
            for key in expired_keys:state["notifications"].pop(key,None)
            protected={f"recovered:{row['fingerprint']}:{row['lifecycle_id']}" for row in state["recoveries"]}
            sent=[(key,row) for key,row in state["notifications"].items() if row.get("state")=="SENT" and key not in protected]
            if any(not isinstance(row.get("sent_at"),str) for _,row in sent):raise ValueError("malformed_sent")
            for key,_ in sorted(sent,key=lambda item:timestamp_value(item[1]["sent_at"]))[:max(0,len(sent)-int(self.retention["sent_notifications"]))]:del state["notifications"][key]
        except Exception:state["retention_untrusted"]=True
    def observe(self,issues:list[Issue],timestamp:str,window_seconds=3600):
        def apply(state):
            self._repair_window(state,timestamp,window_seconds);previous=state["issues"];current={}
            for item in issues:
                row=previous.get(item.fingerprint)
                if row:current[item.fingerprint]={**row,"count":int(row.get("count",0))+1,"last":item.as_dict(),"last_seen":timestamp}
                else:current[item.fingerprint]={"count":1,"lifecycle_id":self._lifecycle_id(item.fingerprint,timestamp),"started_at":timestamp,"last":item.as_dict(),"last_seen":timestamp}
            known={(row["fingerprint"],row["lifecycle_id"]) for row in state["recoveries"]}
            for fingerprint,row in previous.items():
                if fingerprint not in current and (fingerprint,row["lifecycle_id"]) not in known:state["recoveries"].append({"fingerprint":fingerprint,"lifecycle_id":row["lifecycle_id"],"recovered_at":timestamp})
            state["issues"]=current;state["last_observation"]={"timestamp":timestamp,"issues":[item.as_dict() for item in issues]};self._prune_retention(state);return state
        return self._mutate(apply)
    def claim_repair(self,*,fingerprint,lifecycle_id,timestamp,window_seconds,threshold,max_repairs):
        def apply(state):
            self._repair_window(state,timestamp,window_seconds)
            if state.get("repair_window_untrusted"):return "AUTO_REPAIR_LOCKED"
            if int(state["issues"].get(fingerprint,{}).get("count",0))<threshold:return "AWAIT_CONFIRMATION"
            if sum(row.get("status")=="ATTEMPT" for row in state["repairs"])>=max_repairs:return "AUTO_REPAIR_LOCKED"
            if any(row.get("fingerprint")==fingerprint and row.get("lifecycle_id")==lifecycle_id for row in state["repairs"]):return "AWAIT_HEALTH_CONFIRMATION"
            state["repairs"]=(state["repairs"]+[{"fingerprint":fingerprint,"lifecycle_id":lifecycle_id,"timestamp":timestamp,"status":"ATTEMPT"}])[-REPAIR_RECORD_LIMIT:];return "REPAIR_CLAIMED"
        return self._mutate(apply)
    def record_repair_outcome(self,*,fingerprint,lifecycle_id,timestamp,status,error_type=None,window_seconds=3600):
        def apply(state):
            self._repair_window(state,timestamp,window_seconds);row={"fingerprint":fingerprint,"lifecycle_id":lifecycle_id,"timestamp":timestamp,"status":status}
            if error_type:row["error_type"]=error_type
            state["repairs"]=(state["repairs"]+[row])[-REPAIR_RECORD_LIMIT:]
        self._mutate(apply)
    def queue_notification(self,identity,kind,message,timestamp):
        self._mutate(lambda state:(state["notifications"].setdefault(identity,{"kind":kind,"message":message,"state":"PENDING","created_at":timestamp,"attempts":0}),self._prune_retention(state)))
    def notification_identities(self):return list(self._load()["notifications"])
    def claim_notification(self,identity,timestamp):
        def apply(state):
            row=state["notifications"].get(identity)
            if not row or row.get("state")=="SENT":return None
            current=timestamp_value(timestamp);lease=row.get("lease_until")
            if row.get("state")=="CLAIMED" and lease and current<timestamp_value(lease):return None
            token=uuid.uuid4().hex;row.update({"state":"CLAIMED","claim_token":token,"claimed_at":timestamp,"lease_until":(datetime.fromisoformat(timestamp.replace("Z","+00:00"))+timedelta(seconds=int(self.retention["delivery_lease_seconds"]))).isoformat(),"attempts":int(row.get("attempts",0))+1});return {**row,"claim_token":token}
        return self._mutate(apply)
    def mark_sent(self,identity,claim_token,timestamp):
        def apply(state):
            row=state["notifications"].get(identity)
            if row and row.get("state")=="CLAIMED" and row.get("claim_token")==claim_token:row.update({"state":"SENT","sent_at":timestamp});row.pop("claim_token",None);row.pop("lease_until",None);self._prune_retention(state);return True
            return False
        return self._mutate(apply)
    def rearm_repair_window(self,timestamp,window_seconds):
        def apply(state):
            if not state.get("repair_window_untrusted"):raise ValueError("repair_window_not_untrusted")
            probe=dict(state);probe["repair_window_untrusted"]=False;self._repair_window(probe,timestamp,window_seconds)
            if probe.get("repair_window_untrusted"):raise ValueError("repair_window_rearm_validation_failed")
            state.update(probe);state["operator_events"]=(state["operator_events"]+[{"operation":"repair_window_rearm","timestamp":timestamp}])[-OPERATOR_EVENT_LIMIT:]
        self._mutate(apply)

def timestamp_value(value):return datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()
