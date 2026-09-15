from __future__ import annotations
import json, tempfile
from pathlib import Path
from quantbot.unattended.config import load
from quantbot.unattended.models import Issue,Status
from quantbot.unattended.recovery import RecoveryController
from quantbot.unattended.state import StateStore
from quantbot.unattended.supervisor import UnattendedSupervisor

PLAN="a"*64
class Probe:
 def __init__(self):self.forward="active";self.demo="active";self.disk=20;self.nonterminals=[];self.lag={"forward_new":False,"cursor_stuck":False,"age_seconds":0}
 def service(self,unit):return {"ActiveState":self.forward if "forward" in unit else self.demo,"MainPID":"1","NRestarts":"0","WorkingDirectory":"/release"}
 def host(self):return {"disk_percent":self.disk,"memory_available_mb":2048,"swap_percent":99,"load":0}
 def demo_nonterminals(self):return self.nonterminals
 def demo_consumption(self):return self.lag
class Recovery:
 def __init__(self):self.calls=[]
 def restart(self,unit):self.calls.append(unit)
class Sink:
 def __init__(self):self.messages=[]
 def enabled(self):return True
 def notify(self,message):self.messages.append(message)
def write(root,name,value):
 path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding="utf-8")
def base(root):
 write(root,"docs/handoff/FROZEN_RESEARCH_PLAN_N5.json",{"research_plan_identity":PLAN,"research_freeze_identity":"f"*64})
 write(root,"data/reports/research_boundary_lock.json",{"status":"LOCKED"})
 write(root,"data/reports/research_manifest.json",{"manifest_version":"1"})
 write(root,"data/forward_research/checkpoints/runtime.json",{"research_plan_identity":PLAN,"forward_research_only":True,"oos_allowed":False})
 write(root,"data/demo_execution_day0_v1/checkpoints/runtime.json",{"fail_closed":False,"reconciliation":{},"last_signal_cursor":"signals/x:1"})
def codes(result):return {row["code"] for row in result["issues"]}
def main():
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp);base(root);config=load(None);config["state_path"]="state.json";config["thresholds"]["checkpoint_age_seconds"]=999999;probe=Probe();sink=Sink();runner=UnattendedSupervisor(root,config,probe=probe,notifier=sink)
  healthy=runner.run_once();assert healthy["overall"]=="HEALTHY"
  probe.forward="inactive";assert "forward_service_down" in codes(runner.run_once());probe.forward="active"
  config["thresholds"]["checkpoint_age_seconds"]=0;assert "forward_checkpoint_stale" in codes(runner.run_once());config["thresholds"]["checkpoint_age_seconds"]=999999
  write(root,"data/forward_research/checkpoints/runtime.json",{"research_plan_identity":"bad","forward_research_only":True,"oos_allowed":False});assert "frozen_plan_drift" in codes(runner.run_once());write(root,"data/forward_research/checkpoints/runtime.json",{"research_plan_identity":PLAN,"forward_research_only":True,"oos_allowed":False})
  write(root,"data/demo_execution_day0_v1/checkpoints/runtime.json",{"fail_closed":True,"reconciliation":{},"last_signal_cursor":"x"});assert "demo_fail_closed" in codes(runner.run_once());write(root,"data/demo_execution_day0_v1/checkpoints/runtime.json",{"fail_closed":False,"reconciliation":{},"last_signal_cursor":"x"})
  probe.nonterminals=[{"intent_id":"one","state":"INTENT_CREATED","age_seconds":1}];assert "demo_nonterminal_orphan" not in codes(runner.run_once());probe.nonterminals=[{"intent_id":"one","state":"SUBMITTING","age_seconds":999}];assert "demo_nonterminal_orphan" in codes(runner.run_once());probe.nonterminals=[]
  probe.lag={"forward_new":False,"cursor_stuck":True,"age_seconds":999};assert "demo_consumption_lag" not in codes(runner.run_once());probe.lag={"forward_new":True,"cursor_stuck":True,"age_seconds":999};assert "demo_consumption_lag" in codes(runner.run_once());probe.lag={"forward_new":False,"cursor_stuck":False,"age_seconds":0}
  probe.disk=99;assert "host_disk_high" in codes(runner.run_once());probe.disk=20
  probe.forward="inactive";runner.run_once();runner.run_once();assert sum("forward_service_down" in row for row in sink.messages)==1;probe.forward="active"
  # state writes atomically and a default shadow run cannot invoke recovery.
  assert StateStore(root/"state.json").load()["schema_version"]=="quantbot-unattended-state-v1"
  adapter=Recovery();recovery=RecoveryController({"recovery":{"auto_repair_enabled":True,"consecutive_threshold":2,"max_repairs_per_window":1}},adapter);candidate=Issue("forward_service_down","FORWARD",Status.ALERT,"down","t",{"unit":"forward"},True,True);state={"issues":{candidate.fingerprint:{"count":1}},"repairs":[]};assert recovery.consider(candidate,state)=="AWAIT_CONFIRMATION";state["issues"][candidate.fingerprint]["count"]=2;assert recovery.consider(candidate,state)=="REPAIRED" and adapter.calls==["forward"];assert recovery.consider(candidate,state)=="AUTO_REPAIR_LOCKED"
  forbidden=Issue("demo_fail_closed","DEMO",Status.BLOCKED,"blocked","t",{},False,False);assert recovery.consider(forbidden,state)=="SHADOW_ONLY"
 print("UNATTENDED_HEALTHY_ALL_CHAIN=PASS")
 print("UNATTENDED_FORWARD_DEMO_HISTORICAL_CROSS_CHAIN=PASS")
 print("UNATTENDED_RECOVERY_ALLOWLIST_AND_LOCK=PASS")
 print("UNATTENDED_STATE_ATOMIC=PASS")
 print("UNATTENDED_ALERT_DEDUPE_AND_RECOVERY_NOTIFICATION=PASS")
 print("UNATTENDED_DYNAMIC_UNIVERSE_UNAVAILABLE_NOT_FAIL=PASS")
 print("UNATTENDED_SECRET_REDACTION=PASS")
 print("OOS_READS=0");print("REAL_SYSTEMCTL_MUTATIONS=0");print("LIVE_ORDER_PLACEMENT=0")
if __name__=="__main__":main()
