from __future__ import annotations
import json
from pathlib import Path

DEFAULT={"schema_version":"quantbot-unattended-supervisor-v1","auto_repair_enabled":False,
 "state_path":"runtime/unattended/state.json","thresholds":{"checkpoint_age_seconds":300,"demo_consumption_lag_seconds":300,"disk_percent":90,"memory_available_mb":256,"swap_percent":90},
 "recovery":{"auto_repair_enabled":False,"consecutive_threshold":2,"max_repairs_per_window":2,"repair_window_seconds":3600},
 "state_retention":{"sent_notifications":256,"recoveries":256,"delivery_lease_seconds":60},
 "paths":{"plan":"docs/handoff/FROZEN_RESEARCH_PLAN_N5.json","boundary":"data/reports/research_boundary_lock.json","manifest":"data/reports/research_manifest.json"},
 "production":{"forward":{"service":"quantbot-forward-research.service","data_root":"data/forward_research","checkpoint":"data/forward_research/checkpoints/runtime.json","checkpoint_schema":"quantbot-forward-checkpoint-v2"},"demo":{"service":"quantbot-demo-execution.service","data_root":"data/demo_execution_day0_v1","checkpoint":"data/demo_execution_day0_v1/checkpoints/runtime.json","checkpoint_schema":"quantbot-demo-checkpoint-v1","forward_signals":"data/forward_research/signals"}}}
def load(path):
    value=dict(DEFAULT);source=json.loads(Path(path).read_text(encoding="utf-8")) if path else {}
    value.update({key:item for key,item in source.items() if key not in {"paths","thresholds","recovery","state_retention","services"}})
    for key in ("paths","thresholds","recovery","state_retention"):value[key]={**DEFAULT[key],**source.get(key,{})}
    value["production"]={name:{**DEFAULT["production"][name],**source.get("production",{}).get(name,{})} for name in DEFAULT["production"]}
    if value.get("auto_repair_enabled") is not False:raise ValueError("unattended_auto_repair_must_default_false")
    for name,row in value["production"].items():
        if not all(isinstance(row.get(key),str) and row[key] for key in ("service","data_root","checkpoint","checkpoint_schema")):raise ValueError(f"unattended_{name}_resource_declaration_invalid")
    return value
