from __future__ import annotations
import json, multiprocessing, os, tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from pathlib import Path
from quantbot.unattended.config import load
from quantbot.unattended.models import Issue,Status
from quantbot.unattended.state import StateStore
from quantbot.unattended.supervisor import UnattendedSupervisor, SystemProbe
from quantbot.unattended.notifications import NotificationSink
from quantbot.demo_execution.core import identity

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
def signal_row(index,created):
 return {"signal_identity":f"{index:064x}","symbol":"BTCUSDT","direction":"LONG","signal_timestamp":created.isoformat(),"model_id":"synthetic-model","declaration_identity":"d"*64,"created_at":created.isoformat()}
def write_signals(root,through,created):
 path=root/"data/forward_research_3a457e6/signals/2026-09-15/signals.jsonl";path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text("\n".join(json.dumps(signal_row(index,created),sort_keys=True) for index in range(through+1))+"\n",encoding="utf-8")
 return path
def append_signal(root,index,created):
 path=root/"data/forward_research_3a457e6/signals/2026-09-15/signals.jsonl"
 with path.open("a",encoding="utf-8") as out:out.write(json.dumps(signal_row(index,created),sort_keys=True)+"\n")
 return f"signals/2026-09-15/signals.jsonl:{index}"
def recovery_evidence(epoch_root,checkpoint,forward_root,created):
 row={"schema_version":"quantbot-demo-recovery-v1","predecessor_epoch":"demo_execution_44c630d_day2","predecessor_cursor":"signals/2026-09-15/signals.jsonl:15967","source_forward_identity":checkpoint["source_forward_identity"],"forward_root":str(forward_root.resolve()),"target_git_commit":checkpoint["git_commit"],"target_config_identity":checkpoint["config_identity"],"recovery_reason":"synthetic_safe_recovery","old_intents_not_replayed":True}
 row["recovery_identity"]=identity(row);row["created_at"]=created.isoformat()
 path=epoch_root/"recovery/2026-09-15/recovery.jsonl";path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(row,sort_keys=True)+"\n",encoding="utf-8")
 return path,row
def production_probe_config():return load("config/unattended_supervisor.json")
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
 store=StateStore(Path(path),{"sent_notifications":64,"recoveries":64});stamp="2026-01-01T00:00:00+00:00";store.queue_notification(f"concurrent:{index}","ALERT",f"synthetic-{index}",stamp);store.record_repair_outcome(fingerprint=f"f{index}",lifecycle_id=f"l{index}",timestamp=stamp,status="ATTEMPT",window_seconds=3600)
def repair_claim_worker(path,queue,fingerprint,lifecycle_id):
 queue.put(StateStore(Path(path)).claim_repair(fingerprint=fingerprint,lifecycle_id=lifecycle_id,timestamp="2026-01-01T00:00:00+00:00",window_seconds=3600,threshold=1,max_repairs=1))
def notification_claim_worker(path,queue,index):
 row=StateStore(Path(path)).claim_notification("shared","2026-01-01T00:00:00+00:00");queue.put(row["claim_token"] if row else None)
