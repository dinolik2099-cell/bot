from __future__ import annotations
from .models import Issue

NEVER_REPAIR={"demo_fail_closed","demo_reconciliation_ambiguity","deployment_identity_drift","frozen_plan_drift","research_boundary_drift","unknown_exception"}

class RecoveryController:
    """Policy decision and adapter call are separate so attempts are durable first."""
    def __init__(self,config,adapter):self.config,self.adapter=config,adapter
    def decide(self,issue:Issue,state,lifecycle_id):
        policy=self.config["recovery"]
        if not policy.get("auto_repair_enabled",False) or issue.code in NEVER_REPAIR or not issue.auto_repair_allowed:return "SHADOW_ONLY"
        if state.get("repair_window_untrusted") is True:return "AUTO_REPAIR_LOCKED"
        row=state.get("issues",{}).get(issue.fingerprint,{})
        if int(row.get("count",0))<int(policy.get("consecutive_threshold",2)):return "AWAIT_CONFIRMATION"
        repairs=state.get("repairs",[])
        if sum(item.get("status")=="ATTEMPT" for item in repairs)>=int(policy.get("max_repairs_per_window",2)):return "AUTO_REPAIR_LOCKED"
        if any(item.get("fingerprint")==issue.fingerprint and item.get("lifecycle_id")==lifecycle_id for item in repairs):return "AWAIT_HEALTH_CONFIRMATION"
        return "REPAIR_ELIGIBLE"
    def execute(self,issue):self.adapter.restart(issue.details["unit"])
