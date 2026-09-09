"""Canonical, identity-bound future-stage contracts after accepted N11/N12.

The module wires *inputs* and the existing shared-capital engine.  It does not
open OOS, run MC/long-horizon research, start Paper, or connect an exchange.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Sequence
from .artifact_store import seal, validate_seal
from .authorization import AuthorizationError, Capability, locked_evidence

class StageState(str, Enum): PENDING="PENDING"; RUNNING="RUNNING"; INTERRUPTED="INTERRUPTED"; FAILED="FAILED"; COMPLETE="COMPLETE"

@dataclass(frozen=True)
class N12CandidateInput:
    candidate_identity: str; validation_result_identity: str; selected_train_result_identity: str
    task_identity: str; model_id: str; family: str; symbol: str; params: Mapping[str, Any]

@dataclass(frozen=True)
class PortfolioProtocol:
    n11_identity: str; n12_identity: str; correlation_sha256: str; dataset_id: str; boundary_identity_hash: str
    research_freeze_identity: str; research_plan_identity: str; engine_identity: str; cost_model_identity: str
    candidates: tuple[N12CandidateInput, ...]; policy_identity: str; state: str="FROZEN_INPUT"

    def identity(self) -> str:
        return seal({"schema_version":"quantbot-portfolio-protocol-v2", **asdict(self)})["artifact_identity"]

def build_portfolio_protocol(*, n11_identity: str, n12_artifact: Mapping[str, Any], candidates: Sequence[N12CandidateInput],
                             correlation_sha256: str, source: Mapping[str, Any], policy_identity: str) -> dict[str, Any]:
    """Build the only permitted N12 portfolio input; no ranking/search occurs."""
    validate_seal(n12_artifact)
    if n12_artifact.get("oos_status")!="SEALED" or n12_artifact.get("oos_authorization")!="NOT_AUTHORIZED": raise ValueError("n12_oos_not_sealed")
    if n12_artifact.get("input_n11_artifact_identity")!=n11_identity: raise ValueError("n11_n12_identity_mismatch")
    ids=[row.candidate_identity for row in candidates]
    if not ids or len(ids)!=len(set(ids)): raise ValueError("n12_candidate_identity_invalid")
    required=("dataset_id","boundary_identity_hash","research_freeze_identity","research_plan_identity","engine_identity","cost_model_identity")
    if any(not source.get(key) for key in required) or len(correlation_sha256)!=64 or not policy_identity: raise ValueError("portfolio_provenance_missing")
    return seal({"schema_version":"quantbot-portfolio-protocol-v2","n11_identity":n11_identity,"n12_identity":n12_artifact["artifact_identity"],"correlation_sha256":correlation_sha256,"source":dict(source),"policy_identity":policy_identity,"candidates":[asdict(row) for row in sorted(candidates,key=lambda row:row.candidate_identity)],"shared_capital_component":"quantbot.portfolio.shared_capital.shared_backtest","oos_status":"SEALED","oos_authorization":"NOT_AUTHORIZED"})

def validate_portfolio_protocol(protocol: Mapping[str, Any]) -> bool:
    validate_seal(protocol)
    if protocol.get("schema_version")!="quantbot-portfolio-protocol-v2" or protocol.get("oos_status")!="SEALED" or protocol.get("oos_authorization")!="NOT_AUTHORIZED": raise ValueError("portfolio_protocol_invalid")
    candidates=protocol.get("candidates"); ids=[row.get("candidate_identity") for row in candidates] if isinstance(candidates,list) else []
    if not ids or len(ids)!=len(set(ids)) or protocol.get("shared_capital_component")!="quantbot.portfolio.shared_capital.shared_backtest": raise ValueError("portfolio_protocol_candidate_binding_invalid")
    return True

def execute_shared_capital_protocol(protocol: Mapping[str, Any], *, frames, signal_maps, recipe_keys, boundary):
    """Canonical execution bridge; callers must separately pass future formal authorization.

    It intentionally delegates accounting to the existing engine rather than
    averaging sleeve curves or implementing a second portfolio ledger.
    """
    validate_portfolio_protocol(protocol)
    from quantbot.portfolio.shared_capital import shared_backtest
    return shared_backtest(frames,signal_maps,recipe_keys,boundary)

@dataclass(frozen=True)
class FormalStageProtocol:
    stage: str; input_identity: str; dataset_id: str; boundary_identity_hash: str; source_git_commit: str
    config: Mapping[str, Any]; oos_status: str="SEALED"; oos_authorization: str="NOT_AUTHORIZED"
    def artifact(self) -> dict[str, Any]: return seal({"schema_version":"quantbot-formal-stage-protocol-v1", **asdict(self)})

@dataclass(frozen=True)
class ResumableStageState:
    protocol_identity: str; state: StageState=StageState.PENDING; completed_chunks: tuple[str,...]=(); failed_chunks: tuple[str,...]=()
    def resume(self) -> "ResumableStageState":
        if self.state not in {StageState.PENDING,StageState.INTERRUPTED,StageState.FAILED}: raise ValueError("stage_not_resumable")
        return ResumableStageState(self.protocol_identity,StageState.RUNNING,self.completed_chunks,self.failed_chunks)

def validate_stage_protocol(artifact: Mapping[str, Any], *, accepted_input_identity: str) -> bool:
    validate_seal(artifact)
    if artifact.get("schema_version")!="quantbot-formal-stage-protocol-v1" or artifact.get("input_identity")!=accepted_input_identity: raise ValueError("stage_input_drift")
    if artifact.get("oos_status")!="SEALED" or artifact.get("oos_authorization")!="NOT_AUTHORIZED": raise ValueError("stage_oos_violation")
    return True

class PreOOSStatus(str, Enum): ENGINEERING_READY="ENGINEERING_READY"; RESEARCH_NOT_YET_COMPLETE="RESEARCH_NOT_YET_COMPLETE"; OOS_NOT_AUTHORIZED="OOS_NOT_AUTHORIZED"; OOS_AUTHORIZED="OOS_AUTHORIZED"
def pre_oos_gate(evidence: Mapping[str, str], *, required: Sequence[str], human_authorized: bool=False) -> PreOOSStatus:
    if any(not evidence.get(key) for key in required): return PreOOSStatus.RESEARCH_NOT_YET_COMPLETE
    # Engineering completeness can never become authority by itself.
    return PreOOSStatus.OOS_AUTHORIZED if human_authorized else PreOOSStatus.OOS_NOT_AUTHORIZED

def require_future_stage(capability: Capability) -> None:
    locked_evidence(capability).require()
