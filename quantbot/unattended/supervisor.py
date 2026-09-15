from __future__ import annotations
import json, os, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from .models import Issue, Status, overall
from .state import StateStore
from .recovery import RecoveryController
from .notifications import NotificationSink
from quantbot.demo_execution.signal_reader import ForwardSignalReader
from quantbot.demo_execution.core import identity

def now():return datetime.now(timezone.utc).isoformat()
def issue(code,category,severity,message,**details):
    return Issue(code,category,severity,message,now(),details,actionable=severity==Status.ALERT,
                 auto_repair_allowed=code in {"forward_service_down","forward_checkpoint_stale"} and details.get("resource_verified") is True)

class SystemProbe:
    """Production read-only probe.  Its recovery counterpart is injected separately."""
    def __init__(self,root,config,clock=now):self.root=Path(root);self.config=config;self.clock=clock
    def service(self,unit):
        try:
            text=subprocess.check_output(["systemctl","show",unit,"--property=ActiveState,SubState,MainPID,NRestarts,WorkingDirectory","--no-page"],text=True,stderr=subprocess.DEVNULL)
            return {key:value for key,value in (line.split("=",1) for line in text.splitlines() if "=" in line)}
        except Exception:return {"ActiveState":"unknown"}
    def host(self):
        usage=shutil.disk_usage("/");memory={"available_mb":None,"swap_percent":None,"load":None}
        try:
            values=Path("/proc/meminfo").read_text().splitlines();data={line.split(":",1)[0]:int(line.split()[1]) for line in values};memory["available_mb"]=data.get("MemAvailable",0)//1024
            total=data.get("SwapTotal",0);memory["swap_percent"]=(100*(total-data.get("SwapFree",0))/total) if total else 0
            memory["load"]=os.getloadavg()[0]
        except Exception:pass
        return {"disk_percent":100*(usage.total-usage.free)/usage.total,"inode_percent":None,**memory}
    def _production_path(self,key,name):return self.root/self.config["production"][key][name]
    def _timestamp(self,value):
        try:
            parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
            if parsed.tzinfo is None:raise ValueError("timezone_required")
            return parsed.astimezone(timezone.utc)
        except Exception as exc:raise RuntimeError("unattended_timestamp_invalid") from exc
    def demo_nonterminals(self):
        """Read current Demo ledger only; malformed evidence is fail-visible."""
        ledger=self._production_path("demo","data_root")/"runtime"/"ledger.json"
        checkpoint_path=self._production_path("demo","checkpoint")
        try:checkpoint=json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except Exception as exc:raise RuntimeError("demo_checkpoint_evidence_invalid") from exc
        if not ledger.exists() and isinstance(checkpoint,dict) and checkpoint.get("orders_seen")==0:return []
        try:rows=json.loads(ledger.read_text(encoding="utf-8"))
        except Exception as exc:raise RuntimeError("demo_ledger_evidence_invalid") from exc
        if not isinstance(rows,dict):raise RuntimeError("demo_ledger_evidence_invalid")
        terminal={"FILLED","CANCELED","EXPIRED","REJECTED","REJECTED_POLICY","REJECTED_VENUE","FAILED_SAFE","SKIPPED"};result=[]
        for signal_identity,row in rows.items():
            if not isinstance(row,dict) or not isinstance(signal_identity,str) or not isinstance(row.get("state"),str):raise RuntimeError("demo_ledger_evidence_invalid")
            if row["state"] in terminal:continue
            events=row.get("events")
            if not isinstance(events,list) or not events or not isinstance(events[-1],dict):raise RuntimeError("demo_ledger_evidence_invalid")
            age=max(0.0,datetime.now(timezone.utc).timestamp()-self._timestamp(events[-1].get("at")).timestamp())
            result.append({"intent_id":row.get("execution_intent_identity"),"state":row["state"],"age_seconds":age})
        return result
    def demo_consumption(self):
        """Read-only lag probe respecting the recovery epoch's inherited cursor."""
        checkpoint_path=self._production_path("demo","checkpoint")
        signals=self._production_path("demo","forward_signals")
        try:checkpoint=json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except Exception as exc:raise RuntimeError("demo_consumption_checkpoint_invalid") from exc
        if not isinstance(checkpoint,dict) or not isinstance(checkpoint.get("last_signal_cursor"),str):raise RuntimeError("demo_consumption_checkpoint_invalid")
        cursor=checkpoint["last_signal_cursor"]
        recovery_paths=list((self._production_path("demo","data_root")/"recovery").glob("*/*.jsonl"))
        if recovery_paths:
            if len(recovery_paths)!=1:raise RuntimeError("demo_recovery_evidence_ambiguous")
            try:
                rows=[json.loads(line) for line in recovery_paths[0].read_text(encoding="utf-8").splitlines()]
            except Exception as exc:raise RuntimeError("demo_recovery_evidence_invalid") from exc
            if len(rows)!=1 or not isinstance(rows[0],dict):raise RuntimeError("demo_recovery_evidence_ambiguous")
            recovery=rows[0];stored_identity=recovery.get("recovery_identity")
            if recovery.get("schema_version")!="quantbot-demo-recovery-v1" or not isinstance(stored_identity,str) or stored_identity!=identity({key:value for key,value in recovery.items() if key not in {"created_at","recovery_identity"}}):raise RuntimeError("demo_recovery_evidence_invalid")
            expected_forward=str(signals.parent.resolve());expected_identity=identity({"root":expected_forward})
            if recovery.get("target_git_commit")!=checkpoint.get("git_commit") or recovery.get("target_config_identity")!=checkpoint.get("config_identity") or recovery.get("source_forward_identity")!=expected_identity or recovery.get("forward_root")!=expected_forward or checkpoint.get("source_forward_identity")!=expected_identity:raise RuntimeError("demo_recovery_provenance_mismatch")
            epoch_start=self._timestamp(recovery.get("created_at"))
        else:
            if not isinstance(checkpoint.get("demo_epoch_start"),str):raise RuntimeError("demo_consumption_checkpoint_invalid")
            epoch_start=self._timestamp(checkpoint["demo_epoch_start"])
        try:
            records=ForwardSignalReader(signals.parent).discover()
        except RuntimeError:raise
        except Exception as exc:raise RuntimeError("demo_consumption_signal_invalid") from exc
        markers=[marker for marker,_signal in records]
        if cursor not in markers:raise RuntimeError("demo_consumption_cursor_invalid")
        index=markers.index(cursor)
        try:pending=[self._timestamp(signal["created_at"]) for _marker,signal in records[index+1:] if self._timestamp(signal["created_at"])>=epoch_start]
        except Exception as exc:raise RuntimeError("demo_consumption_signal_invalid") from exc
        if not pending:return {"forward_new":False,"cursor_stuck":False,"age_seconds":0}
        age=max(0.0,datetime.now(timezone.utc).timestamp()-min(pending).timestamp())
        return {"forward_new":True,"cursor_stuck":True,"age_seconds":age}

