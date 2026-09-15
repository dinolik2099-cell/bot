from __future__ import annotations
import json, os, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from .models import Issue, Status, overall
from .state import StateStore
from .recovery import RecoveryController
from .notifications import NotificationSink

def now():return datetime.now(timezone.utc).isoformat()
def issue(code,category,severity,message,**details):return Issue(code,category,severity,message,now(),details,actionable=severity==Status.ALERT,auto_repair_allowed=code in {"forward_service_down","forward_checkpoint_stale"})

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
    def _json(self,name,issues):
        path=self.root/self.config["paths"][name]
        try:return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:issues.append(issue(f"missing_{name}","HISTORICAL",Status.ALERT,"required artifact is missing",path=str(path)));return None
        except Exception as exc:issues.append(issue(f"malformed_{name}","HISTORICAL",Status.BLOCKED,"artifact is not parseable",error=type(exc).__name__));return None
    def _historical(self,issues):
        plan=self._json("plan",issues);boundary=self._json("boundary",issues);manifest=self._json("manifest",issues)
        if plan and plan.get("research_plan_identity") is None:issues.append(issue("frozen_plan_drift","HISTORICAL",Status.BLOCKED,"frozen plan identity absent"))
        if boundary and boundary.get("status")!="LOCKED":issues.append(issue("research_boundary_drift","HISTORICAL",Status.BLOCKED,"research boundary is not locked"))
        return plan,boundary,manifest
    def _service(self,key,issues):
        unit=self.config["services"][key];row=self.probe.service(unit)
        if row.get("ActiveState")!="active":issues.append(issue(f"{key}_service_down",key.upper(),Status.ALERT,"service is not active",unit=unit,state=row.get("ActiveState")))
        return row
    def _forward(self,plan,issues):
        service=self._service("forward",issues);checkpoint=self._json("forward_checkpoint",issues)
        if not checkpoint:return service,None
        if checkpoint.get("research_plan_identity")!=plan.get("research_plan_identity"):
            issues.append(issue("frozen_plan_drift","CROSS_CHAIN",Status.BLOCKED,"forward checkpoint plan mismatch"))
        if checkpoint.get("forward_research_only") is not True or checkpoint.get("oos_allowed") is not False:
            issues.append(issue("forward_authority_invalid","FORWARD",Status.BLOCKED,"forward authority boundary invalid"))
        path=self.root/self.config["paths"]["forward_checkpoint"]
        if path.exists() and now_timestamp(path)>self.config["thresholds"]["checkpoint_age_seconds"]:issues.append(issue("forward_checkpoint_stale","FORWARD",Status.ALERT,"forward checkpoint is stale",unit=self.config["services"]["forward"]))
        return service,checkpoint
    def _demo(self,issues):
        service=self._service("demo",issues);checkpoint=self._json("demo_checkpoint",issues)
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
        signals=self.root/self.config["paths"]["forward_signals"]
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
            action=self.recovery.consider(item,state) if not shadow else "SHADOW_ONLY";actions.append({"fingerprint":item.fingerprint,"action":action})
            if item.severity in {Status.ALERT,Status.BLOCKED} and self.state.notify_once(item.fingerprint,timestamp):
                self.notifier.notify(f"QuantBot {item.severity.value}: {item.code}")
            if action=="REPAIRED":self.notifier.notify(f"QuantBot recovery: {item.code}")
        return {"schema_version":"quantbot-unattended-report-v1","timestamp":timestamp,"overall":overall(issues).value,"issues":[item.as_dict() for item in issues],"actions":actions,"shadow":bool(shadow),"services":{"forward":forward_service,"demo":demo_service},"host":host,"identities":{"research_plan_identity":(plan or {}).get("research_plan_identity"),"forward_checkpoint_plan":(forward or {}).get("research_plan_identity")}}

def now_timestamp(path):
    return max(0.0,datetime.now(timezone.utc).timestamp()-Path(path).stat().st_mtime)
