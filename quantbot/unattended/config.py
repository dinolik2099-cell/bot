from __future__ import annotations
import json
from pathlib import Path

DEFAULT={"schema_version":"quantbot-unattended-supervisor-v1","auto_repair_enabled":False,
 "state_path":"server_local_audit/unattended/state.json","thresholds":{"checkpoint_age_seconds":300,"demo_consumption_lag_seconds":300,"disk_percent":90,"memory_available_mb":256,"swap_percent":90},
 "recovery":{"auto_repair_enabled":False,"consecutive_threshold":2,"max_repairs_per_window":2},
 "paths":{"plan":"docs/handoff/FROZEN_RESEARCH_PLAN_N5.json","boundary":"data/reports/research_boundary_lock.json","manifest":"data/reports/research_manifest.json","forward_checkpoint":"data/forward_research/checkpoints/runtime.json","demo_checkpoint":"data/demo_execution_day0_v1/checkpoints/runtime.json","forward_signals":"data/forward_research/signals"},
 "services":{"forward":"quantbot-forward-research.service","demo":"quantbot-demo-execution.service"}}
def load(path):
    value=dict(DEFAULT);source=json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    value.update({key:item for key,item in source.items() if key not in {"paths","thresholds","recovery","services"}})
    for key in ("paths","thresholds","recovery","services"):value[key]={**DEFAULT[key],**source.get(key,{})}
    if value.get("auto_repair_enabled") is not False:raise ValueError("unattended_auto_repair_must_default_false")
    return value
