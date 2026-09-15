from __future__ import annotations
from .models import Issue

NEVER_REPAIR={"demo_fail_closed","demo_reconciliation_ambiguity","deployment_identity_drift","frozen_plan_drift","research_boundary_drift","unknown_exception"}

class RecoveryController:
    def __init__(self,config,adapter):self.config,self.adapter=config,adapter
    def consider(self,issue:Issue,state):
        policy=self.config["recovery"]
        if not policy.get("auto_repair_enabled",False) or issue.code in NEVER_REPAIR or not issue.auto_repair_allowed:return "SHADOW_ONLY"
        count=state.get("issues",{}).get(issue.fingerprint,{}).get("count",0)
        if count<int(policy.get("consecutive_threshold",2)):return "AWAIT_CONFIRMATION"
        repairs=state.get("repairs",[])
        if len(repairs)>=int(policy.get("max_repairs_per_window",2)):return "AUTO_REPAIR_LOCKED"
        self.adapter.restart(issue.details["unit"]);repairs.append({"fingerprint":issue.fingerprint,"unit":issue.details["unit"]});state["repairs"]=repairs;return "REPAIRED"