class NoopRecovery:
    def restart(self,unit):raise RuntimeError("recovery_adapter_not_configured")

class UnattendedSupervisor:
    def __init__(self,root,config,probe=None,recovery_adapter=None,notifier=None,clock=now):
        self.root=Path(root);self.config=config;self.probe=probe or SystemProbe(self.root,config);self.clock=clock
        self.state=StateStore(self.root/config["state_path"],config.get("state_retention"));self.recovery=RecoveryController(config,recovery_adapter or NoopRecovery());self.notifier=notifier or NotificationSink()
    def _json(self,name,issues,*,category="HISTORICAL",path=None):
        target=self.root/(path if path is not None else self.config["paths"][name])
        try:return json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:issues.append(issue(f"missing_{name}",category,Status.ALERT,"required resource is missing",path=str(target),resource_verified=False));return None
        except Exception as exc:issues.append(issue(f"malformed_{name}",category,Status.BLOCKED,"resource is not parseable",error=type(exc).__name__,path=str(target),resource_verified=False));return None
    def _historical(self,issues):
        plan=self._json("plan",issues);boundary=self._json("boundary",issues);manifest=self._json("manifest",issues)
        if plan and plan.get("research_plan_identity") is None:issues.append(issue("frozen_plan_drift","HISTORICAL",Status.BLOCKED,"frozen plan identity absent"))
        if boundary and boundary.get("status")!="LOCKED":issues.append(issue("research_boundary_drift","HISTORICAL",Status.BLOCKED,"research boundary is not locked"))
        if manifest and not isinstance(manifest.get("manifest_version"),str):issues.append(issue("research_manifest_integrity_invalid","HISTORICAL",Status.BLOCKED,"research manifest version is absent"))
        return plan,boundary,manifest
    def _service(self,key,issues):
        unit=self.config["production"][key]["service"];row=self.probe.service(unit)
        if row.get("ActiveState")!="active":issues.append(issue(f"{key}_service_down",key.upper(),Status.ALERT,"service is not active",unit=unit,state=row.get("ActiveState")))
        return row
    def _resource(self,key,issues):
        declaration=self.config["production"][key];data_root=self.root/declaration["data_root"];checkpoint_path=self.root/declaration["checkpoint"]
        try: belongs=checkpoint_path.resolve().is_relative_to(data_root.resolve())
        except (OSError,ValueError):belongs=False
        if not data_root.is_dir() or not belongs:
            issues.append(issue(f"{key}_resource_configuration_invalid",key.upper(),Status.ALERT,"declared production resource is invalid",data_root=str(data_root),checkpoint=str(checkpoint_path),resource_verified=False));return None,None
        checkpoint=self._json(f"{key}_checkpoint",issues,category=key.upper(),path=declaration["checkpoint"])
        if not checkpoint:return None,checkpoint
        if checkpoint.get("schema_version")!=declaration["checkpoint_schema"]:
            issues.append(issue(f"{key}_checkpoint_identity_invalid",key.upper(),Status.BLOCKED,"checkpoint does not match declared production instance",path=str(checkpoint_path),resource_verified=False));return None,checkpoint
        if key=="demo" and checkpoint.get("demo_epoch")!=data_root.name:
            issues.append(issue("demo_checkpoint_identity_invalid","DEMO",Status.BLOCKED,"checkpoint epoch does not match declared data root",path=str(checkpoint_path),resource_verified=False));return None,checkpoint
        return checkpoint_path,checkpoint
    def _forward(self,plan,issues):
        service=self._service("forward",issues);path,checkpoint=self._resource("forward",issues)
        if not checkpoint:return service,None
        if checkpoint.get("research_plan_identity")!=plan.get("research_plan_identity"):
            issues.append(issue("frozen_plan_drift","CROSS_CHAIN",Status.BLOCKED,"forward checkpoint plan mismatch"))
        if checkpoint.get("forward_research_only") is not True or checkpoint.get("oos_allowed") is not False:
            issues.append(issue("forward_authority_invalid","FORWARD",Status.BLOCKED,"forward authority boundary invalid"))
        verified=path is not None and checkpoint.get("research_plan_identity")==plan.get("research_plan_identity") and checkpoint.get("forward_research_only") is True and checkpoint.get("oos_allowed") is False
        if path and now_timestamp(path)>self.config["thresholds"]["checkpoint_age_seconds"]:issues.append(issue("forward_checkpoint_stale","FORWARD",Status.ALERT,"forward checkpoint is stale",unit=self.config["production"]["forward"]["service"],resource_verified=verified))
        return service,checkpoint
    def _demo(self,issues):
        service=self._service("demo",issues);_path,checkpoint=self._resource("demo",issues)
        if not checkpoint:return service,None
        if checkpoint.get("fail_closed") is True:issues.append(issue("demo_fail_closed","DEMO",Status.BLOCKED,"Demo runtime is fail-closed"))
        reconciliation=checkpoint.get("reconciliation",{})
        if reconciliation.get("ambiguous") is True:issues.append(issue("demo_reconciliation_ambiguity","DEMO",Status.BLOCKED,"Demo reconciliation is ambiguous"))
        try:nonterminals=self.probe.demo_nonterminals()
        except Exception as exc:
            issues.append(issue("demo_nonterminal_evidence_invalid","DEMO",Status.BLOCKED,"Demo ledger evidence is not reliable",error=type(exc).__name__));nonterminals=[]
        for row in nonterminals:
            if row.get("age_seconds",0)>self.config["thresholds"].get("nonterminal_age_seconds",300):issues.append(issue("demo_nonterminal_orphan","DEMO",Status.ALERT,"same nonterminal lifecycle is persistent",intent_id=row.get("intent_id"),state=row.get("state")))
        return service,checkpoint
    def _cross_chain(self,plan,forward,demo,issues):
        if not forward or not demo:return
        if forward.get("research_plan_identity")!=plan.get("research_plan_identity"):return
        # Demo source_forward_identity has no declared semantic equality with
        # individual signal fields, so it is reported only as provenance.
        signals=self.root/self.config["production"]["demo"]["forward_signals"]
        if signals.exists() and demo.get("last_signal_cursor") is None:
            issues.append(issue("demo_cursor_uninitialized","CROSS_CHAIN",Status.WARN,"forward signals exist but Demo cursor is absent"))
        try:lag=self.probe.demo_consumption()
        except Exception as exc:
            issues.append(issue("demo_consumption_evidence_invalid","CROSS_CHAIN",Status.BLOCKED,"Demo consumption evidence is not reliable",error=type(exc).__name__));return
        if lag.get("forward_new") and lag.get("cursor_stuck") and lag.get("age_seconds",0)>self.config["thresholds"]["demo_consumption_lag_seconds"]:issues.append(issue("demo_consumption_lag","CROSS_CHAIN",Status.ALERT,"Forward continues while Demo consumption is stuck",age_seconds=lag["age_seconds"]))
    def _host(self,issues):
        row=self.probe.host();limits=self.config["thresholds"]
        if row.get("disk_percent",0)>=limits["disk_percent"]:issues.append(issue("host_disk_high","HOST",Status.ALERT,"disk usage above threshold",disk_percent=row.get("disk_percent")))
        if row.get("memory_available_mb") is not None and row["memory_available_mb"]<limits["memory_available_mb"]:issues.append(issue("host_memory_low","HOST",Status.ALERT,"available memory below threshold",available_mb=row["memory_available_mb"]))
        # High swap with healthy available memory is deliberately not a fault.
        return row
    def run_once(self,shadow=True):
        issues=[];plan,boundary,manifest=self._historical(issues);forward_service,forward=self._forward(plan or {},issues);demo_service,demo=self._demo(issues);self._cross_chain(plan or {},forward,demo,issues);host=self._host(issues)
        timestamp=self.clock();state=self.state.observe(issues,timestamp,self.config["recovery"]["repair_window_seconds"]);actions=[]
        for item in issues:
            lifecycle=state["issues"][item.fingerprint]["lifecycle_id"]
            if item.severity in {Status.ALERT,Status.BLOCKED}:self.state.queue_notification(f"alert:{item.fingerprint}:{lifecycle}","ALERT",f"QuantBot {item.severity.value}: {item.code}",timestamp)
            action="SHADOW_ONLY" if shadow else self.recovery.claim(item,self.state,lifecycle,timestamp)
            action_details={}
            if action=="REPAIR_CLAIMED":
                try:
                    self.recovery.execute(item);self.state.record_repair_outcome(fingerprint=item.fingerprint,lifecycle_id=lifecycle,timestamp=timestamp,status="SUCCESS",window_seconds=self.config["recovery"]["repair_window_seconds"]);action="REPAIRED"
                    self.state.queue_notification(f"repair_success:{item.fingerprint}:{lifecycle}","REPAIR_SUCCESS",f"QuantBot auto-repair attempt success: {item.code}",timestamp)
                except Exception as exc:
                    error_type=type(exc).__name__;self.state.record_repair_outcome(fingerprint=item.fingerprint,lifecycle_id=lifecycle,timestamp=timestamp,status="FAILURE",error_type=error_type,window_seconds=self.config["recovery"]["repair_window_seconds"]);action="REPAIR_FAILED";action_details={"error_type":error_type}
            actions.append({"fingerprint":item.fingerprint,"action":action,**action_details})
        for recovered in self.state.load()["recoveries"]:self.state.queue_notification(f"recovered:{recovered['fingerprint']}:{recovered['lifecycle_id']}","RECOVERED","QuantBot RECOVERED",timestamp)
        for identity in self.state.notification_identities():
            row=self.state.claim_notification(identity,timestamp)
            if not row:continue
            try:self.notifier.notify(row["message"])
            except Exception:continue
            self.state.mark_sent(identity,row["claim_token"],timestamp)
        return {"schema_version":"quantbot-unattended-report-v1","timestamp":timestamp,"overall":overall(issues).value,"issues":[item.as_dict() for item in issues],"actions":actions,"shadow":bool(shadow),"services":{"forward":forward_service,"demo":demo_service},"host":host,"identities":{"research_plan_identity":(plan or {}).get("research_plan_identity"),"forward_checkpoint_plan":(forward or {}).get("research_plan_identity")}}

def now_timestamp(path):
    return max(0.0,datetime.now(timezone.utc).timestamp()-Path(path).stat().st_mtime)
