from __future__ import annotations
from .models import Issue

NEVER_REPAIR={"demo_fail_closed","demo_reconciliation_ambiguity","deployment_identity_drift","frozen_plan_drift","research_boundary_drift","unknown_exception"}

class RecoveryController:
    """Policy decision and adapter call are separate so attempts are durable first."""
    def __init__(self,config,adapter):self.config,self.adapter=config,adapter
    def claim(self,issue:Issue,state_store,lifecycle_id,timestamp):
        policy=self.config["recovery"]
        if not policy.get("auto_repair_enabled",False) or issue.code in NEVER_REPAIR or not issue.auto_repair_allowed:return "SHADOW_ONLY"
        return state_store.claim_repair(fingerprint=issue.fingerprint,lifecycle_id=lifecycle_id,timestamp=timestamp,window_seconds=int(policy["repair_window_seconds"]),threshold=int(policy.get("consecutive_threshold",2)),max_repairs=int(policy.get("max_repairs_per_window",2)))
    def execute(self,issue):self.adapter.restart(issue.details["unit"])
