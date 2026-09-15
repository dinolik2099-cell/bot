from __future__ import annotations
import json, os, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from .models import Issue, Status, overall
from .state import StateStore
from .recovery import RecoveryController
from .notifications import NotificationSink

def now():return datetime.now(timezone.utc).isoformat()
def issue(code,category,severity,message,**details):
    return Issue(code,category,severity,message,now(),details,actionable=severity==Status.ALERT,
                 auto_repair_allowed=code in {"forward_service_down","forward_checkpoint_stale"} and details.get("resource_verified") is True)

class SystemProbe:
    """Production read-only probe.  Its recovery counterpart is injected separately."""
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
    def demo_nonterminals(self):return []
    def demo_consumption(self):return {"forward_new":False,"cursor_stuck":False,"age_seconds":0}

class NoopRecovery:
    def restart(self,unit):raise RuntimeError("recovery_adapter_not_configured")

class UnattendedSupervisor:
    def __init__(self,root,config,probe=None,recovery_adapter=None,notifier=None,clock=now):
        self.root=Path(root);self.config=config;self.probe=probe or SystemProbe();self.clock=clock
        self.state=StateStore(self.root/config["state_path"]);self.recovery=RecoveryController(config,recovery_adapter or NoopRecovery());self.notifier=notifier or NotificationSink()
    def _json(self,name,issues,*,category="HISTORICAL",path=None):
        target=self.root/(path if path is not None else self.config["paths"][name])
        try:return json.loads(target.read_text(encoding="utf-8"))
        except FileNotFoundError:issues.append(issue(f"missing_{name}",category,Status.ALERT,"required resource is missing",path=str(target),resource_verified=False));return None
        except Exception as exc:issues.append(issue(f"malformed_{name}",category,Status.BLOCKED,"resource is not parseable",error=type(exc).__name__,path=str(target),resource_verified=False));return None
    def _historical(self,issues):
        plan=self._json("plan",issues);boundary=self._json("boundary",issues);manifest=self._json("manifest",issues)
        if plan and plan.get("research_plan_identity") is None:issues.append(issue("frozen_plan_drift","HISTORICAL",Status.BLOCKED,"frozen plan identity absent"))
        if boundary and boundary.get("status")!="LOCKED":issues.append(issue("research_boundary_drift","HISTORICAL",Status.BLOCKED,"research boundary is not locked"))
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
        for row in self.probe.demo_nonterminals():
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
        lag=self.probe.demo_consumption()
        if lag.get("forward_new") and lag.get("cursor_stuck") and lag.get("age_seconds",0)>self.config["thresholds"]["demo_consumption_lag_seconds"]:issues.append(issue("demo_consumption_lag","CROSS_CHAIN",Status.ALERT,"Forward continues while Demo consumption is stuck",age_seconds=lag["age_seconds"]))
    def _host(self,issues):
        row=self.probe.host();limits=self.config["thresholds"]
        if row.get("disk_percent",0)>=limits["disk_percent"]:issues.append(issue("host_disk_high","HOST",Status.ALERT,"disk usage above threshold",disk_percent=row.get("disk_percent")))
        if row.get("memory_available_mb") is not None and row["memory_available_mb"]<limits["memory_available_mb"]:issues.append(issue("host_memory_low","HOST",Status.ALERT,"available memory below threshold",available_mb=row["memory_available_mb"]))
        # High swap with healthy available memory is deliberately not a fault.
        return row
    def run_once(self,shadow=True):
        issues=[];plan,boundary,manifest=self._historical(issues);forward_service,forward=self._forward(plan or {},issues);demo_service,demo=self._demo(issues);self._cross_chain(plan or {},forward,demo,issues);host=self._host(issues)
        timestamp=self.clock();state=self.state.observe(issues,timestamp);actions=[]
        for item in issues:
            lifecycle=state["issues"][item.fingerprint]["lifecycle_id"]
            if item.severity in {Status.ALERT,Status.BLOCKED} and self.state.mark_notified(f"alert:{item.fingerprint}:{lifecycle}",timestamp):self.notifier.notify(f"QuantBot {item.severity.value}: {item.code}")
            action="SHADOW_ONLY" if shadow else self.recovery.decide(item,state,lifecycle)
            if action=="REPAIR_ELIGIBLE":
                self.state.record_repair(fingerprint=item.fingerprint,lifecycle_id=lifecycle,timestamp=timestamp,status="ATTEMPT",window_seconds=self.config["recovery"]["repair_window_seconds"])
                try:
                    self.recovery.execute(item);self.state.record_repair(fingerprint=item.fingerprint,lifecycle_id=lifecycle,timestamp=timestamp,status="SUCCESS",window_seconds=self.config["recovery"]["repair_window_seconds"]);action="REPAIRED"
                    if self.state.mark_notified(f"repair_success:{item.fingerprint}:{lifecycle}",timestamp):self.notifier.notify(f"QuantBot auto-repair attempt success: {item.code}")
                except Exception as exc:
                    self.state.record_repair(fingerprint=item.fingerprint,lifecycle_id=lifecycle,timestamp=timestamp,status="FAILURE",error_type=type(exc).__name__,window_seconds=self.config["recovery"]["repair_window_seconds"]);action="REPAIR_FAILED"
            actions.append({"fingerprint":item.fingerprint,"action":action})
        for recovered in self.state.pending_recoveries():
            if self.state.mark_recovered_notified(recovered["fingerprint"],recovered["lifecycle_id"],timestamp):self.notifier.notify("QuantBot RECOVERED")
        return {"schema_version":"quantbot-unattended-report-v1","timestamp":timestamp,"overall":overall(issues).value,"issues":[item.as_dict() for item in issues],"actions":actions,"shadow":bool(shadow),"services":{"forward":forward_service,"demo":demo_service},"host":host,"identities":{"research_plan_identity":(plan or {}).get("research_plan_identity"),"forward_checkpoint_plan":(forward or {}).get("research_plan_identity")}}

def now_timestamp(path):
    return max(0.0,datetime.now(timezone.utc).timestamp()-Path(path).stat().st_mtime)
