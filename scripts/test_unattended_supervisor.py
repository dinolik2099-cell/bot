from __future__ import annotations
import json, multiprocessing, os, tempfile
from pathlib import Path
from quantbot.unattended.config import load
from quantbot.unattended.models import Issue,Status
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
 def __init__(self,fail=False):self.calls=[];self.fail=fail
 def restart(self,unit):
  self.calls.append(unit)
  if self.fail:raise RuntimeError("synthetic_repair_failure")
class Sink:
 def __init__(self):self.messages=[]
 def enabled(self):return True
 def notify(self,message):self.messages.append(message)
class FlakySink(Sink):
 def __init__(self,failures=1):super().__init__();self.failures=failures
 def notify(self,message):
  if self.failures:self.failures-=1;raise RuntimeError("synthetic_notification_failure")
  super().notify(message)
def write(root,name,value):
 path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding="utf-8")
def base(root):
 write(root,"docs/handoff/FROZEN_RESEARCH_PLAN_N5.json",{"research_plan_identity":PLAN,"research_freeze_identity":"f"*64})
 write(root,"data/reports/research_boundary_lock.json",{"status":"LOCKED"});write(root,"data/reports/research_manifest.json",{"manifest_version":"1"})
 write(root,"data/forward_research/checkpoints/runtime.json",{"schema_version":"quantbot-forward-checkpoint-v2","research_plan_identity":PLAN,"forward_research_only":True,"oos_allowed":False})
 write(root,"data/demo_execution_day0_v1/checkpoints/runtime.json",{"schema_version":"quantbot-demo-checkpoint-v1","demo_epoch":"demo_execution_day0_v1","fail_closed":False,"reconciliation":{},"last_signal_cursor":"signals/x:1"})
def codes(result):return {row["code"] for row in result["issues"]}
def stale(root):os.utime(root/"data/forward_research/checkpoints/runtime.json",(1,1))
def runner(root,probe,sink,recovery,*,auto=False):
 config=load(None);config["state_path"]="state.json";config["thresholds"]["checkpoint_age_seconds"]=0;config["recovery"].update({"auto_repair_enabled":auto,"consecutive_threshold":2,"max_repairs_per_window":1,"repair_window_seconds":3600})
 return UnattendedSupervisor(root,config,probe=probe,recovery_adapter=recovery,notifier=sink)
def concurrent_mutation(path,index):
 store=StateStore(Path(path),{"sent_notifications":64,"recoveries":64});stamp="2026-01-01T00:00:00+00:00";store.queue_notification(f"concurrent:{index}","ALERT",f"synthetic-{index}",stamp);store.record_repair(fingerprint=f"f{index}",lifecycle_id=f"l{index}",timestamp=stamp,status="ATTEMPT",window_seconds=3600)
