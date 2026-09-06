"""Side-effect-free, fail-closed authorization checks for frozen research."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Mapping

from .candidate_universe import CURRENT_PROTOCOL_SCOPE, build_candidate_universe
from .freeze_manifest import SCHEMA_VERSION, _hash, boundary_identity, build_freeze_manifest, protocol_scope_dict
from .model_registry import register_existing_models, validate_registry

class FreezeAuthorizationError(RuntimeError):
    def __init__(self, reasons: list[str]):
        self.reasons = tuple(reasons)
        super().__init__(",".join(reasons))

def _load(path: Path) -> Mapping[str, Any]:
    if not path.exists(): raise FreezeAuthorizationError(["missing_freeze_manifest"])
    return json.loads(path.read_text(encoding="utf-8"))

def validate_pre_research_freeze(manifest_path: str | Path, boundary_lock: Mapping[str, Any], models=None, scope=None) -> dict[str, Any]:
    manifest = _load(Path(manifest_path)); reasons=[]
    if manifest.get("schema_version") != SCHEMA_VERSION: reasons.append("unsupported_freeze_schema")
    if models is None:
        # Registration APIs intentionally reject duplicates.  Build a temporary
        # universe for validation, then restore the exact caller-owned registry.
        from .model_registry import _REGISTRY
        from quantbot.strategies.model_pool import register_model_pool
        snapshot = dict(_REGISTRY)
        try:
            _REGISTRY.clear()
            register_existing_models(); register_model_pool(); validate_registry()
            models=build_candidate_universe()
        finally:
            _REGISTRY.clear(); _REGISTRY.update(snapshot)
    scope = CURRENT_PROTOCOL_SCOPE if scope is None else scope
    candidate_hash = __import__("quantbot.research.candidate_universe", fromlist=["candidate_universe_hash"]).candidate_universe_hash(tuple(models))
    scope_hash = _hash(protocol_scope_dict(scope)); boundary = boundary_identity(boundary_lock); boundary_hash = _hash(boundary)
    identity = _hash({"candidate_universe_hash":candidate_hash,"protocol_scope_hash":scope_hash,"boundary_identity_hash":boundary_hash})
    for key,actual in (("candidate_universe_hash",candidate_hash),("protocol_scope_hash",scope_hash),("boundary_identity_hash",boundary_hash),("research_freeze_identity",identity)):
        if manifest.get(key)!=actual: reasons.append(f"{key}_mismatch")
    frozen=manifest.get("models",[]); current=list(models)
    if len(frozen)!=len(current): reasons.append("model_count_mismatch")
    if {x.get("model_id") for x in frozen}!={x.model_id for x in current}: reasons.append("model_id_set_mismatch")
    status=manifest.get("freeze_status",{})
    if status.get("oos_status")!="SEALED": reasons.append("oos_not_sealed")
    if status.get("oos_authorization")!="NOT_AUTHORIZED": reasons.append("oos_authorization_changed")
    if status.get("formal_research_results_embedded") is not False: reasons.append("formal_results_embedded")
    if scope.engine_identity!="quantbot.backtest.engine_v2.BacktestEngine": reasons.append("canonical_engine_identity_mismatch")
    if scope.cost_model_identity!="quantbot.backtest.costs.CostModel": reasons.append("canonical_cost_model_identity_mismatch")
    if reasons: raise FreezeAuthorizationError(reasons)
    return {"research_freeze_identity": identity, "oos_authorized": False}

def require_oos_authorized(*args, **kwargs):
    validate_pre_research_freeze(*args, **kwargs)
    raise FreezeAuthorizationError(["oos_not_authorized"])
