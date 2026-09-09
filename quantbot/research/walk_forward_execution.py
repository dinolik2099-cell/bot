"""Frozen walk-forward request/result contracts.  No OOS data code is imported."""
from __future__ import annotations
from dataclasses import dataclass, asdict
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
    def identity(self) -> str:
        return seal({"schema_version": "quantbot-walk-forward-fold-definition-v1", **self.__dict__})["artifact_identity"]

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

def validate_fold_result(artifact: Mapping[str, object], *, request: FrozenOOSExecutionRequest) -> bool:
    validate_seal(artifact)
    if artifact.get("schema_version") != "quantbot-walk-forward-fold-v1": raise ValueError("fold_schema_invalid")
    if artifact.get("request") != asdict(request) or not isinstance(artifact.get("result"),Mapping): raise ValueError("fold_request_binding_invalid")
    if request.status != "LOCKED": raise ValueError("fold_request_state_invalid")
    return True

@dataclass(frozen=True)
class WalkForwardState:
    request_identity: str
    completed_fold_ids: tuple[str, ...] = ()
    failed_fold_ids: tuple[str, ...] = ()
    status: str = "PENDING"
    def resume(self) -> "WalkForwardState":
        if self.status not in {"INTERRUPTED", "FAILED", "PENDING"}: raise ValueError("walk_forward_not_resumable")
        return WalkForwardState(self.request_identity, self.completed_fold_ids, self.failed_fold_ids, "RUNNING")

def aggregate_fold_artifacts(requests: tuple[FrozenOOSExecutionRequest, ...], artifacts: tuple[Mapping[str, object], ...]) -> dict[str, object]:
    """Identity-only aggregation; authorized execution is intentionally absent."""
    expected = {request.fold.fold_id:request for request in requests}
    if len(expected)!=len(requests): raise ValueError("walk_forward_duplicate_fold_id")
    actual = {artifact.get("request", {}).get("fold", {}).get("fold_id") for artifact in artifacts}
    if set(expected) != actual or len(actual) != len(artifacts): raise ValueError("walk_forward_fold_set_mismatch")
    for artifact in artifacts:
        fold_id=artifact["request"]["fold"]["fold_id"]
        validate_fold_result(artifact,request=expected[fold_id])
    return seal({"schema_version": "quantbot-walk-forward-aggregate-v1", "fold_result_identities": sorted(artifact["artifact_identity"] for artifact in artifacts),
                 "request_identities": sorted(seal(asdict(request))["artifact_identity"] for request in requests), "oos_authorized": False})