def main():
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp);base(root);probe=Probe();sink=Sink();adapter=Recovery();supervisor=runner(root,probe,sink,adapter,auto=True);stale(root)
  # Production declarations target the recovery epoch, never frozen Day-2.
  production=production_probe_config();assert production["production"]["demo"]["data_root"]=="data/demo_execution_c60a235_recovery1" and "44c630d_day2" not in production["production"]["demo"]["data_root"]
  epoch_root=root/production["production"]["demo"]["data_root"];forward_root=root/"data/forward_research_3a457e6";recovery_start=datetime.now(timezone.utc)-timedelta(minutes=10);historical=recovery_start-timedelta(seconds=1);cursor="signals/2026-09-15/signals.jsonl:15967";write_signals(root,28697,historical)
  checkpoint={"schema_version":"quantbot-demo-checkpoint-v1","demo_epoch":epoch_root.name,"git_commit":"a"*40,"config_identity":"c"*64,"source_forward_identity":identity({"root":str(forward_root.resolve())}),"last_signal_cursor":cursor,"orders_seen":0,"fail_closed":False,"reconciliation":{}}
  write(root,production["production"]["demo"]["checkpoint"],checkpoint);recovery_path,recovery=recovery_evidence(epoch_root,checkpoint,forward_root,recovery_start);real_probe=SystemProbe(root,production);assert real_probe.demo_nonterminals()==[];(epoch_root/"runtime").mkdir(parents=True,exist_ok=True);(epoch_root/"runtime/ledger.json").write_text(json.dumps({"old":{"state":"REJECTED_POLICY","events":[{"at":recovery_start.isoformat()}]}}),encoding="utf-8")
  # ForwardSignalReader's canonical marker semantics begin immediately after inherited :15967.
  assert real_probe.demo_consumption()=={"forward_new":False,"cursor_stuck":False,"age_seconds":0} and real_probe.demo_nonterminals()==[]
  post_marker=append_signal(root,28698,datetime.now(timezone.utc)-timedelta(minutes=6));lag=real_probe.demo_consumption();assert lag["forward_new"] and lag["cursor_stuck"] and lag["age_seconds"]>300
  checkpoint["last_signal_cursor"]=post_marker;write(root,production["production"]["demo"]["checkpoint"],checkpoint);assert real_probe.demo_consumption()=={"forward_new":False,"cursor_stuck":False,"age_seconds":0}
  # Missing, malformed, and conflicting recovery evidence must never default healthy.
  recovery_path.unlink()
  try:real_probe.demo_consumption();raise AssertionError("missing_recovery_evidence_healthy")
  except RuntimeError:pass
  recovery_path.write_text("not-json\n",encoding="utf-8")
  try:real_probe.demo_consumption();raise AssertionError("malformed_recovery_evidence_healthy")
  except RuntimeError:pass
  recovery_path.write_text(json.dumps(recovery,sort_keys=True)+"\n",encoding="utf-8");conflict=epoch_root/"recovery/2026-09-16/recovery.jsonl";conflict.parent.mkdir(parents=True,exist_ok=True);conflict.write_text(json.dumps(recovery,sort_keys=True)+"\n",encoding="utf-8")
  try:real_probe.demo_consumption();raise AssertionError("ambiguous_recovery_evidence_healthy")
  except RuntimeError:pass
  conflict.unlink()
  (epoch_root/"runtime/ledger.json").write_text(json.dumps({"open":{"execution_intent_identity":"intent","state":"VALIDATED","events":[{"at":(datetime.now(timezone.utc)-timedelta(minutes=6)).isoformat()}]}}),encoding="utf-8");assert real_probe.demo_nonterminals()[0]["state"]=="VALIDATED"
  checkpoint["last_signal_cursor"]="malformed";write(root,production["production"]["demo"]["checkpoint"],checkpoint)
  try:real_probe.demo_consumption();raise AssertionError("malformed_cursor_healthy")
  except RuntimeError:pass
  (epoch_root/"runtime/ledger.json").write_text("not-json",encoding="utf-8")
  try:real_probe.demo_nonterminals();raise AssertionError("malformed_ledger_healthy")
  except RuntimeError:pass
  # Telegram transport is disabled by default; enabled delivery is mock-only.
  transport_calls=[]
  class Response:
   status=200
   def close(self):pass
  disabled=NotificationSink(environ={"TG_ENABLED":"false"},transport=lambda *_args,**_kwargs:transport_calls.append(1));disabled.notify("safe");assert transport_calls==[]
  enabled_env={"TG_ENABLED":"true","TG_BOT_TOKEN":"secret-token","TG_CHAT_ID":"secret-chat"}
  enabled=NotificationSink(environ=enabled_env,transport=lambda request,timeout:(transport_calls.append((request.full_url,request.data,timeout)) or Response()));enabled.notify("safe");assert len(transport_calls)==1 and b"safe" in transport_calls[0][1] and b"secret-token" not in transport_calls[0][1]
  try:NotificationSink(environ=enabled_env,transport=lambda *_args,**_kwargs:(_ for _ in ()).throw(OSError("synthetic_tg_failure"))).notify("safe");raise AssertionError("tg_failure_not_retryable")
  except OSError:pass
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
  outbox_root=root/"outbox";base(outbox_root);stale(outbox_root);flaky=FlakySink();outbox=runner(outbox_root,Probe(),flaky,Recovery(),auto=False);outbox.run_once(shadow=True);pending=StateStore(outbox_root/"state.json").load()["notifications"];assert len(pending)==1 and next(iter(pending.values()))["state"]=="CLAIMED";StateStore(outbox_root/"state.json")._mutate(lambda state:next(iter(state["notifications"].values())).update({"lease_until":"2020-01-01T00:00:00+00:00"}))
  outbox=runner(outbox_root,Probe(),flaky,Recovery(),auto=False);outbox.run_once(shadow=True);sent=StateStore(outbox_root/"state.json").load()["notifications"];assert next(iter(sent.values()))["state"]=="SENT" and len(flaky.messages)==1;outbox.run_once(shadow=True);assert len(flaky.messages)==1
  outbox.config["thresholds"]["checkpoint_age_seconds"]=999999;os.utime(outbox_root/"data/forward_research/checkpoints/runtime.json",None);flaky.failures=1;outbox.run_once(shadow=True);assert any(row["kind"]=="RECOVERED" and row["state"]=="CLAIMED" for row in StateStore(outbox_root/"state.json").load()["notifications"].values());StateStore(outbox_root/"state.json")._mutate(lambda state:[row.update({"lease_until":"2020-01-01T00:00:00+00:00"}) for row in state["notifications"].values() if row.get("kind")=="RECOVERED"]);outbox.run_once(shadow=True);assert sum(message=="QuantBot RECOVERED" for message in flaky.messages)==1
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
   key=f"sent:{index}";created=f"2026-01-01T00:00:{index:02d}+00:00";retained.queue_notification(key,"ALERT","safe",created);claim=retained.claim_notification(key,created);retained.mark_sent(key,claim["claim_token"],created)
  retained.queue_notification("pending","ALERT","safe",stamp);active=Issue("active","FORWARD",Status.ALERT,"safe",stamp,{},True,True);retained.observe([active],stamp,3600);kept=retained.load();assert sum(row["state"]=="SENT" for row in kept["notifications"].values())<=3 and kept["notifications"]["pending"]["state"]=="PENDING" and active.fingerprint in kept["issues"]
  # Process-level writes retain every independent intent and attempt without shared tmp collision.
  concurrent_path=root/"concurrent.json";workers=[multiprocessing.Process(target=concurrent_mutation,args=(str(concurrent_path),index)) for index in range(8)]
  [worker.start() for worker in workers];[worker.join(20) for worker in workers];assert all(worker.exitcode==0 for worker in workers);concurrent=StateStore(concurrent_path).load();assert len(concurrent["notifications"])==8 and len(concurrent["repairs"])==8
  # Exactly one process can reserve a repair or delivery claim; stale delivery claim is recoverable.
  claim_path=root/"repair_claim.json";claim_store=StateStore(claim_path);claim_issue=Issue("shared","FORWARD",Status.ALERT,"safe","2026-01-01T00:00:00+00:00",{},True,True);claim_state=claim_store.observe([claim_issue],"2026-01-01T00:00:00+00:00",3600);claim_fingerprint=claim_issue.fingerprint;claim_lifecycle=claim_state["issues"][claim_fingerprint]["lifecycle_id"];queue=multiprocessing.Queue();workers=[multiprocessing.Process(target=repair_claim_worker,args=(str(claim_path),queue,claim_fingerprint,claim_lifecycle)) for _ in range(8)];[worker.start() for worker in workers];[worker.join(20) for worker in workers];assert all(worker.exitcode==0 for worker in workers);claims=[queue.get() for _ in workers];assert claims.count("REPAIR_CLAIMED")==1 and sum(row.get("status")=="ATTEMPT" for row in claim_store.load()["repairs"])==1
  notification_path=root/"notification_claim.json";notification_store=StateStore(notification_path);notification_store.queue_notification("shared","ALERT","safe","2026-01-01T00:00:00+00:00");queue=multiprocessing.Queue();workers=[multiprocessing.Process(target=notification_claim_worker,args=(str(notification_path),queue,index)) for index in range(8)];[worker.start() for worker in workers];[worker.join(20) for worker in workers];tokens=[queue.get() for _ in workers];token=next(row for row in tokens if row);assert all(worker.exitcode==0 for worker in workers) and sum(bool(row) for row in tokens)==1 and notification_store.mark_sent("shared",token,"2026-01-01T00:00:00+00:00") and notification_store.claim_notification("shared","2026-01-01T00:02:00+00:00") is None
  notification_store.queue_notification("stale","ALERT","safe","2026-01-01T00:00:00+00:00");first_claim=notification_store.claim_notification("stale","2026-01-01T00:00:00+00:00");second_claim=notification_store.claim_notification("stale","2026-01-01T00:02:00+00:00");assert first_claim and second_claim and first_claim["claim_token"]!=second_claim["claim_token"]
  # Temp fsync is part of every successful durable write path.
  durable_path=root/"durable.json"
  with patch("quantbot.unattended.state.os.fsync",wraps=os.fsync) as synced:StateStore(durable_path).queue_notification("fsync","ALERT","safe","2026-01-01T00:00:00+00:00");assert synced.called
  try:
   with patch("quantbot.unattended.state.os.fsync",side_effect=OSError("synthetic_fsync_failure")):StateStore(root/"fsync_failure.json").queue_notification("fsync","ALERT","safe","2026-01-01T00:00:00+00:00")
   raise AssertionError("fsync_failure_was_accepted")
  except OSError:pass
  assert load(None)["state_path"].startswith("runtime/") and "server_local_audit" not in load(None)["state_path"]
  assert StateStore(root/"state.json").load()["schema_version"]=="quantbot-unattended-state-v1"
 print("UNATTENDED_HEALTHY_ALL_CHAIN=PASS")
 print("CONSECUTIVE_STRIKES=PASS");print("REPAIR_STATE_DURABLE=PASS");print("REPAIR_BUDGET_RESTART_SAFE=PASS");print("REPAIR_FAILURE_DURABLE=PASS")
 print("RECOVERED_EXACTLY_ONCE=PASS");print("FAULT_RECURRENCE_NEW_LIFECYCLE=PASS");print("RECURRENCE_CANNOT_BYPASS_BUDGET=PASS");print("REPAIR_SUCCESS_NOT_EQUAL_RECOVERED=PASS")
 print("SHADOW_NEVER_REPAIRS=PASS");print("STATE_ATOMIC_WRITE=PASS");print("SECRET_REDACTION=PASS")
 print("NOTIFICATION_DURABLE_AT_LEAST_ONCE=PASS");print("REPAIR_WINDOW_TIME_FAIL_SAFE=PASS")
 print("STATE_CROSS_PROCESS_LOCKING=PASS");print("STATE_RETENTION_BOUNDED=PASS");print("REPAIR_WINDOW_EXPLICIT_REARM=PASS")
 print("ATOMIC_REPAIR_CLAIM=PASS");print("ATOMIC_NOTIFICATION_CLAIM=PASS");print("DURABLE_WRITE_FSYNC=PASS");print("RUNTIME_STATE_PATH_ISOLATED=PASS")
 print("RECOVERY1_CONFIG_BINDING=PASS");print("FROZEN_DAY2_NOT_PRODUCTION_TARGET=PASS")
 print("DEMO_NONTERMINAL_READ_ONLY_PROBE=PASS");print("DEMO_CONSUMPTION_RECOVERY_EPOCH_SEMANTICS=PASS");print("DEMO_CONSUMPTION_MALFORMED_FAIL_VISIBLE=PASS")
 print("TG_DISABLED_NO_SEND=PASS");print("TG_ENABLED_MOCKED_SUCCESS=PASS");print("TG_MOCKED_FAILURE_RETRYABLE=PASS")
 print("OOS_READS=0");print("REAL_SYSTEMCTL_MUTATIONS=0");print("LIVE_ORDER_PLACEMENT=0")
if __name__=="__main__":main()