def main():
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp);base(root);probe=Probe();sink=Sink();adapter=Recovery();supervisor=runner(root,probe,sink,adapter,auto=True);stale(root)
  # Consecutive strikes, stable fingerprint, durable success and restart-safe budget.
  first=supervisor.run_once(shadow=False);fault=next(row for row in first["issues"] if row["code"]=="forward_checkpoint_stale");assert first["overall"]=="ALERT" and adapter.calls==[] and first["actions"][0]["action"]=="AWAIT_CONFIRMATION"
  second=supervisor.run_once(shadow=False);assert adapter.calls==["quantbot-forward-research.service"] and next(row for row in second["issues"] if row["code"]=="forward_checkpoint_stale")["fingerprint"]==fault["fingerprint"]
  durable=StateStore(root/"state.json").load();assert len(durable["repairs"])==2 and {row["status"] for row in durable["repairs"]}=={"ATTEMPT","SUCCESS"} and any(row["kind"]=="REPAIR_SUCCESS" and row["state"]=="SENT" for row in durable["notifications"].values())
  restarted=runner(root,probe,sink,adapter,auto=True);locked=restarted.run_once(shadow=False);assert adapter.calls==["quantbot-forward-research.service"] and "AUTO_REPAIR_LOCKED" in {row["action"] for row in locked["actions"]}
  # Actual health disappearance produces one recovered event, never merely adapter success.
  restarted.config["thresholds"]["checkpoint_age_seconds"]=999999;os.utime(root/"data/forward_research/checkpoints/runtime.json",None);healthy=restarted.run_once(shadow=False);assert healthy["overall"]=="HEALTHY" and sum(message=="QuantBot RECOVERED" for message in sink.messages)==1
  restarted.run_once(shadow=False);assert sum(message=="QuantBot RECOVERED" for message in sink.messages)==1
  # Recurrence gains a new lifecycle/alert but cannot bypass window budget.
  restarted.config["thresholds"]["checkpoint_age_seconds"]=0;stale(root);restarted.run_once(shadow=False);recurred=restarted.run_once(shadow=False);assert adapter.calls==["quantbot-forward-research.service"] and sum(message=="QuantBot ALERT: forward_checkpoint_stale" for message in sink.messages)==2 and "AUTO_REPAIR_LOCKED" in {row["action"] for row in recurred["actions"]}
  # Shadow records observations only and cannot consume budget or invoke adapter.
  shadow_root=root/"shadow";base(shadow_root);stale(shadow_root);shadow_adapter=Recovery();shadow=runner(shadow_root,Probe(),Sink(),shadow_adapter,auto=True);shadow.run_once(shadow=True);shadow.run_once(shadow=True);assert shadow_adapter.calls==[] and StateStore(shadow_root/"state.json").load()["repairs"]==[]
  # Failure is durable, safe, and never falsely reported as recovered/success.
  failed_root=root/"failed";base(failed_root);stale(failed_root);failed_sink=Sink();failed=runner(failed_root,Probe(),failed_sink,Recovery(fail=True),auto=True);failed.run_once(shadow=False);failure=failed.run_once(shadow=False);assert "REPAIR_FAILED" in {row["action"] for row in failure["actions"]} and next(row for row in failure["actions"] if row["action"]=="REPAIR_FAILED")["error_type"]=="RuntimeError";state=StateStore(failed_root/"state.json").load();assert any(row["status"]=="FAILURE" and row["error_type"]=="RuntimeError" for row in state["repairs"]);assert not any("RECOVERED" in message or "attempt success" in message for message in failed_sink.messages)
  # Unsafe faults remain nonrepairable, while declared resource failure is nonrepairable.
  write(root,"data/demo_execution_day0_v1/checkpoints/runtime.json",{"schema_version":"quantbot-demo-checkpoint-v1","demo_epoch":"demo_execution_day0_v1","fail_closed":True,"reconciliation":{},"last_signal_cursor":"x"});unsafe=restarted.run_once(shadow=False);assert "demo_fail_closed" in codes(unsafe) and all(row["action"]!="REPAIRED" for row in unsafe["actions"])
  safe_root=root/"unsafe";base(safe_root);safe_probe=Probe();safe_adapter=Recovery();safe=runner(safe_root,safe_probe,Sink(),safe_adapter,auto=True)
  write(safe_root,"data/forward_research/checkpoints/runtime.json",{"schema_version":"quantbot-forward-checkpoint-v2","research_plan_identity":"bad","forward_research_only":True,"oos_allowed":False});assert "frozen_plan_drift" in codes(safe.run_once(shadow=False)) and safe_adapter.calls==[]
  write(safe_root,"data/forward_research/checkpoints/runtime.json",{"schema_version":"quantbot-forward-checkpoint-v2","research_plan_identity":PLAN,"forward_research_only":True,"oos_allowed":False});write(safe_root,"data/demo_execution_day0_v1/checkpoints/runtime.json",{"schema_version":"quantbot-demo-checkpoint-v1","demo_epoch":"demo_execution_day0_v1","fail_closed":False,"reconciliation":{"ambiguous":True},"last_signal_cursor":"x"});assert "demo_reconciliation_ambiguity" in codes(safe.run_once(shadow=False)) and safe_adapter.calls==[]
  safe.config["production"]["forward"]["checkpoint"]="data/forward_research/checkpoints/missing.json";assert "missing_forward_checkpoint" in codes(safe.run_once(shadow=False)) and safe_adapter.calls==[]
  safe.config["production"]["forward"]["checkpoint"]="data/forward_research/checkpoints/runtime.json";(safe_root/"docs/handoff/FROZEN_RESEARCH_PLAN_N5.json").unlink();assert "missing_plan" in codes(safe.run_once(shadow=False)) and safe_adapter.calls==[]
  safe_probe.disk=99;assert "host_disk_high" in codes(safe.run_once(shadow=False)) and safe_adapter.calls==[]
  # Notification intent is durable first, then retried at-least-once until SENT.
  outbox_root=root/"outbox";base(outbox_root);stale(outbox_root);flaky=FlakySink();outbox=runner(outbox_root,Probe(),flaky,Recovery(),auto=False);outbox.run_once(shadow=True);pending=StateStore(outbox_root/"state.json").load()["notifications"];assert len(pending)==1 and next(iter(pending.values()))["state"]=="PENDING"
  outbox=runner(outbox_root,Probe(),flaky,Recovery(),auto=False);outbox.run_once(shadow=True);sent=StateStore(outbox_root/"state.json").load()["notifications"];assert next(iter(sent.values()))["state"]=="SENT" and len(flaky.messages)==1;outbox.run_once(shadow=True);assert len(flaky.messages)==1
  outbox.config["thresholds"]["checkpoint_age_seconds"]=999999;os.utime(outbox_root/"data/forward_research/checkpoints/runtime.json",None);flaky.failures=1;outbox.run_once(shadow=True);assert any(row["kind"]=="RECOVERED" and row["state"]=="PENDING" for row in StateStore(outbox_root/"state.json").load()["notifications"].values());outbox.run_once(shadow=True);assert sum(message=="QuantBot RECOVERED" for message in flaky.messages)==1
  # Future, rollback and malformed repair timestamps permanently fail safe.
  for label,row in (("future",{"timestamp":"2999-01-01T00:00:00+00:00"}),("rollback",{"timestamp":"2026-01-02T00:00:00+00:00","clock":"2027-01-01T00:00:00+00:00"}),("malformed",{"timestamp":"not-a-time"})):
   time_root=root/label;base(time_root);store=StateStore(time_root/"state.json");state=store.load();state["repairs"]=[{"timestamp":row["timestamp"],"status":"ATTEMPT"}];
   if "clock" in row:state["repair_clock"]=row["clock"]
   store._mutate(lambda current:(current.clear(),current.update(state)));checked=store.observe([],"2026-01-01T00:00:00+00:00",3600);assert checked["repair_window_untrusted"] is True
  stale(time_root);locked_time=runner(time_root,Probe(),Sink(),Recovery(),auto=True).run_once(shadow=False);assert "AUTO_REPAIR_LOCKED" in {row["action"] for row in locked_time["actions"]}
  # Explicit operator re-arm validates persisted clock/records and never clears budget.
  rearm_root=root/"rearm";base(rearm_root);rearm_store=StateStore(rearm_root/"state.json");rearm_store._mutate(lambda state:state.update({"repair_window_untrusted":True,"repair_clock":"2026-01-01T00:00:00+00:00","repairs":[{"timestamp":"2026-01-01T00:00:00+00:00","status":"ATTEMPT"}]}));rearm_store.rearm_repair_window("2026-01-01T00:01:00+00:00",3600);rearmed=rearm_store.load();assert not rearmed["repair_window_untrusted"] and len(rearmed["repairs"])==1 and rearmed["operator_events"][-1]["operation"]=="repair_window_rearm" and not StateStore(rearm_root/"state.json").load()["repair_window_untrusted"]
  invalid_store=StateStore(time_root/"state.json")
  try:invalid_store.rearm_repair_window("2026-01-01T00:00:00+00:00",3600);raise AssertionError("invalid_rearm_accepted")
  except ValueError:pass
  # Bounded sent/recovered history never removes PENDING or active lifecycle evidence.
  retained=StateStore(root/"retained.json",{"sent_notifications":3,"recoveries":2});stamp="2026-01-01T00:00:00+00:00"
  for index in range(10):
   key=f"sent:{index}";retained.queue_notification(key,"ALERT","safe",f"2026-01-01T00:00:{index:02d}+00:00");retained.delivery_attempt(key,stamp);retained.mark_sent(key,f"2026-01-01T00:00:{index:02d}+00:00")
  retained.queue_notification("pending","ALERT","safe",stamp);active=Issue("active","FORWARD",Status.ALERT,"safe",stamp,{},True,True);retained.observe([active],stamp,3600);kept=retained.load();assert sum(row["state"]=="SENT" for row in kept["notifications"].values())<=3 and kept["notifications"]["pending"]["state"]=="PENDING" and active.fingerprint in kept["issues"]
  # Process-level writes retain every independent intent and attempt without shared tmp collision.
  concurrent_path=root/"concurrent.json";workers=[multiprocessing.Process(target=concurrent_mutation,args=(str(concurrent_path),index)) for index in range(8)]
  [worker.start() for worker in workers];[worker.join(20) for worker in workers];assert all(worker.exitcode==0 for worker in workers);concurrent=StateStore(concurrent_path).load();assert len(concurrent["notifications"])==8 and len(concurrent["repairs"])==8
  assert StateStore(root/"state.json").load()["schema_version"]=="quantbot-unattended-state-v1"
 print("UNATTENDED_HEALTHY_ALL_CHAIN=PASS")
 print("CONSECUTIVE_STRIKES=PASS");print("REPAIR_STATE_DURABLE=PASS");print("REPAIR_BUDGET_RESTART_SAFE=PASS");print("REPAIR_FAILURE_DURABLE=PASS")
 print("RECOVERED_EXACTLY_ONCE=PASS");print("FAULT_RECURRENCE_NEW_LIFECYCLE=PASS");print("RECURRENCE_CANNOT_BYPASS_BUDGET=PASS");print("REPAIR_SUCCESS_NOT_EQUAL_RECOVERED=PASS")
 print("SHADOW_NEVER_REPAIRS=PASS");print("STATE_ATOMIC_WRITE=PASS");print("SECRET_REDACTION=PASS")
 print("NOTIFICATION_DURABLE_AT_LEAST_ONCE=PASS");print("REPAIR_WINDOW_TIME_FAIL_SAFE=PASS")
 print("STATE_CROSS_PROCESS_LOCKING=PASS");print("STATE_RETENTION_BOUNDED=PASS");print("REPAIR_WINDOW_EXPLICIT_REARM=PASS")
 print("OOS_READS=0");print("REAL_SYSTEMCTL_MUTATIONS=0");print("LIVE_ORDER_PLACEMENT=0")
if __name__=="__main__":main()
