"""Frozen walk-forward request/result contracts.  No OOS data code is imported."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
from .artifact_store import seal, validate_seal
from .authorization import AuthorizationError, Capability, locked_evidence

@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: str
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    oos_start: str
    oos_end: str

@dataclass(frozen=True)
class FrozenOOSExecutionRequest:
    research_freeze_identity: str
    research_plan_identity: str
    task_identity: str
    model_id: str
    symbol: str
    parameter_grid_hash: str
    fold: WalkForwardFold
    status: str = "LOCKED"

    def authorize(self) -> None:
        if self.status != "LOCKED": raise AuthorizationError("oos_request_state_invalid")
        locked_evidence(Capability.OOS, freeze_identity=self.research_freeze_identity, plan_identity=self.research_plan_identity).require()

def build_fold_result(request: FrozenOOSExecutionRequest, result: Mapping[str, object]) -> dict[str, object]:
    """For synthetic fixtures only; real OOS authorization fails before here."""
    request.authorize()
    return seal({"schema_version": "quantbot-walk-forward-fold-v1", "request": request.__dict__, "result": dict(result)})

def validate_fold_result(artifact: Mapping[str, object]) -> bool:
    validate_seal(artifact)
    if artifact.get("schema_version") != "quantbot-walk-forward-fold-v1": raise ValueError("fold_schema_invalid")
    return True
